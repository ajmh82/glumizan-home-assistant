from __future__ import annotations

from datetime import datetime

_TRENDS = {
    "double_up": ("Rapidly rising", "mdi:arrow-up-bold", "DoubleUp"),
    "up": ("Rising", "mdi:arrow-up", "SingleUp"),
    "forty_five_up": ("Slightly rising", "mdi:arrow-top-right", "FortyFiveUp"),
    "flat": ("Steady", "mdi:arrow-right", "Flat"),
    "forty_five_down": ("Slightly falling", "mdi:arrow-bottom-right", "FortyFiveDown"),
    "down": ("Falling", "mdi:arrow-down", "SingleDown"),
    "double_down": ("Rapidly falling", "mdi:arrow-down-bold", "DoubleDown"),
}


def trend_presentation(value: str | None) -> tuple[str, str]:
    trend = _TRENDS.get(value or "")
    return trend[:2] if trend else ("Unknown", "mdi:help-circle-outline")


def nightscout_direction(value: str | None) -> str | None:
    trend = _TRENDS.get(value or "")
    return trend[2] if trend else None


def last_reading_time(measured_at: str | None) -> str | None:
    if not measured_at:
        return None
    try:
        return datetime.fromisoformat(measured_at.replace("Z", "+00:00")).astimezone().strftime("%-I:%M %p")
    except ValueError:
        return None
