from datetime import UTC

from xteink_sugartv.models import Trend
from xteink_sugartv.normalize import normalize_trend, parse_timestamp, sibling_entity_id


def test_normalizes_integration_trends() -> None:
    assert normalize_trend("DoubleUp") is Trend.RISING_QUICKLY
    assert normalize_trend("5") is Trend.STEADY
    assert normalize_trend("decreasing fast") is Trend.FALLING_QUICKLY
    assert normalize_trend("unavailable") is Trend.UNKNOWN


def test_rebuilds_sibling_from_entity_tail() -> None:
    assert (
        sibling_entity_id("sensor.jane_glucose_value", "glucose_value", "glucose_trend") == "sensor.jane_glucose_trend"
    )
    assert sibling_entity_id("sensor.glucose_value", "glucose_value", "glucose_trend") == ("sensor.glucose_trend")


def test_parses_epoch_seconds_and_iso_timestamps() -> None:
    epoch = parse_timestamp("1767225600")
    iso = parse_timestamp("2026-01-01T00:00:00Z")
    assert epoch == iso
    assert iso
    assert iso.tzinfo is UTC
