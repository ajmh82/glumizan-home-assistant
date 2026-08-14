from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import CONF_BASE_URL, CONF_CALLBACK_SECRET, DOMAIN, signal_patients_changed

_LOGGER = logging.getLogger(__name__)


class GluMizanCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self._session = aiohttp.ClientSession()
        self.patient_data = {}
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=30))

    async def async_close(self):
        await self._session.close()

    def _snapshot(self):
        return {alias: dict(value) for alias, value in self.patient_data.items()}

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(25):
                async with self._session.get(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/events?limit=1", headers=self._headers()) as response:
                    if response.status < 300:
                        await self.async_receive_events((await response.json()).get("events", []))
                return self._snapshot()
        except TimeoutError as error:
            raise UpdateFailed("GluMizan bridge unavailable") from error

    async def async_receive_events(self, events):
        event_ids = []
        new_aliases = []
        for event in events:
            alias = event["patientAlias"]
            if alias not in self.patient_data:
                new_aliases.append(alias)
            current = self.patient_data.setdefault(alias, {"alias": alias, "glucose": None, "trend": None, "freshness": "UNKNOWN", "episode": None})
            payload = event.get("payload", {})
            glucose = payload.get("glucose")
            if glucose:
                current.update(glucose)
            if event["type"].startswith("episode."):
                current["episode"] = event["type"]
                current["episode_id"] = payload.get("episodeId") or payload.get("activeEpisodeId")
            if isinstance(event["id"], str) and len(event["id"]) == 36:
                event_ids.append(event["id"])
            await self.async_refresh_presence_context(alias)
        self.async_set_updated_data(self._snapshot())
        if new_aliases:
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), new_aliases)
        else:
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), list(self.patient_data))
        if event_ids:
            headers = self._headers()
            try:
                async with self._session.post(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/events/ack", headers=headers, json={"eventIds": event_ids}) as response:
                    if response.status >= 300:
                        _LOGGER.warning("GluMizan event acknowledgement failed with status %s", response.status)
            except Exception:
                _LOGGER.warning("GluMizan event acknowledgement failed", exc_info=True)

    def _headers(self):
        return {"X-Home-Assistant-Signature": self.entry.data[CONF_CALLBACK_SECRET]}

    async def async_refresh_presence_context(self, alias):
        async with self._session.get(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/patients/{alias}/presence", headers=self._headers()) as response:
            if response.status < 300:
                self.patient_data[alias]["caregivers"] = (await response.json()).get("caregivers", [])

    async def async_command(self, alias, grant_id, action, episode_id=None):
        headers = {"Idempotency-Key": str(uuid.uuid4()), **self._headers()}
        body = {"action": action, "patientAlias": alias, "grantId": grant_id, "metadata": {"action": "caregiver_response"}}
        if episode_id:
            body["episodeId"] = episode_id
        async with self._session.post(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/commands", headers=headers, json=body) as response:
            if response.status >= 300:
                raise UpdateFailed("GluMizan command rejected")
        await self.async_refresh_presence_context(alias)
        self.async_set_updated_data(self._snapshot())

    async def async_request_reconcile(self):
        headers = self._headers()
        async with self._session.post(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/reconcile", headers=headers, json={}) as response:
            if response.status >= 300:
                _LOGGER.warning("GluMizan reconcile request failed with status %s", response.status)

    async def async_acknowledge(self, alias, grant_id, episode_id):
        if not episode_id:
            raise UpdateFailed("No active GluMizan episode for this patient")
        await self.async_command(alias, grant_id, "caregiver.acknowledge", episode_id)
