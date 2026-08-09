from __future__ import annotations

import logging
from datetime import datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import quote

import httpx
from pydantic import TypeAdapter, ValidationError

from xteink_sugartv.models import GlucoseReading, Trend, utc_now
from xteink_sugartv.normalize import (
    VALUE_SUFFIXES,
    normalize_trend,
    normalize_unit,
    parse_timestamp,
    sibling_entity_id,
    timestamp_from_age_state,
)

if TYPE_CHECKING:
    from xteink_sugartv.config import Settings

log = logging.getLogger(__name__)
STATE_ADAPTER = TypeAdapter(dict[str, Any])


class ReadingProvider(Protocol):
    async def get_reading(self) -> GlucoseReading: ...

    async def close(self) -> None: ...


class MockReadingProvider:
    async def get_reading(self) -> GlucoseReading:
        return GlucoseReading(
            value=112,
            unit="mg/dL",
            trend=Trend.STEADY,
            measured_at=utc_now(),
            source_entity="sensor.mock_glucose_value",
            delta=1,
        )

    async def close(self) -> None:
        return None


class HomeAssistantReadingProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.ha_url or not settings.ha_token or not settings.ha_entity_id:
            raise ValueError("Home Assistant settings are incomplete")
        self._settings = settings
        self._entity_id = settings.ha_entity_id
        self._client = client or httpx.AsyncClient(
            base_url=settings.ha_url.rstrip("/"),
            headers={"Authorization": f"Bearer {settings.ha_token}"},
            timeout=10,
            trust_env=False,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _state(self, entity_id: str) -> dict[str, Any] | None:
        path = f"/api/states/{quote(entity_id, safe='.')}"
        log.info("Home Assistant request: GET %s", path)
        response = await self._client.get(path)
        log.info(
            "Home Assistant response: GET %s -> %s %s",
            path,
            response.status_code,
            response.text,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload = response.json()
        try:
            return STATE_ADAPTER.validate_python(payload, strict=True)
        except ValidationError as exc:
            log.warning("Home Assistant response validation failed for GET %s: %s", path, exc)
            return None

    async def _history(self, entity_id: str) -> list[dict[str, Any]]:
        now = utc_now()
        start = (now - timedelta(minutes=25)).isoformat()
        path = f"/api/history/period/{quote(start, safe=':+')}"
        params = {
            "filter_entity_id": entity_id,
            "end_time": now.isoformat(),
            "minimal_response": "true",
            "no_attributes": "true",
            "significant_changes_only": "false",
        }
        log.info("Home Assistant request: GET %s params=%s", path, params)
        response = await self._client.get(path, params=params)
        log.info(
            "Home Assistant response: GET %s -> %s %s",
            path,
            response.status_code,
            response.text,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
            return []
        history = cast("list[object]", payload[0])
        states: list[dict[str, Any]] = []
        for index, state in enumerate(history):
            try:
                states.append(STATE_ADAPTER.validate_python(state, strict=True))
            except ValidationError as exc:
                log.warning(
                    "Home Assistant history state validation failed for GET %s at index %s: %s",
                    path,
                    index,
                    exc,
                )
                continue
        return states

    async def get_reading(self) -> GlucoseReading:
        try:
            return await self._get_reading(self._entity_id)
        except httpx.HTTPError as exc:
            log.warning("Home Assistant request failed for %s: %s", self._entity_id, exc)
            return self._error(self._entity_id, "Home Assistant is unreachable")

    async def _get_reading(self, entity_id: str) -> GlucoseReading:
        state = await self._state(entity_id)
        if not state:
            return self._error(entity_id, "Entity not found")

        raw_value = state.get("state")
        if raw_value in {None, "unknown", "unavailable"}:
            return self._error(entity_id, f"Entity state is {raw_value}")
        try:
            value = float(str(raw_value).replace(",", "."))
        except ValueError:
            return self._error(entity_id, "Entity state is not numeric")

        raw_attributes = state.get("attributes")
        attributes = cast("dict[str, Any]", raw_attributes) if isinstance(raw_attributes, dict) else {}
        unit = normalize_unit(attributes.get("unit_of_measurement"))
        trend = await self._resolve_trend(entity_id, attributes)
        measured_at = await self._resolve_timestamp(entity_id, state, attributes)
        delta = None
        cadence_seconds = None
        try:
            history = await self._history(entity_id)
            delta, cadence_seconds = self._history_metrics(
                history,
                value=value,
                measured_at=measured_at,
                unit=unit,
            )
        except httpx.HTTPError as exc:
            log.warning("Home Assistant history request failed for %s: %s", entity_id, exc)
        return GlucoseReading(
            value=value,
            unit=unit,
            trend=trend,
            measured_at=measured_at,
            source_entity=entity_id,
            delta=delta,
            cadence_seconds=cadence_seconds,
        )

    def _error(self, entity_id: str, message: str) -> GlucoseReading:
        log.warning("Home Assistant reading failed for %s: %s", entity_id, message)
        return GlucoseReading(
            value=None,
            unit="mg/dL",
            trend=Trend.UNKNOWN,
            measured_at=None,
            source_entity=entity_id,
            error=message,
        )

    async def _resolve_trend(self, entity_id: str, attributes: dict[str, Any]) -> Trend:
        candidates: list[str] = []
        if self._settings.ha_trend_entity_id:
            candidates.append(self._settings.ha_trend_entity_id)
        for value_tail, trend_tail in (
            (VALUE_SUFFIXES["dexcom"], "glucose_trend"),
            (VALUE_SUFFIXES["carelink_mgdl"], "last_glucose_trend"),
            (VALUE_SUFFIXES["carelink_mmol"], "last_glucose_trend"),
            ("last_sg_mgdl", "last_sg_trend"),
            ("last_sg_mmol", "last_sg_trend"),
        ):
            candidate = sibling_entity_id(entity_id, value_tail, trend_tail)
            if candidate:
                candidates.append(candidate)
        if "_" in entity_id:
            candidates.append(f"{entity_id.rsplit('_', 1)[0]}_trend")

        for candidate in dict.fromkeys(candidates):
            sibling = await self._state(candidate)
            if sibling:
                return normalize_trend(sibling.get("state"))
        return normalize_trend(attributes.get("direction") or attributes.get("trend"))

    async def _resolve_timestamp(
        self,
        entity_id: str,
        state: dict[str, Any],
        attributes: dict[str, Any],
    ) -> datetime | None:
        configured = self._settings.ha_timestamp_attribute
        timestamp_attribute = configured or "measurement_timestamp"
        parsed = parse_timestamp(attributes.get(timestamp_attribute))
        if parsed:
            return parsed
        if not configured:
            looks_like_nightscout = (
                attributes.get("device_class") == "blood_glucose_concentration"
                and "date" in attributes
                and "direction" in attributes
                and "delta" in attributes
            )
            if looks_like_nightscout:
                parsed = parse_timestamp(attributes.get("date"))
                if parsed:
                    return parsed

            for value_tail, timestamp_tail in (
                (VALUE_SUFFIXES["carelink_mgdl"], "last_glucose_update"),
                (VALUE_SUFFIXES["carelink_mmol"], "last_glucose_update"),
            ):
                candidate = sibling_entity_id(entity_id, value_tail, timestamp_tail)
                if candidate and (sibling := await self._state(candidate)):
                    parsed = parse_timestamp(sibling.get("state"))
                    if parsed:
                        return parsed

            age_candidate = sibling_entity_id(entity_id, VALUE_SUFFIXES["librelink"], "minutes_since_update")
            if age_candidate and (age_state := await self._state(age_candidate)):
                parsed = timestamp_from_age_state(age_state)
                if parsed:
                    return parsed

        return parse_timestamp(state.get("last_updated") or state.get("last_changed"))

    @staticmethod
    def _history_metrics(
        states: list[dict[str, Any]],
        *,
        value: float,
        measured_at: datetime | None,
        unit: str,
    ) -> tuple[float | None, float | None]:
        valid: list[tuple[float, datetime]] = []
        for state in states:
            try:
                state_value = float(str(state.get("state")).replace(",", "."))
            except (TypeError, ValueError):
                continue
            timestamp = parse_timestamp(
                state.get("last_updated") or state.get("last_changed") or state.get("last_reported")
            )
            if timestamp:
                valid.append((state_value, timestamp))

        unique_times = sorted({timestamp for _, timestamp in valid})
        gaps: list[float] = []
        for earlier, later in pairwise(unique_times):
            gap = (later - earlier).total_seconds()
            if gap >= 60:
                gaps.append(gap)
        cadence = sorted(gaps)[(len(gaps) - 1) // 2] if gaps else None

        if not measured_at:
            return None, cadence
        target = measured_at - timedelta(minutes=5)
        candidate = min(
            (
                (abs((timestamp - target).total_seconds()), state_value, timestamp)
                for state_value, timestamp in valid
                if abs((timestamp - measured_at).total_seconds()) >= 1
            ),
            default=None,
            key=lambda item: item[0],
        )
        if candidate is None:
            return None, cadence
        _, previous_value, previous_time = candidate
        if abs((measured_at - previous_time).total_seconds()) >= 9 * 60:
            return None, cadence
        delta = value - previous_value
        return (round(delta, 1) if unit == "mmol/L" else round(delta)), cadence
