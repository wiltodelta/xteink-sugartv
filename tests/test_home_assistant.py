from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from xteink_sugartv.config import Settings
from xteink_sugartv.home_assistant import HomeAssistantReadingProvider
from xteink_sugartv.models import Trend


@pytest.mark.anyio
async def test_reads_dexcom_value_and_sibling_trend() -> None:
    requested: list[str] = []
    states = {
        "/api/states/sensor.jane_glucose_value": {
            "state": "112",
            "attributes": {"unit_of_measurement": "mg/dL"},
            "last_updated": "2026-08-08T19:40:00Z",
        },
        "/api/states/sensor.jane_glucose_trend": {
            "state": "rising_slightly",
            "attributes": {},
            "last_updated": "2026-08-08T19:40:00Z",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        if request.url.path.startswith("/api/history/period/"):
            return httpx.Response(
                200,
                json=[
                    [
                        {"state": "110", "last_updated": "2026-08-08T19:35:00Z"},
                        {"state": "112", "last_updated": "2026-08-08T19:40:00Z"},
                    ]
                ],
            )
        payload = states.get(request.url.path)
        return httpx.Response(200, json=payload) if payload else httpx.Response(404)

    client = httpx.AsyncClient(
        base_url="http://ha.test",
        transport=httpx.MockTransport(handler),
    )
    provider = HomeAssistantReadingProvider(
        Settings(
            mock=False,
            api_key="secret",
            device_id="AA:BB:CC:DD:EE:FF",
            ha_url="http://ha.test",
            ha_token="token",
            ha_entity_id="sensor.jane_glucose_value",
        ),
        client=client,
    )

    reading = await provider.get_reading()

    assert reading.value == 112
    assert reading.trend is Trend.RISING_SLIGHTLY
    assert reading.measured_at == datetime(2026, 8, 8, 19, 40, tzinfo=UTC)
    assert reading.delta == 2
    assert reading.cadence_seconds == 300
    assert "/api/states/sensor.jane_glucose_value" in requested
    assert "/api/states/sensor.jane_glucose_trend" in requested
    await client.aclose()


@pytest.mark.anyio
async def test_nonsense_trend_override_falls_back_to_nightscout_attributes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/states/sensor.blood_sugar":
            return httpx.Response(
                200,
                json={
                    "state": "6.2",
                    "attributes": {
                        "unit_of_measurement": "mmol/L",
                        "device_class": "blood_glucose_concentration",
                        "date": 1786218000000,
                        "direction": "Flat",
                        "delta": None,
                    },
                    "last_updated": "2026-08-08T19:41:00Z",
                },
            )
        return httpx.Response(404, content=json.dumps({"message": "Entity not found"}))

    client = httpx.AsyncClient(
        base_url="http://ha.test",
        transport=httpx.MockTransport(handler),
    )
    provider = HomeAssistantReadingProvider(
        Settings(
            mock=False,
            api_key="secret",
            device_id="AA:BB:CC:DD:EE:FF",
            ha_url="http://ha.test",
            ha_token="token",
            ha_entity_id="sensor.blood_sugar",
            ha_trend_entity_id="sensor.this_does_not_exist",
        ),
        client=client,
    )

    reading = await provider.get_reading()

    assert reading.unit == "mmol/L"
    assert reading.trend is Trend.STEADY
    assert reading.measured_at == datetime.fromtimestamp(1786218000, tz=UTC)
    await client.aclose()


@pytest.mark.anyio
async def test_network_failure_becomes_an_explicit_error_reading() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.AsyncClient(
        base_url="http://ha.test",
        transport=httpx.MockTransport(handler),
    )
    provider = HomeAssistantReadingProvider(
        Settings(
            mock=False,
            api_key="secret",
            device_id="AA:BB:CC:DD:EE:FF",
            ha_url="http://ha.test",
            ha_token="token",
            ha_entity_id="sensor.jane_glucose_value",
        ),
        client=client,
    )

    reading = await provider.get_reading()

    assert reading.value is None
    assert reading.error == "Home Assistant is unreachable"
    await client.aclose()


@pytest.mark.anyio
async def test_invalid_state_payload_becomes_an_explicit_error_reading(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = httpx.AsyncClient(
        base_url="http://ha.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=["invalid"])),
    )
    provider = HomeAssistantReadingProvider(
        Settings(
            mock=False,
            api_key="secret",
            ha_url="http://ha.test",
            ha_token="token",
            ha_entity_id="sensor.jane_glucose_value",
        ),
        client=client,
    )

    reading = await provider.get_reading()

    assert reading.value is None
    assert reading.error == "Entity not found"
    assert "response validation failed" in caplog.text
    await client.aclose()


def test_history_uses_lower_median_cadence_and_strict_delta_window() -> None:
    states = [
        {"state": "100", "last_updated": "2026-08-08T11:43:00Z"},
        {"state": "105", "last_updated": "2026-08-08T11:48:00Z"},
        {"state": "108", "last_updated": "2026-08-08T11:53:00Z"},
        {"state": "112", "last_updated": "2026-08-08T12:00:00Z"},
    ]
    delta, cadence = HomeAssistantReadingProvider._history_metrics(
        states,
        value=112,
        measured_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        unit="mg/dL",
    )
    assert delta == 4
    assert cadence == 300

    too_old = states[:1] + states[-1:]
    delta, _ = HomeAssistantReadingProvider._history_metrics(
        too_old,
        value=112,
        measured_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        unit="mg/dL",
    )
    assert delta is None
