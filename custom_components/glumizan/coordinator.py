from __future__ import annotations

import asyncio
import logging
import uuid
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
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def async_close(self):
        await self._session.close()

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(25):
                return self.patient_data
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
            event_ids.append(event["id"])
            await self.async_refresh_presence_context(alias)
        self.async_set_updated_data(self.patient_data)
        if new_aliases:
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), new_aliases)
        else:
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), list(self.patient_data))
        if event_ids:
            headers = self._headers()
            async with self._session.post(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/events/ack", headers=headers, json={"eventIds": event_ids}) as response:
                if response.status >= 300:
                    raise UpdateFailed("GluMizan event acknowledgement failed")

    def _headers(self):
        return {"X-Home-Assistant-Signature": self.entry.data[CONF_CALLBACK_SECRET], "X-GluMizan-Installation-Id": self.entry.entry_id}

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
        self.async_set_updated_data(self.patient_data)

    async def async_acknowledge(self, alias, grant_id, episode_id):
        if not episode_id:
            raise UpdateFailed("No active GluMizan episode for this patient")
        await self.async_command(alias, grant_id, "caregiver.acknowledge", episode_id)
