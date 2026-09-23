from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from aiohttp import web
from homeassistant.components import frontend
from homeassistant.components.http import KEY_HASS_USER, HomeAssistantView, StaticPathConfig

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PANEL_PATH = "glumizan-account-link"
PANEL_COMPONENT = "glumizan-account-link-panel"
STATIC_URL = "/glumizan-static/account-link-panel.js"
_VIEWS_REGISTERED = "_glumizan_account_link_views_registered"
_STATIC_REGISTERED = "_glumizan_account_link_static_registered"
_PANEL_REGISTERED = "_glumizan_account_link_panel_registered"


def _valid_request_id(request_id: str) -> bool:
    try:
        return str(UUID(request_id)) == request_id.lower()
    except (AttributeError, ValueError):
        return False


def _coordinators(hass):
    return tuple(hass.data.get(DOMAIN, {}).values())


async def _resolve_pending_link(hass, request_id: str):
    matches = []
    for coordinator in _coordinators(hass):
        result = await coordinator.async_get_pending_account_link(request_id)
        if result.get("status") == "PENDING":
            matches.append((coordinator, result))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        _LOGGER.warning("GluMizan account-link request matched multiple installations")
    return None


def _not_found_response():
    return web.json_response({"error": "not_found"}, status=404)


class GluMizanAccountLinkGetView(HomeAssistantView):
    url = "/api/glumizan/account-link/{request_id}"
    name = "api:glumizan:account-link:get"
    requires_auth = True

    async def get(self, request, request_id):
        if not _valid_request_id(request_id):
            return _not_found_response()
        resolved = await _resolve_pending_link(request.app["hass"], request_id)
        if resolved is None:
            return _not_found_response()
        _coordinator, pending = resolved
        return web.json_response({"status": "PENDING", "expiresAt": pending["expiresAt"]})


class GluMizanAccountLinkCompleteView(HomeAssistantView):
    url = "/api/glumizan/account-link/{request_id}/complete"
    name = "api:glumizan:account-link:complete"
    requires_auth = True

    async def post(self, request, request_id):
        if not _valid_request_id(request_id):
            return _not_found_response()
        body = await request.read()
        if body not in (b"", b"{}"):
            return web.json_response({"error": "invalid_request"}, status=400)
        ha_user = request[KEY_HASS_USER]
        ha_user_id = getattr(ha_user, "id", None)
        if not isinstance(ha_user_id, str) or not ha_user_id:
            return _not_found_response()
        resolved = await _resolve_pending_link(request.app["hass"], request_id)
        if resolved is None:
            return _not_found_response()
        coordinator, _pending = resolved
        result = await coordinator.async_complete_pending_account_link(request_id, ha_user_id)
        if result.get("status") == "LINKED":
            return web.json_response({"status": "LINKED"})
        return _not_found_response()


class GluMizanAccountLinkCancelView(HomeAssistantView):
    url = "/api/glumizan/account-link/{request_id}/cancel"
    name = "api:glumizan:account-link:cancel"
    requires_auth = True

    async def post(self, request, request_id):
        if not _valid_request_id(request_id):
            return _not_found_response()
        body = await request.read()
        if body not in (b"", b"{}"):
            return web.json_response({"error": "invalid_request"}, status=400)
        resolved = await _resolve_pending_link(request.app["hass"], request_id)
        if resolved is None:
            return _not_found_response()
        coordinator, _pending = resolved
        result = await coordinator.async_cancel_pending_account_link(request_id)
        if result.get("status") == "CANCELLED":
            return web.json_response({"status": "CANCELLED"})
        return _not_found_response()


async def async_register_account_link_infrastructure(hass) -> None:
    if not hass.data.get(_VIEWS_REGISTERED):
        hass.http.register_view(GluMizanAccountLinkGetView())
        hass.http.register_view(GluMizanAccountLinkCompleteView())
        hass.http.register_view(GluMizanAccountLinkCancelView())
        hass.data[_VIEWS_REGISTERED] = True
    if not hass.data.get(_STATIC_REGISTERED):
        asset = Path(__file__).parent / "frontend" / "account-link-panel.js"
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL, str(asset), False)])
        hass.data[_STATIC_REGISTERED] = True
    if not hass.data.get(_PANEL_REGISTERED):
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=None,
            sidebar_icon=None,
            sidebar_default_visible=False,
            frontend_url_path=PANEL_PATH,
            config={"_panel_custom": {
                "name": PANEL_COMPONENT,
                "module_url": STATIC_URL,
                "embed_iframe": False,
                "trust_external": False,
                "handle_safe_area": False,
            }},
            require_admin=False,
            config_panel_domain=DOMAIN,
            show_in_sidebar=False,
        )
        hass.data[_PANEL_REGISTERED] = True


def async_remove_account_link_panel(hass) -> None:
    if hass.data.pop(_PANEL_REGISTERED, None):
        frontend.async_remove_panel(hass, PANEL_PATH, warn_if_unknown=False)
