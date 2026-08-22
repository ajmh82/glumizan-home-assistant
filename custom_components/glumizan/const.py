DOMAIN = "glumizan"
PLATFORMS = ["sensor", "button"]
CONF_BASE_URL = "base_url"
CONF_CALLBACK_SECRET = "callback_secret"
SSE_STREAM_PATH = "/v1/integrations/home-assistant/stream"
SSE_RECONNECT_BASE_SECONDS = 2
SSE_RECONNECT_MAX_SECONDS = 30
SSE_BACKOFF_MULTIPLIER = 2


def signal_patients_changed(entry_id: str) -> str:
    return f"{DOMAIN}_patients_changed_{entry_id}"
