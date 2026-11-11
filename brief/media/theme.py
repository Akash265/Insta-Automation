"""Load the visual identity (`video_templates/theme.yaml`)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml  # type: ignore[import-untyped]
from PIL import ImageFont

DEFAULT_THEME = Path("video_templates/theme.yaml")
RGBA = tuple[int, int, int, int]


class ThemeError(ValueError):
    pass


def _colour(value: str) -> RGBA:
    h = value.lstrip("#")
    if len(h) not in (6, 8):
        raise ThemeError(f"colour {value!r} must be #RRGGBB or #RRGGBBAA")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return (r, g, b, a)


@dataclass(frozen=True)
class SafeArea:
    left: int
    right: int
    top: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left


@dataclass(frozen=True)
class Theme:
    brand: str
    width: int
    height: int
    safe: SafeArea
    colours: dict[str, RGBA]
    fonts: dict[str, Path]
    subtitle_top: int
    subtitle_size: int
    subtitle_chars: int
    subtitle_lines: int

    def font(self, weight: str, size: int) -> ImageFont.FreeTypeFont:
        return _font(str(self.fonts[weight]), size)


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def load_theme(path: Path = DEFAULT_THEME) -> Theme:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ThemeError(f"cannot read {path}: {exc}") from exc
    fonts = {k: (path.parent / v) for k, v in raw["fonts"].items()}
    missing = [str(p) for p in fonts.values() if not p.exists()]
    if missing:
        raise ThemeError(f"font files missing: {', '.join(missing)}")
    s, sub = raw["safe_area"], raw["subtitles"]
    return Theme(
        brand=str(raw["brand"]),
        width=int(raw["canvas"]["width"]),
        height=int(raw["canvas"]["height"]),
        safe=SafeArea(int(s["left"]), int(s["right"]), int(s["top"]), int(s["bottom"])),
        colours={k: _colour(str(v)) for k, v in raw["colours"].items()},
        fonts=fonts,
        subtitle_top=int(sub["top"]),
        subtitle_size=int(sub["size"]),
        subtitle_chars=int(sub["max_chars_per_line"]),
        subtitle_lines=int(sub["max_lines"]),
    )
