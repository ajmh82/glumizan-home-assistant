DOMAIN = "glumizan"
PLATFORMS = ["sensor", "button"]
CONF_BASE_URL = "base_url"
CONF_CALLBACK_SECRET = "callback_secret"


def signal_patients_changed(entry_id: str) -> str:
    return f"{DOMAIN}_patients_changed_{entry_id}"
