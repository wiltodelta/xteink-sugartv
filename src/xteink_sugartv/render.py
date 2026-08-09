from __future__ import annotations

import io
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PIL import Image, ImageDraw, ImageFont

from xteink_sugartv.config import Settings
from xteink_sugartv.models import GlucoseReading, Trend, Zone

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

WIDTH = 528
HEIGHT = 792

FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
)
PREDICTION_RANGES = {
    Trend.RISING_QUICKLY: ("rise_over", "45", "2,5"),
    Trend.RISING: ("rise_in", "30-45", "1,7-2,5"),
    Trend.RISING_SLIGHTLY: ("rise_in", "15-30", "0,8-1,7"),
    Trend.FALLING_SLIGHTLY: ("fall_in", "15-30", "0,8-1,7"),
    Trend.FALLING: ("fall_in", "30-45", "1,7-2,5"),
    Trend.FALLING_QUICKLY: ("fall_over", "45", "2,5"),
}
TREND_DIRECTIONS = {
    Trend.RISING_QUICKLY: (0.0, -1.0),
    Trend.RISING: (0.0, -1.0),
    Trend.RISING_SLIGHTLY: (0.72, -0.72),
    Trend.STEADY: (1.0, 0.0),
    Trend.FALLING_SLIGHTLY: (0.72, 0.72),
    Trend.FALLING: (0.0, 1.0),
    Trend.FALLING_QUICKLY: (0.0, 1.0),
}
DOUBLE_TRENDS = {Trend.RISING_QUICKLY, Trend.FALLING_QUICKLY}


@lru_cache(maxsize=1)
def _font_path() -> str:
    configured = os.getenv("XTEINK_FONT_PATH")
    candidates = (configured, *FONT_CANDIDATES) if configured else FONT_CANDIDATES
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError(
        "No suitable font found. Set XTEINK_FONT_PATH to a TrueType font such as Noto Sans or DejaVu Sans."
    )


@lru_cache(maxsize=32)
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(), size=size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return round(box[2] - box[0])


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int) -> ImageFont.FreeTypeFont:
    size = start_size
    while size > 18:
        font = _font(size)
        if _text_width(draw, text, font) <= max_width:
            return font
        size -= 2
    return _font(size)


def _fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    max_lines: int,
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    words = text.split()
    for size in range(start_size, 17, -2):
        font = _font(size)
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and _text_width(draw, candidate, font) > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) <= max_lines and all(_text_width(draw, line, font) <= max_width for line in lines):
            return font, lines
    return _font(18), [text]


def _is_russian(settings: Settings) -> bool:
    return settings.locale.lower().startswith("ru")


def _format_age(reading: GlucoseReading, now: datetime, russian: bool) -> str:
    age = reading.age_seconds(now)
    if age is None:
        return "00:00"
    minutes = round(age / 60)
    if minutes < 1:
        return "сейчас" if russian else "now"
    if minutes < 60:
        return f"{minutes} мин. назад" if russian else f"{minutes} min. ago"
    hours = round(minutes / 60)
    return f"{hours} ч. назад" if russian else f"{hours} hr. ago"


def _format_time(reading: GlucoseReading, now: datetime, settings: Settings) -> str:
    if settings.relative_time:
        return _format_age(reading, now, _is_russian(settings))
    if not reading.measured_at:
        return "00:00"
    return reading.measured_at.astimezone().strftime("%H:%M")


def _format_value(reading: GlucoseReading, russian: bool) -> str:
    if reading.value is None:
        return "Н/Д" if russian else "N/A"  # noqa: RUF001
    if reading.unit == "mmol/L":
        value = f"{reading.value:.1f}"
        return value.replace(".", ",") if russian else value
    return str(round(reading.value))


def _format_delta(reading: GlucoseReading, russian: bool) -> str | None:
    if reading.delta is None:
        return None
    if reading.unit == "mmol/L":
        absolute = f"{abs(reading.delta):.1f}"
        if russian:
            absolute = absolute.replace(".", ",")
    else:
        absolute = str(round(abs(reading.delta)))
    if reading.delta == 0:
        return absolute
    return f"{'+' if reading.delta > 0 else '−'}{absolute}"  # noqa: RUF001


def _prediction(reading: GlucoseReading, russian: bool) -> str:
    prediction = PREDICTION_RANGES.get(reading.trend)
    if not prediction:
        return ""
    key, mg, mmol_ru = prediction
    if reading.unit == "mmol/L":
        amount = mmol_ru if russian else mmol_ru.replace(",", ".")
        unit = "ммоль/л" if russian else "mmol/L"
    else:
        amount = mg
        unit = "мг/дл" if russian else "mg/dL"
    if russian:
        direction = "подъем" if key.startswith("rise") else "падение"
        qualifier = "более чем на " if key.endswith("over") else "на "
        return f"Ожидается {direction} {qualifier}{amount} {unit} в течение 15 минут"
    direction = "rise" if key.startswith("rise") else "fall"
    qualifier = "over " if key.endswith("over") else ""
    return f"Expected to {direction} {qualifier}{amount} {unit} in 15 minutes"


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    trend: Trend,
    center: tuple[int, int],
    *,
    ink: int,
) -> None:
    cx, cy = center
    if trend not in TREND_DIRECTIONS:
        draw.ellipse((cx - 38, cy - 38, cx + 38, cy + 38), outline=ink, width=7)
        draw.text((cx, cy - 4), "?", font=_font(54), fill=ink, anchor="mm")
        return

    dx, dy = TREND_DIRECTIONS[trend]
    double = trend in DOUBLE_TRENDS
    length = 83

    def line_arrow(offset: float = 0) -> None:
        normal = (-dy, dx)
        sx = cx - dx * length / 2 + normal[0] * offset
        sy = cy - dy * length / 2 + normal[1] * offset
        ex = cx + dx * length / 2 + normal[0] * offset
        ey = cy + dy * length / 2 + normal[1] * offset
        draw.line((sx, sy, ex, ey), fill=ink, width=12)
        head = 28
        left = (ex - dx * head + normal[0] * head, ey - dy * head + normal[1] * head)
        right = (ex - dx * head - normal[0] * head, ey - dy * head - normal[1] * head)
        draw.line((left, (ex, ey), right), fill=ink, width=12, joint="curve")

    if double:
        line_arrow(-24)
        line_arrow(24)
    else:
        line_arrow()


def _draw_progress_clock(draw: ImageDraw.ImageDraw, center: tuple[int, int], *, ink: int) -> None:
    cx, cy = center
    draw.arc((cx - 27, cy - 27, cx + 27, cy + 27), 35, 325, fill=ink, width=6)
    draw.line((cx, cy, cx, cy - 15), fill=ink, width=5)
    draw.line((cx, cy, cx + 12, cy + 8), fill=ink, width=5)


def render_frame(reading: GlucoseReading, now: datetime, settings: Settings | None = None) -> bytes:
    settings = settings or Settings()
    zone = reading.zone(settings.thresholds_for(reading.unit)) if settings.color_thresholds else None
    urgent = zone in {Zone.URGENT_LOW, Zone.URGENT_HIGH}
    background, ink = (0, 255) if urgent else (255, 0)
    image = Image.new("L", (WIDTH, HEIGHT), background)
    draw = ImageDraw.Draw(image)
    russian = _is_russian(settings)
    prediction = _prediction(reading, russian) if settings.show_prediction else ""
    vertical_offset = 0 if prediction else 80

    time_text = _format_time(reading, now, settings)
    draw.text(
        (WIDTH // 2, 86 + vertical_offset),
        time_text,
        font=_fit_font(draw, time_text, 470, 62),
        fill=ink,
        anchor="mm",
    )

    value_text = _format_value(reading, russian)
    value_font = _fit_font(draw, value_text, 490, 230)
    draw.text((WIDTH // 2, 300 + vertical_offset), value_text, font=value_font, fill=ink, anchor="mm")

    delta = _format_delta(reading, russian)
    _draw_arrow(draw, reading.trend, (190, 510 + vertical_offset), ink=ink)
    if delta:
        draw.text(
            (335, 510 + vertical_offset),
            delta,
            font=_fit_font(draw, delta, 170, 72),
            fill=ink,
            anchor="mm",
        )
    else:
        _draw_progress_clock(draw, (335, 510 + vertical_offset), ink=ink)

    if prediction:
        prediction_font, prediction_lines = _fit_wrapped_text(draw, prediction, 470, 30, 2)
        draw.multiline_text(
            (WIDTH // 2, 680),
            "\n".join(prediction_lines),
            font=prediction_font,
            fill=ink,
            anchor="mm",
            align="center",
            spacing=8,
        )

    # SugarTV uses orange text for low/high and a red field for urgent zones.
    # A one-bit panel preserves that hierarchy with an outline for warning and
    # full inversion for urgent readings.
    if zone in {Zone.LOW, Zone.HIGH}:
        draw.rectangle((5, 5, WIDTH - 6, HEIGHT - 6), outline=ink, width=5)

    tier = reading.age_tier(now)
    strength = 1.0
    if tier == "stale":
        strength = 0.7
    elif tier == "aging" and settings.dim_by_age:
        strength = 0.85
    return _to_bmp(image, ink_strength=strength)


def _to_bmp(image: Image.Image, *, ink_strength: float = 1.0) -> bytes:
    if ink_strength < 1:
        lut = [round(255 - (255 - value) * ink_strength) for value in range(256)]
        apply_lut = cast(
            "Callable[[Sequence[int]], Image.Image]",
            image.point,  # pyright: ignore[reportUnknownMemberType]
        )
        image = apply_lut(lut)
        converted = image.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        converted = image.convert("1", dither=Image.Dither.NONE)
    output = io.BytesIO()
    converted.save(output, format="BMP")
    return output.getvalue()
