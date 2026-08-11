from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^]]*]\(([^)]+)\)")


def test_local_markdown_links_resolve() -> None:
    documents = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
    missing: list[str] = []
    for document in documents:
        for target in MARKDOWN_LINK.findall(document.read_text()):
            if target.startswith(("http://", "https://", "#")):
                continue
            relative_target = target.split("#", 1)[0]
            if relative_target and not (document.parent / relative_target).exists():
                missing.append(f"{document.relative_to(ROOT)} -> {target}")
    assert not missing, "Missing local documentation targets:\n" + "\n".join(missing)


def test_firmware_screenshots_are_native_one_bit_images() -> None:
    expected_sizes = {
        "sugartv-display.png": (528, 792),
        "sugartv-update-failed.png": (528, 792),
        "sugartv-state-matrix.png": (1056, 1712),
    }
    for name, expected_size in expected_sizes.items():
        with Image.open(ROOT / "docs" / "images" / name) as image:
            assert image.size == expected_size
            assert image.mode == "1"
