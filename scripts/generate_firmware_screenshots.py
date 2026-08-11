#!/usr/bin/env python3
"""Generate documentation screenshots with the patched CrossPoint renderer."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIRECTORY = PROJECT_ROOT / "docs" / "images"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("crosspoint", type=Path, help="Patched CrossPoint checkout")
    return parser.parse_args()


def render(crosspoint: Path, output: str, *arguments: str) -> None:
    renderer = crosspoint / "tools" / "render_sugartv_preview.py"
    font = crosspoint / "lib" / "EpdFont" / "builtinFonts" / "source" / "NotoSans" / "NotoSans-Regular.ttf"
    if not renderer.is_file() or not font.is_file():
        raise FileNotFoundError("CrossPoint is not patched with the SugarTV renderer")
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(renderer),
            "--font",
            str(font),
            "--output",
            str(OUTPUT_DIRECTORY / output),
            *arguments,
        ],
        cwd=crosspoint,
        check=True,
    )


def main() -> None:
    args = parse_args()
    crosspoint = args.crosspoint.resolve()
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    render(
        crosspoint,
        "sugartv-display.png",
        "--time",
        "now",
        "--value",
        "116",
        "--delta",
        "+1",
        "--battery",
        "87%",
        "--status-time",
        "Aug 10, 5:54 PM",
        "--trend",
        "steady",
        "--zone",
        "target",
        "--no-color-thresholds",
    )
    render(
        crosspoint,
        "sugartv-update-failed.png",
        "--time",
        "3 min ago",
        "--value",
        "116",
        "--delta",
        "+1",
        "--battery",
        "86%",
        "--status-time",
        "Aug 10, 5:57 PM",
        "--trend",
        "steady",
        "--zone",
        "target",
        "--no-color-thresholds",
        "--update-failed",
    )
    render(crosspoint, "sugartv-state-matrix.png", "--matrix")
    log.info("Generated firmware screenshots in %s", OUTPUT_DIRECTORY)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
