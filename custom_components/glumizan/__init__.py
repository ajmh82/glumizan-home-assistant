from __future__ import annotations

import re
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from aiohttp import web
from .const import DOMAIN, PLATFORMS
from .coordinator import GluMizanCoordinator
from .pairing import migrate_options_into_data

VIEW_REGISTERED_KEY = "_glumizan_event_view_registered"
CLAIM_SERVICE_REGISTERED_KEY = "_glumizan_identity_claim_service_registered"
CLAIM_SERVICE = "connect_home_assistant_account"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    migrate_options_into_data(hass, entry)
    coordinator = GluMizanCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    if not hass.data.get(VIEW_REGISTERED_KEY):
        hass.http.register_view(GluMizanEventView())
        hass.data[VIEW_REGISTERED_KEY] = True
    _register_identity_claim_service(hass)
    try:
        await coordinator.async_config_entry_first_refresh()
        await coordinator.async_request_reconcile()
        await coordinator.async_request_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await coordinator.async_report_notification_destinations_when_ready()
        coordinator.start_sse_listener()
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await coordinator.async_close()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    coordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.async_close()
    if not hass.data[DOMAIN]:
        hass.data.pop(VIEW_REGISTERED_KEY, None)
        if hass.data.pop(CLAIM_SERVICE_REGISTERED_KEY, None):
            hass.services.async_remove(DOMAIN, CLAIM_SERVICE)
    return unloaded


def _register_identity_claim_service(hass):
    if hass.data.get(CLAIM_SERVICE_REGISTERED_KEY) or not getattr(hass, "services", None):
        return

    async def async_connect_account(call):
        claim_code = call.data.get("claim_code") if isinstance(call.data, dict) else None
        ha_user_id = getattr(getattr(call, "context", None), "user_id", None)
        if not isinstance(claim_code, str) or not isinstance(ha_user_id, str) or not ha_user_id:
            raise ValueError("A signed-in Home Assistant user and claim code are required")
        coordinators = list(hass.data.get(DOMAIN, {}).values())
        for coordinator in coordinators:
            if await coordinator.async_complete_identity_claim(claim_code, ha_user_id):
                return
        raise ValueError("The Home Assistant account claim could not be completed")

    hass.services.async_register(DOMAIN, CLAIM_SERVICE, async_connect_account)
    hass.data[CLAIM_SERVICE_REGISTERED_KEY] = True


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
