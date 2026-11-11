"""Story cards for the Reel (P1-07, ADR-015): intro, one per story, outro. 1080x1920 PNG.

Layout (inside the Reels safe area, `video_templates/theme.yaml`):
- brand line, category chip, headline (auto-sized), key phrase (`card_text`),
  publisher and date, and a progress bar with "n/N";
- the band from `subtitles.top` to the safe-area bottom is left empty for subtitles.
Text that can't fit even at the smallest size raises `CardOverflowError`; it is never
cut off silently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from brief.edition.schema import Edition, Story
from brief.media.theme import Theme

IST = ZoneInfo("Asia/Kolkata")
CATEGORY_LABELS = {
    "model_release": "MODEL RELEASE",
    "research": "RESEARCH",
    "open_source": "OPEN SOURCE",
    "business": "BUSINESS",
    "policy": "POLICY",
}


class CardOverflowError(ValueError):
    """Text does not fit its box even at the smallest allowed size."""


@dataclass(frozen=True)
class Card:
    segment: int
    kind: str  # intro | story | outro
    path: Path


def wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= width:
            current = trial
            continue
        if not current or font.getlength(word) > width:
            raise CardOverflowError(f"word {word!r} is wider than the card")
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def fit(
    theme: Theme,
    text: str,
    weight: str,
    sizes: range,
    width: int,
    max_lines: int,
    max_height: int,
    spacing: float = 1.15,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """Largest size whose wrapped text fits; returns (font, lines, line_height)."""
    for size in sizes:
        font = theme.font(weight, size)
        try:
            lines = wrap(text, font, width)
        except CardOverflowError:
            continue
        line_h = round(size * spacing)
        if len(lines) <= max_lines and len(lines) * line_h <= max_height:
            return font, lines, line_h
    raise CardOverflowError(f"text does not fit ({len(text)} chars): {text[:60]!r}")


def _canvas(theme: Theme) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (theme.width, theme.height), theme.colours["background"][:3])
    return img, ImageDraw.Draw(img)


def _text_block(
    draw: ImageDraw.ImageDraw,
    theme: Theme,
    y: int,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    line_h: int,
    colour: str,
) -> int:
    for line in lines:
        draw.text((theme.safe.left, y), line, font=font, fill=theme.colours[colour])
        y += line_h
    return y


def _brand(draw: ImageDraw.ImageDraw, theme: Theme) -> None:
    draw.text(
        (theme.safe.left, theme.safe.top),
        theme.brand,
        font=theme.font("semibold", 34),
        fill=theme.colours["muted"],
    )


def _chip(draw: ImageDraw.ImageDraw, theme: Theme, label: str, y: int) -> int:
    font = theme.font("bold", 30)
    pad_x, pad_y = 20, 12
    w = round(font.getlength(label))
    box = (theme.safe.left, y, theme.safe.left + w + 2 * pad_x, y + 30 + 2 * pad_y + 6)
    draw.rounded_rectangle(box, radius=10, fill=theme.colours["accent"])
    draw.text((theme.safe.left + pad_x, y + pad_y), label, font=font, fill=theme.colours["text"])
    return box[3]


def _progress(draw: ImageDraw.ImageDraw, theme: Theme, n: int, total: int) -> None:
    y = theme.safe.bottom - 12
    left, right = theme.safe.left, theme.safe.right - 1  # rectangles include their right edge
    draw.rounded_rectangle((left, y, right, y + 8), radius=4, fill=theme.colours["track"])
    filled = left + round((right - left) * n / total)
    draw.rounded_rectangle((left, y, filled, y + 8), radius=4, fill=theme.colours["accent"])


def _footer(draw: ImageDraw.ImageDraw, theme: Theme, left_text: str, right_text: str) -> None:
    font = theme.font("semibold", 32)
    y = theme.subtitle_top - 70
    draw.text((theme.safe.left, y), left_text, font=font, fill=theme.colours["muted"])
    if right_text:
        w = font.getlength(right_text)
        draw.text((theme.safe.right - w, y), right_text, font=font, fill=theme.colours["muted"])


def _story_date(story: Story) -> str:
    moment = story.published_at or story.event_at
    return moment.astimezone(IST).strftime("%-d %b %Y") if moment else ""


def story_card(theme: Theme, story: Story, n: int, total: int) -> Image.Image:
    img, draw = _canvas(theme)
    _brand(draw, theme)
    y = _chip(draw, theme, CATEGORY_LABELS.get(str(story.category), str(story.category)), 320)
    top = y + 60
    footer_top = theme.subtitle_top - 90
    font, lines, lh = fit(theme, story.headline, "bold", range(84, 51, -4),
                          theme.safe.width, 6, 560)  # fmt: skip
    y = _text_block(draw, theme, top, lines, font, lh, "text")
    if story.card_text:
        kf, kl, klh = fit(theme, story.card_text, "regular", range(46, 33, -2),
                          theme.safe.width, 3, footer_top - y - 40)  # fmt: skip
        _text_block(draw, theme, y + 40, kl, kf, klh, "muted")
    meta = " · ".join(p for p in (story.publisher, _story_date(story)) if p)
    if theme.font("semibold", 32).getlength(meta) > theme.safe.width - 120:
        meta = story.publisher
    _footer(draw, theme, meta, f"{n}/{total}")
    _progress(draw, theme, n, total)
    return img


def intro_card(theme: Theme, edition: Edition) -> Image.Image:
    img, draw = _canvas(theme)
    _brand(draw, theme)
    day = date.fromisoformat(str(edition.issue_date))
    draw.text((theme.safe.left, 330), day.strftime("%A, %-d %B %Y"),
              font=theme.font("semibold", 44), fill=theme.colours["accent"])  # fmt: skip
    hook = edition.script.hook if edition.script else ""
    font, lines, lh = fit(theme, hook, "bold", range(80, 47, -4), theme.safe.width, 7, 640)
    _text_block(draw, theme, 460, lines, font, lh, "text")
    count = len(edition.stories)
    _footer(draw, theme, f"{count} {'story' if count == 1 else 'stories'} · sources linked", "")
    return img


def outro_card(theme: Theme, edition: Edition) -> Image.Image:
    img, draw = _canvas(theme)
    _brand(draw, theme)
    outro = edition.script.outro if edition.script else ""
    font, lines, lh = fit(theme, outro, "bold", range(76, 43, -4), theme.safe.width, 6, 560)
    y = _text_block(draw, theme, 460, lines, font, lh, "text")
    note = "Every story links to its original source."
    nf, nl, nlh = fit(theme, note, "regular", range(42, 31, -2), theme.safe.width, 3, 200)
    _text_block(draw, theme, y + 40, nl, nf, nlh, "muted")
    _footer(draw, theme, "Corrections are always published.", "")
    return img


def render_cards(theme: Theme, edition: Edition, out_dir: Path) -> list[Card]:
    """Segment-ordered cards matching `edition_segments`: intro, stories by rank, outro."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stories = sorted(edition.stories, key=lambda s: s.rank)
    images: list[tuple[str, Image.Image]] = [("intro", intro_card(theme, edition))]
    images += [("story", story_card(theme, s, n, len(stories))) for n, s in enumerate(stories, 1)]
    images.append(("outro", outro_card(theme, edition)))
    cards = []
    for segment, (kind, img) in enumerate(images):
        path = out_dir / f"card-{segment:02d}-{kind}.png"
        img.save(path, format="PNG", optimize=False)
        cards.append(Card(segment, kind, path))
    return cards
