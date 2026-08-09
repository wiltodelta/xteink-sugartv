from datetime import UTC, datetime, timedelta

from xteink_sugartv.models import GlucoseReading, Trend, Zone


def reading(value: float, *, age_minutes: int = 0, cadence_seconds: int = 300) -> GlucoseReading:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    return GlucoseReading(
        value=value,
        unit="mg/dL",
        trend=Trend.STEADY,
        measured_at=now - timedelta(minutes=age_minutes),
        source_entity="sensor.glucose",
        cadence_seconds=cadence_seconds,
    )


def test_threshold_boundaries_match_sugartv_strict_comparisons() -> None:
    assert reading(53).zone() is Zone.URGENT_LOW
    assert reading(54).zone() is Zone.LOW
    assert reading(70).zone() is Zone.TARGET
    assert reading(180).zone() is Zone.TARGET
    assert reading(250).zone() is Zone.HIGH
    assert reading(251).zone() is Zone.URGENT_HIGH


def test_age_ladder_uses_sensor_cadence_and_fifteen_minute_cap() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    assert reading(112, age_minutes=1, cadence_seconds=60).age_tier(now) == "current"
    assert reading(112, age_minutes=2, cadence_seconds=60).age_tier(now) == "aging"
    assert reading(112, age_minutes=4, cadence_seconds=60).age_tier(now) == "stale"
    assert reading(112, age_minutes=16, cadence_seconds=600).age_tier(now) == "stale"
