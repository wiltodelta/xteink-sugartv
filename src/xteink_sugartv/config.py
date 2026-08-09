from __future__ import annotations

import os
from dataclasses import dataclass

from xteink_sugartv.models import DEFAULT_THRESHOLDS, Thresholds


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str = "change-me"
    device_id: str | None = None
    public_base_url: str | None = None
    refresh_seconds: int = 60
    mock: bool = True
    ha_url: str | None = None
    ha_token: str | None = None
    ha_entity_id: str | None = None
    ha_trend_entity_id: str | None = None
    ha_timestamp_attribute: str | None = None
    locale: str = "ru"
    show_prediction: bool = True
    relative_time: bool = False
    dim_by_age: bool = False
    color_thresholds: bool = True
    urgent_low: float | None = None
    low: float | None = None
    high: float | None = None
    urgent_high: float | None = None

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls(
            api_key=os.getenv("XTEINK_API_KEY", "change-me"),
            device_id=os.getenv("XTEINK_DEVICE_ID") or None,
            public_base_url=os.getenv("XTEINK_PUBLIC_BASE_URL") or None,
            refresh_seconds=int(os.getenv("XTEINK_REFRESH_SECONDS", "60")),
            mock=_as_bool(os.getenv("XTEINK_MOCK"), default=True),
            ha_url=os.getenv("HA_URL") or None,
            ha_token=os.getenv("HA_TOKEN") or None,
            ha_entity_id=os.getenv("HA_ENTITY_ID") or None,
            ha_trend_entity_id=os.getenv("HA_TREND_ENTITY_ID") or None,
            ha_timestamp_attribute=os.getenv("HA_TIMESTAMP_ATTRIBUTE") or None,
            locale=os.getenv("XTEINK_LOCALE", "ru"),
            show_prediction=_as_bool(os.getenv("XTEINK_SHOW_PREDICTION"), default=True),
            relative_time=_as_bool(os.getenv("XTEINK_RELATIVE_TIME"), default=False),
            dim_by_age=_as_bool(os.getenv("XTEINK_DIM_BY_AGE"), default=False),
            color_thresholds=_as_bool(os.getenv("XTEINK_COLOR_THRESHOLDS"), default=True),
            urgent_low=_as_float(os.getenv("XTEINK_URGENT_LOW")),
            low=_as_float(os.getenv("XTEINK_LOW")),
            high=_as_float(os.getenv("XTEINK_HIGH")),
            urgent_high=_as_float(os.getenv("XTEINK_URGENT_HIGH")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.refresh_seconds < 60:
            raise ValueError("XTEINK_REFRESH_SECONDS must be at least 60")
        if not self.api_key:
            raise ValueError("XTEINK_API_KEY must not be empty")
        if not self.mock and not all((self.ha_url, self.ha_token, self.ha_entity_id)):
            raise ValueError("HA_URL, HA_TOKEN, and HA_ENTITY_ID are required when XTEINK_MOCK=false")
        if not self.mock and self.api_key == "change-me":
            raise ValueError("XTEINK_API_KEY must be changed when XTEINK_MOCK=false")

    @property
    def normalized_device_id(self) -> str | None:
        return self.device_id.upper() if self.device_id else None

    def thresholds_for(self, unit: str) -> Thresholds:
        defaults = DEFAULT_THRESHOLDS.get(unit, DEFAULT_THRESHOLDS["mg/dL"])
        return Thresholds(
            urgent_low=self.urgent_low if self.urgent_low is not None else defaults.urgent_low,
            low=self.low if self.low is not None else defaults.low,
            high=self.high if self.high is not None else defaults.high,
            urgent_high=(self.urgent_high if self.urgent_high is not None else defaults.urgent_high),
        )


def _as_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
