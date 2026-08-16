from __future__ import annotations

from .const import CONF_BASE_URL, CONF_CALLBACK_SECRET

EVENTS_PATH = "/v1/integrations/home-assistant/events?limit=1"


def canonical_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def persist_runtime_credentials(hass, entry, base_url: str, callback_secret: str) -> None:
    hass.config_entries.async_update_entry(
        entry,
        data={
            CONF_BASE_URL: canonical_base_url(base_url),
            CONF_CALLBACK_SECRET: callback_secret.strip(),
        },
        options={},
    )


def migrate_options_into_data(hass, entry) -> bool:
    options = dict(getattr(entry, "options", None) or {})
    if CONF_CALLBACK_SECRET not in options and CONF_BASE_URL not in options:
        return False
    persist_runtime_credentials(
        hass,
        entry,
        str(options.get(CONF_BASE_URL, entry.data.get(CONF_BASE_URL, ""))),
        str(options.get(CONF_CALLBACK_SECRET, entry.data.get(CONF_CALLBACK_SECRET, ""))),
    )
    return True


async def validate_pairing(base_url: str, callback_secret: str, session=None) -> str | None:
    normalized = canonical_base_url(base_url)
    secret = callback_secret.strip()
    if not normalized.startswith("https://"):
        return "https_required"
    if not secret:
        return "invalid_secret"
    owns_session = session is None
    if session is None:
        import aiohttp
        client = aiohttp.ClientSession()
    else:
        client = session
    try:
        async with client.get(
            f"{normalized}{EVENTS_PATH}",
            headers={"X-Home-Assistant-Signature": secret},
        ) as response:
            if response.status < 300:
                return None
            if response.status in (401, 403):
                return "invalid_secret"
            if response.status == 503:
                return "integration_disabled"
            return "cannot_connect"
    except Exception:
        return "cannot_connect"
    finally:
        if owns_session:
            await client.close()


async def apply_validated_pairing(hass, entry, base_url: str, callback_secret: str, session=None) -> str | None:
    error = await validate_pairing(base_url, callback_secret, session=session)
    if error:
        return error
    persist_runtime_credentials(hass, entry, base_url, callback_secret)
    await hass.config_entries.async_reload(entry.entry_id)
    return None
