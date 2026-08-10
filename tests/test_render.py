import struct
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw

from xteink_sugartv.config import Settings
from xteink_sugartv.models import GlucoseReading, Trend
from xteink_sugartv.render import (
    HEIGHT,
    WIDTH,
    _fit_wrapped_text,
    _font_path,
    _format_age,
    _prediction,
    _text_width,
    render_frame,
)


def reading(
    *,
    value: float | None = 112,
    age_minutes: int = 2,
    trend: Trend = Trend.STEADY,
) -> GlucoseReading:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    return GlucoseReading(
        value=value,
        unit="mg/dL",
        trend=trend,
        measured_at=now - timedelta(minutes=age_minutes) if value is not None else None,
        source_entity="sensor.jane_glucose_value",
        error="Unavailable" if value is None else None,
    )


def test_renders_x3_compatible_one_bit_bmp() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    content = render_frame(reading(), now)
    image = Image.open(BytesIO(content))
    assert image.size == (WIDTH, HEIGHT)
    assert image.mode == "1"
    assert content[:2] == b"BM"
    assert struct.unpack_from("<H", content, 28)[0] == 1
    assert "PIL" not in _font_path()


def test_error_frame_is_still_renderable() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    content = render_frame(reading(value=None), now)
    assert Image.open(BytesIO(content)).size == (WIDTH, HEIGHT)


def test_relative_age_changes_the_frame_cache_key_material() -> None:
    first = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    second = first + timedelta(minutes=1)
    settings = Settings(relative_time=True)
    assert render_frame(reading(), first, settings) != render_frame(reading(), second, settings)


def test_relative_age_matches_card_abbreviation_style() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

    assert _format_age(reading(age_minutes=14), now, russian=False) == "14 min ago"
    assert _format_age(reading(age_minutes=14), now, russian=True) == "14 мин назад"
    assert _format_age(reading(age_minutes=180), now, russian=False) == "3 hr ago"
    assert _format_age(reading(age_minutes=180), now, russian=True) == "3 ч назад"


def test_reading_without_prediction_is_vertically_centered() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    image = Image.open(BytesIO(render_frame(reading(), now))).convert("L")
    white = Image.new("L", image.size, 255)
    ink_bounds = ImageChops.difference(image, white).getbbox()

    assert ink_bounds is not None
    top_margin = ink_bounds[1]
    bottom_margin = HEIGHT - ink_bounds[3]
    assert abs(top_margin - bottom_margin) <= 30


def test_russian_prediction_fits_portrait_frame() -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    glucose = reading(trend=Trend.RISING_SLIGHTLY)
    prediction = _prediction(glucose, russian=True)
    draw = ImageDraw.Draw(Image.new("L", (WIDTH, HEIGHT)))
    font, lines = _fit_wrapped_text(draw, prediction, 470, 30, 2)

    assert len(lines) == 2
    assert all(_text_width(draw, line, font) <= 470 for line in lines)

    content = render_frame(
        glucose,
        now,
        Settings(locale="ru", show_prediction=True),
    )
    without_prediction = render_frame(
        glucose,
        now,
        Settings(locale="ru", show_prediction=False),
    )
    assert Image.open(BytesIO(content)).size == (528, 792)
    assert content != without_prediction
