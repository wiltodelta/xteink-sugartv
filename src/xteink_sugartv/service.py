from __future__ import annotations

import hashlib
from asyncio import to_thread
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from xteink_sugartv.models import utc_now
from xteink_sugartv.render import render_frame

if TYPE_CHECKING:
    from datetime import datetime

    from xteink_sugartv.config import Settings
    from xteink_sugartv.home_assistant import ReadingProvider


@dataclass(frozen=True, slots=True)
class Frame:
    filename: str
    content: bytes
    has_error: bool


class DisplayService:
    def __init__(self, provider: ReadingProvider, settings: Settings, *, cache_size: int = 8) -> None:
        self._provider = provider
        self._settings = settings
        self._cache_size = cache_size
        self._frames: OrderedDict[str, bytes] = OrderedDict()

    async def close(self) -> None:
        await self._provider.close()

    async def current_frame(self, now: datetime | None = None) -> Frame:
        reading = await self._provider.get_reading()
        content = await to_thread(render_frame, reading, now or utc_now(), self._settings)
        digest = hashlib.sha256(content).hexdigest()[:16]
        filename = f"sugartv-{digest}.bmp"
        self._frames[filename] = content
        self._frames.move_to_end(filename)
        while len(self._frames) > self._cache_size:
            self._frames.popitem(last=False)
        return Frame(filename=filename, content=content, has_error=reading.error is not None)

    def frame(self, filename: str) -> bytes | None:
        return self._frames.get(filename)
