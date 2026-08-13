from __future__ import annotations

import asyncio
import logging
import uuid
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .const import CONF_BASE_URL, CONF_CALLBACK_SECRET, DOMAIN, SIGNAL_PATIENTS_CHANGED

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
        self.async_set_updated_data(self.patient_data)
        if new_aliases:
            async_dispatcher_send(self.hass, SIGNAL_PATIENTS_CHANGED, new_aliases)
        if event_ids:
            headers = {"X-Home-Assistant-Signature": self.entry.data[CONF_CALLBACK_SECRET]}
            async with self._session.post(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/events/ack", headers=headers, json={"eventIds": event_ids}) as response:
                if response.status >= 300:
                    raise UpdateFailed("GluMizan event acknowledgement failed")

    async def async_acknowledge(self, alias, episode_id):
        headers = {"Idempotency-Key": str(uuid.uuid4()), "X-Home-Assistant-Signature": self.entry.data[CONF_CALLBACK_SECRET]}
        if not episode_id:
            raise UpdateFailed("No active GluMizan episode for this patient")
        body = {"action": "caregiver.acknowledge", "patientAlias": alias, "episodeId": episode_id, "caregiverUserId": self.entry.data["caregiver_user_id"], "metadata": {"action": "caregiver_response"}}
        async with self._session.post(f"{self.entry.data[CONF_BASE_URL]}/v1/integrations/home-assistant/commands", headers=headers, json=body) as response:
            if response.status >= 300:
                raise UpdateFailed("GluMizan acknowledgement rejected")
