from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from xteink_sugartv.config import Settings
from xteink_sugartv.home_assistant import HomeAssistantReadingProvider, MockReadingProvider
from xteink_sugartv.service import DisplayService

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

log = logging.getLogger(__name__)
basic_auth = HTTPBasic(auto_error=False)


class DeviceLog(BaseModel):
    message: str
    fw_version: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_env()
    resolved_settings.validate()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        provider = MockReadingProvider() if resolved_settings.mock else HomeAssistantReadingProvider(resolved_settings)
        app.state.display = DisplayService(provider, resolved_settings)
        yield
        await app.state.display.close()

    app = FastAPI(title="Xteink SugarTV", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved_settings

    def check_device(device_id: str | None) -> str:
        if not device_id:
            raise HTTPException(status_code=400, detail="Missing ID header")
        normalized = device_id.upper()
        allowed = resolved_settings.normalized_device_id
        if allowed and not hmac.compare_digest(normalized, allowed):
            raise HTTPException(status_code=404, detail="Unknown device")
        return normalized

    def authorize(device_id: str | None, access_token: str | None) -> str:
        normalized = check_device(device_id)
        if not access_token or not hmac.compare_digest(access_token, resolved_settings.api_key):
            raise HTTPException(status_code=401, detail="Invalid access token")
        return normalized

    def authorize_basic(
        device_id: str | None,
        credentials: HTTPBasicCredentials | None,
    ) -> str:
        normalized = check_device(device_id)
        valid_username = credentials is not None and hmac.compare_digest(credentials.username.encode(), b"x3")
        valid_password = credentials is not None and hmac.compare_digest(
            credentials.password.encode(), resolved_settings.api_key.encode()
        )
        if not valid_username or not valid_password:
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
        return normalized

    def base_url(request: Request) -> str:
        configured = resolved_settings.public_base_url
        return (configured or str(request.base_url)).rstrip("/")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/setup")
    async def setup(
        request: Request,
        device_id: str | None = Header(None, alias="ID"),
    ) -> dict[str, Any]:
        normalized = check_device(device_id)
        frame = await request.app.state.display.current_frame()
        return {
            "status": 200,
            "api_key": resolved_settings.api_key,
            "friendly_id": normalized.replace(":", "")[-6:],
            "image_url": f"{base_url(request)}/screen/{frame.filename}",
            "filename": frame.filename,
        }

    @app.get("/api/display")
    async def display(
        request: Request,
        device_id: str | None = Header(None, alias="ID"),
        access_token: str | None = Header(None, alias="Access-Token"),
    ) -> dict[str, Any]:
        authorize(device_id, access_token)
        frame = await request.app.state.display.current_frame()
        refresh_seconds = (
            max(300, resolved_settings.refresh_seconds) if frame.has_error else resolved_settings.refresh_seconds
        )
        return {
            "status": 0,
            "image_url": f"{base_url(request)}/screen/{frame.filename}",
            "filename": frame.filename,
            "refresh_rate": refresh_seconds,
            "reset_firmware": False,
            "update_firmware": False,
        }

    @app.get("/screen/latest.bmp")
    async def latest_screen(
        request: Request,
        credentials: Annotated[HTTPBasicCredentials | None, Depends(basic_auth)],
        device_id: str | None = Query(None),
    ) -> Response:
        authorize_basic(device_id, credentials)
        frame = await request.app.state.display.current_frame()
        return Response(
            content=frame.content,
            media_type="image/bmp",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/screen/{filename}")
    async def screen(request: Request, filename: str) -> Response:
        content = request.app.state.display.frame(filename)
        if content is None:
            raise HTTPException(status_code=404, detail="Frame expired")
        return Response(
            content=content,
            media_type="image/bmp",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @app.post("/api/log", status_code=204)
    async def device_log(
        payload: DeviceLog,
        device_id: str | None = Header(None, alias="ID"),
        access_token: str | None = Header(None, alias="Access-Token"),
    ) -> Response:
        normalized = authorize(device_id, access_token)
        log.info(
            "X3 %s firmware %s: %s",
            normalized,
            payload.fw_version or "unknown",
            payload.message,
        )
        return Response(status_code=204)

    return app


app = create_app()
