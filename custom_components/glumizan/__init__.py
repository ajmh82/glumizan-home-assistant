from __future__ import annotations

import re
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from aiohttp import web
from .const import DOMAIN, PLATFORMS
from .coordinator import GluMizanCoordinator

VIEW_REGISTERED_KEY = "_glumizan_event_view_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = GluMizanCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if not hass.data.get(VIEW_REGISTERED_KEY):
        hass.http.register_view(GluMizanEventView())
        hass.data[VIEW_REGISTERED_KEY] = True
    await coordinator.async_request_reconcile()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_close()
    if not hass.data[DOMAIN]:
        hass.data.pop(VIEW_REGISTERED_KEY, None)
    return unloaded


class GluMizanEventView(HomeAssistantView):
    url = "/api/glumizan/events"
    name = "api:glumizan:events"
    requires_auth = True

    async def post(self, request):
        hass = request.app["hass"]
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        if not coordinators:
            return web.json_response({"error": "not_ready"}, status=503)
        body = await request.json()
        events = body.get("events") if isinstance(body, dict) else None
        if not isinstance(events, list) or len(events) > 100 or any(not isinstance(event, dict) or not isinstance(event.get("id"), str) or not isinstance(event.get("type"), str) or not isinstance(event.get("patientAlias"), str) or not re.fullmatch(r"A[0-9]{8,}", event["patientAlias"]) or not isinstance(event.get("payload", {}), dict) for event in events):
            return web.json_response({"error": "invalid_events"}, status=400)
        await coordinators[0].async_receive_events(events)
        return web.json_response({"accepted": len(events)})
