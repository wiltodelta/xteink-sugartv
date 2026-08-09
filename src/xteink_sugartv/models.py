from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Trend(StrEnum):
    RISING_QUICKLY = "rising_quickly"
    RISING = "rising"
    RISING_SLIGHTLY = "rising_slightly"
    STEADY = "steady"
    FALLING_SLIGHTLY = "falling_slightly"
    FALLING = "falling"
    FALLING_QUICKLY = "falling_quickly"
    UNKNOWN = "unknown"


class Zone(StrEnum):
    URGENT_LOW = "urgent_low"
    LOW = "low"
    TARGET = "target"
    HIGH = "high"
    URGENT_HIGH = "urgent_high"


@dataclass(frozen=True, slots=True)
class Thresholds:
    urgent_low: float
    low: float
    high: float
    urgent_high: float


DEFAULT_THRESHOLDS = {
    "mg/dL": Thresholds(urgent_low=54, low=70, high=180, urgent_high=250),
    "mmol/L": Thresholds(urgent_low=3.0, low=3.9, high=10.0, urgent_high=13.9),
}


@dataclass(frozen=True, slots=True)
class GlucoseReading:
    value: float | None
    unit: str
    trend: Trend
    measured_at: datetime | None
    source_entity: str
    delta: float | None = None
    cadence_seconds: float | None = None
    error: str | None = None

    def age_seconds(self, now: datetime) -> float | None:
        if self.measured_at is None:
            return None
        return max(0.0, (now - self.measured_at).total_seconds())

    def zone(self, thresholds: Thresholds | None = None) -> Zone | None:
        if self.value is None:
            return None
        thresholds = thresholds or DEFAULT_THRESHOLDS.get(self.unit, DEFAULT_THRESHOLDS["mg/dL"])
        if self.value < thresholds.urgent_low:
            return Zone.URGENT_LOW
        if self.value < thresholds.low:
            return Zone.LOW
        if self.value > thresholds.urgent_high:
            return Zone.URGENT_HIGH
        if self.value > thresholds.high:
            return Zone.HIGH
        return Zone.TARGET

    def stale_after_seconds(self) -> float:
        cadence = self.cadence_seconds or 5 * 60
        return min(cadence * 3, 15 * 60)

    def age_tier(self, now: datetime) -> str:
        age = self.age_seconds(now)
        cadence = self.cadence_seconds or 5 * 60
        stale_after = self.stale_after_seconds()
        if age is None or age > stale_after:
            return "stale"
        if age > min(cadence, stale_after):
            return "aging"
        return "current"

    def is_stale(self, now: datetime) -> bool:
        return self.age_tier(now) == "stale"


def utc_now() -> datetime:
    return datetime.now(UTC)
