from fastapi.testclient import TestClient

from xteink_sugartv.app import create_app
from xteink_sugartv.config import Settings
from xteink_sugartv.service import Frame

DEVICE_ID = "AA:BB:CC:DD:EE:FF"


def client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                api_key="test-secret",
                device_id=DEVICE_ID,
                public_base_url="https://display.test",
                refresh_seconds=60,
                mock=True,
            )
        )
    )


def test_provisions_and_serves_a_frame() -> None:
    with client() as test_client:
        setup = test_client.get("/api/setup", headers={"ID": DEVICE_ID})
        assert setup.status_code == 200
        payload = setup.json()
        assert payload["status"] == 200
        assert payload["api_key"] == "test-secret"

        display = test_client.get(
            "/api/display",
            headers={"ID": DEVICE_ID, "Access-Token": "test-secret"},
        )
        assert display.status_code == 200
        display_payload = display.json()
        assert display_payload["refresh_rate"] == 60
        frame_path = display_payload["image_url"].removeprefix("https://display.test")
        frame = test_client.get(frame_path)
        assert frame.status_code == 200
        assert frame.headers["content-type"] == "image/bmp"
        assert frame.content[:2] == b"BM"


def test_rejects_wrong_device_and_token() -> None:
    with client() as test_client:
        unknown = test_client.get("/api/setup", headers={"ID": "00:00:00:00:00:00"})
        assert unknown.status_code == 404
        unauthorized = test_client.get(
            "/api/display",
            headers={"ID": DEVICE_ID, "Access-Token": "wrong"},
        )
        assert unauthorized.status_code == 401


def test_serves_latest_frame_with_basic_auth() -> None:
    with client() as test_client:
        response = test_client.get(
            "/screen/latest.bmp",
            params={"device_id": DEVICE_ID},
            auth=("x3", "test-secret"),
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/bmp"
        assert response.headers["cache-control"] == "no-store"
        assert response.content[:2] == b"BM"


def test_latest_frame_rejects_invalid_basic_auth() -> None:
    with client() as test_client:
        missing = test_client.get("/screen/latest.bmp", params={"device_id": DEVICE_ID})
        wrong_device = test_client.get(
            "/screen/latest.bmp",
            params={"device_id": "00:00:00:00:00:00"},
            auth=("x3", "test-secret"),
        )
        wrong_password = test_client.get(
            "/screen/latest.bmp",
            params={"device_id": DEVICE_ID},
            auth=("x3", "wrong"),
        )

        assert missing.status_code == 401
        assert wrong_device.status_code == 404
        assert wrong_password.status_code == 401


def test_backs_off_when_the_frame_reports_an_upstream_error() -> None:
    class ErrorDisplay:
        async def current_frame(self) -> Frame:
            return Frame(filename="error.bmp", content=b"BM", has_error=True)

        async def close(self) -> None:
            return None

    with client() as test_client:
        test_client.app.state.display = ErrorDisplay()
        display = test_client.get(
            "/api/display",
            headers={"ID": DEVICE_ID, "Access-Token": "test-secret"},
        )
        assert display.status_code == 200
        assert display.json()["refresh_rate"] == 300
