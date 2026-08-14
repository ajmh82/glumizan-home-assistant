from __future__ import annotations

from datetime import datetime

_TRENDS = {
    "double_up": ("Rapidly rising", "mdi:arrow-up-bold"),
    "up": ("Rising", "mdi:arrow-up"),
    "forty_five_up": ("Slightly rising", "mdi:arrow-top-right"),
    "flat": ("Steady", "mdi:arrow-right"),
    "forty_five_down": ("Slightly falling", "mdi:arrow-bottom-right"),
    "down": ("Falling", "mdi:arrow-down"),
    "double_down": ("Rapidly falling", "mdi:arrow-down-bold"),
}


def trend_presentation(value: str | None) -> tuple[str, str]:
    return _TRENDS.get(value or "", ("Unknown", "mdi:help-circle-outline"))


def last_reading_time(measured_at: str | None) -> str | None:
    if not measured_at:
        return None
    try:
        return datetime.fromisoformat(measured_at.replace("Z", "+00:00")).astimezone().strftime("%-I:%M %p")
    except ValueError:
        return None
