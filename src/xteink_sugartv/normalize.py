from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from xteink_sugartv.models import Trend

VALUE_SUFFIXES = {
    "dexcom": "glucose_value",
    "carelink_mgdl": "last_glucose_level_mg_dl",
    "carelink_mmol": "last_glucose_level_mmol",
    "librelink": "glucose_measurement",
}

TREND_MAP = {
    "rising_quickly": Trend.RISING_QUICKLY,
    "rising": Trend.RISING,
    "rising_slightly": Trend.RISING_SLIGHTLY,
    "steady": Trend.STEADY,
    "falling_slightly": Trend.FALLING_SLIGHTLY,
    "falling": Trend.FALLING,
    "falling_quickly": Trend.FALLING_QUICKLY,
    "doubleup": Trend.RISING_QUICKLY,
    "singleup": Trend.RISING,
    "fortyfiveup": Trend.RISING_SLIGHTLY,
    "flat": Trend.STEADY,
    "fortyfivedown": Trend.FALLING_SLIGHTLY,
    "singledown": Trend.FALLING,
    "doubledown": Trend.FALLING_QUICKLY,
    "2": Trend.RISING_QUICKLY,
    "3": Trend.RISING,
    "4": Trend.RISING_SLIGHTLY,
    "5": Trend.STEADY,
    "6": Trend.FALLING_SLIGHTLY,
    "7": Trend.FALLING,
    "8": Trend.FALLING_QUICKLY,
    "rising quickly": Trend.RISING_QUICKLY,
    "rising slightly": Trend.RISING_SLIGHTLY,
    "stable": Trend.STEADY,
    "falling slightly": Trend.FALLING_SLIGHTLY,
    "falling quickly": Trend.FALLING_QUICKLY,
    "decreasing_fast": Trend.FALLING_QUICKLY,
    "decreasing": Trend.FALLING,
    "increasing": Trend.RISING,
    "increasing_fast": Trend.RISING_QUICKLY,
    "decreasing fast": Trend.FALLING_QUICKLY,
    "increasing fast": Trend.RISING_QUICKLY,
    "up": Trend.RISING,
    "up_up": Trend.RISING_QUICKLY,
    "up_double": Trend.RISING_QUICKLY,
    "down": Trend.FALLING,
    "down_down": Trend.FALLING_QUICKLY,
    "down_double": Trend.FALLING_QUICKLY,
    "none": Trend.STEADY,
}


def normalize_unit(raw: Any) -> str:
    key = str(raw or "").lower()
    return "mmol/L" if key == "mmol/l" else "mg/dL"


def normalize_trend(raw: Any) -> Trend:
    key = str(raw or "").strip().lower()
    return TREND_MAP.get(key, Trend.UNKNOWN)


def sibling_entity_id(entity_id: str, value_tail: str, sibling_tail: str) -> str | None:
    if "." not in entity_id:
        return None
    domain, object_id = entity_id.split(".", 1)
    if object_id == value_tail:
        return f"{domain}.{sibling_tail}"
    suffix = f"_{value_tail}"
    if object_id.endswith(suffix):
        return f"{domain}.{object_id[: -len(value_tail)]}{sibling_tail}"
    return None


def parse_timestamp(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"unknown", "unavailable"}:
        return None
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        if abs(number) < 1e11:
            number *= 1000
        return datetime.fromtimestamp(number / 1000, tz=UTC)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def timestamp_from_age_state(state: dict[str, Any]) -> datetime | None:
    try:
        minutes = float(str(state.get("state")))
    except (TypeError, ValueError):
        return None
    if not 0 <= minutes <= 15:
        return None
    reported_at = parse_timestamp(state.get("last_updated") or state.get("last_changed"))
    return reported_at - timedelta(minutes=minutes) if reported_at else None
