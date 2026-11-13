"""P1-11: `brief site build` from edition records."""

from __future__ import annotations

import copy
import dataclasses
import json
import xml.etree.ElementTree as ET  # parses our own build output only
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import html5lib
import pytest
from typer.testing import CliRunner

from brief.cli import app
from brief.site.build import (
    POLICY_PAGES,
    SiteBuildError,
    SiteConfig,
    build_site,
    load_site_config,
)
from tests.conftest import FIXTURES, ROOT

TEMPLATES = ROOT / "site_templates"
CFG = load_site_config(ROOT / "config" / "site.yaml")
NORMAL = json.loads((FIXTURES / "normal.json").read_text(encoding="utf-8"))
QUIET = json.loads((FIXTURES / "quiet_day.json").read_text(encoding="utf-8"))
PUBLIC = dataclasses.replace(  # the soft-launch build: every policy page approved
    CFG, noindex=False, contact_email="editor@example.com",
    policy_approved=dict.fromkeys(POLICY_PAGES, "2026-12-01"),
)  # fmt: skip


def write_editions(folder: Path, *editions: dict[str, Any]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for e in editions:
        (folder / f"{e['issue_date']}.json").write_text(json.dumps(e), encoding="utf-8")
    return folder


def dated(base: dict[str, Any], day: str, **changes: Any) -> dict[str, Any]:
    e = copy.deepcopy(base)
    e["issue_date"], e["issue_key"] = day, f"ADB-{day}"
    e["issue_url"] = f"{CFG.base_url}/issues/{day}/"
    e.update(changes)
    return e


def build(tmp: Path, *editions: dict[str, Any], preview: bool = False,
          cfg: SiteConfig = CFG) -> Path:  # fmt: skip
    eds = write_editions(tmp / "editions", *editions)
    build_site(eds, tmp / "dist", cfg, TEMPLATES, preview)
    return tmp / "dist"


def parse_xml(path: Path) -> ET.ElementTree[ET.Element]:
    return ET.parse(path)  # noqa: S314 - our own build output


def read(dist: Path, rel: str) -> str:
    return (dist / rel).read_text(encoding="utf-8")


class Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), ""

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, self._text.strip()))
            self._href = None


def test_build_creates_every_listed_path(tmp_path: Path) -> None:
    dist = build(tmp_path, NORMAL, QUIET)
    expected = [
        "index.html", "today/index.html", "archive/index.html", "corrections/index.html",
        "issues/2026-11-20/index.html", "issues/2026-11-23/index.html", "404.html",
        "sitemap.xml", "feed.xml", "search-index.json", "robots.txt", "_headers", "_redirects",
    ] + [f"{slug}/index.html" for slug in POLICY_PAGES]  # fmt: skip
    for rel in expected:
        assert (dist / rel).is_file(), rel
    assert read(dist, "_redirects") == (
        "/today /issues/2026-11-23/ 302\n/today/ /issues/2026-11-23/ 302\n"
    )
    assert 'url=/issues/2026-11-23/"' in read(dist, "today/index.html")


def test_every_story_shows_publisher_dates_and_read_original(tmp_path: Path) -> None:
    dist = build(tmp_path, NORMAL, QUIET)
    for edition in (NORMAL, QUIET):
        page = read(dist, f"issues/{edition['issue_date']}/index.html")
        parser = Links()
        parser.feed(page)
        for story in edition["stories"]:
            block = page.split(f'id="story-{story["rank"]}"', 1)[1].split("</li>", 1)[0]
            assert story["publisher"] in block
            assert "Published " in block or "Publication date not stated" in block
            assert any(
                href == story["primary_source_url"] and text.startswith("Read original")
                for href, text in parser.links
            ), story["story_id"]
    weekend = read(dist, "issues/2026-11-23/index.html")
    assert "Event Sat 21 Nov 2026" in weekend  # event shown separately from publication


def test_all_html_is_valid(tmp_path: Path) -> None:
    dist = build(tmp_path, NORMAL, QUIET, preview=True)
    pages = sorted(dist.rglob("*.html"))
    assert len(pages) >= 12
    for page in pages:
        html5lib.HTMLParser(strict=True).parse(page.read_text(encoding="utf-8"))
        text = page.read_text(encoding="utf-8")
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in text


def test_feeds_and_index_are_well_formed(tmp_path: Path) -> None:
    dist = build(tmp_path, NORMAL, QUIET)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in parse_xml(dist / "sitemap.xml").findall(".//s:loc", ns)]
    assert f"{CFG.base_url}/issues/2026-11-20/" in locs and f"{CFG.base_url}/today/" not in locs
    items = parse_xml(dist / "feed.xml").findall("./channel/item")
    assert [i.findtext("link") for i in items] == [
        f"{CFG.base_url}/issues/2026-11-23/",
        f"{CFG.base_url}/issues/2026-11-20/",
    ]
    index = json.loads(read(dist, "search-index.json"))
    assert [i["date"] for i in index["issues"]] == ["2026-11-23", "2026-11-20"]
    assert len(index["issues"][1]["stories"]) == 5
    assert len(read(dist, "search-index.json")) < 2500 * len(index["issues"])  # ~2 KB per issue


def test_build_is_deterministic(tmp_path: Path) -> None:
    a = build(tmp_path / "a", NORMAL, QUIET)
    b = build(tmp_path / "b", NORMAL, QUIET)
    files = sorted(p.relative_to(a) for p in a.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(b) for p in b.rglob("*") if p.is_file())
    for rel in files:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_noindex_during_the_experiment(tmp_path: Path) -> None:
    dist = build(tmp_path, NORMAL)
    assert CFG.noindex
    assert all('content="noindex, nofollow"' in p.read_text(encoding="utf-8")
               for p in dist.rglob("*.html"))  # fmt: skip
    assert "Disallow: /" in read(dist, "robots.txt")
    assert "X-Robots-Tag: noindex" in read(dist, "_headers")
    dist = build(tmp_path / "public", NORMAL, cfg=PUBLIC)
    assert "noindex" not in read(dist, "issues/2026-11-20/index.html")
    assert "Sitemap:" in read(dist, "robots.txt")
    assert "X-Robots-Tag" not in read(dist, "_headers")


def test_policy_pages_are_drafts_until_approved(tmp_path: Path) -> None:
    assert not CFG.policy_approved and CFG.contact_email is None  # nothing approved yet
    dist = build(tmp_path, NORMAL)
    for slug in POLICY_PAGES:
        page = read(dist, f"{slug}/index.html")
        assert "Draft page" in page
        assert f'href="/{slug}/"' in read(dist, "index.html")  # linked from the footer
    assert "mailto:" not in read(dist, "contact/index.html")
    approved = build(tmp_path / "approved", NORMAL, cfg=PUBLIC)
    assert not any("Draft page" in read(approved, f"{s}/index.html") for s in POLICY_PAGES)
    assert 'href="mailto:editor@example.com"' in read(approved, "contact/index.html")


@pytest.mark.parametrize(
    "change",
    [{"policy_approved": {}}, {"contact_email": None},
     {"policy_approved": dict.fromkeys(list(POLICY_PAGES)[:-1], "2026-12-01")}],
)  # fmt: skip
def test_indexable_build_needs_approved_policies(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(SiteBuildError, match="P1-20U"):
        build(tmp_path, NORMAL, cfg=dataclasses.replace(PUBLIC, **change))
    # a preview build is always noindex, so drafts are fine there
    build(tmp_path / "preview", NORMAL, cfg=dataclasses.replace(PUBLIC, **change), preview=True)


def test_policy_settings_are_validated(tmp_path: Path) -> None:
    text = (ROOT / "config" / "site.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "site.yaml"
    bad.write_text(text.replace("  privacy: null", "  privacy: soon"), encoding="utf-8")
    with pytest.raises(SiteBuildError, match="approval date"):
        load_site_config(bad)
    bad.write_text(text.replace("  privacy: null", "  pricing: 2026-12-01"), encoding="utf-8")
    with pytest.raises(SiteBuildError, match="unknown policy pages"):
        load_site_config(bad)
    bad.write_text(text.replace("contact_email: null", "contact_email: nobody"), encoding="utf-8")
    with pytest.raises(SiteBuildError, match="not an email"):
        load_site_config(bad)


def test_which_editions_are_built(tmp_path: Path) -> None:
    review = copy.deepcopy(QUIET)
    review["status"] = "in_review"
    review["review"]["decision"] = "pending"
    draft = dated(NORMAL, "2026-11-25", status="draft")
    eds = write_editions(tmp_path / "editions", NORMAL, review, draft)
    (eds / "_template.json").write_text("{}", encoding="utf-8")  # ignored
    prod = build_site(eds, tmp_path / "prod", CFG, TEMPLATES)
    assert prod.issues == ["2026-11-20"] and prod.latest == "2026-11-20"
    assert {name for name, _ in prod.skipped} == {"2026-11-23.json", "2026-11-25.json"}
    prev = build_site(eds, tmp_path / "prev", CFG, TEMPLATES, preview=True)
    assert prev.issues == ["2026-11-23", "2026-11-20"]
    page = read(tmp_path / "prev", "issues/2026-11-23/index.html")
    assert "Preview build" in page and 'content="noindex, nofollow"' in page


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda e: e["review"].update(decision="pending"), "review decision"),
        (lambda e: e.update(issue_url="https://elsewhere.example/x/"), "issue_url"),
        (lambda e: e["stories"][0].pop("headline"), "headline"),
        (lambda e: e["stories"][0]["claims"][0].update(evidence=[]), "blocking checks"),
    ],
)
def test_broken_editions_stop_the_build(tmp_path: Path, change: Any, message: str) -> None:
    bad = copy.deepcopy(NORMAL)
    change(bad)
    with pytest.raises(SiteBuildError, match=message):
        build(tmp_path, bad)
    assert not (tmp_path / "dist").exists()


def test_never_replaces_a_folder_it_did_not_build(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "keep.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(SiteBuildError, match="not made by"):
        build(tmp_path, NORMAL)
    assert (tmp_path / "dist" / "keep.txt").exists()


def test_corrections_are_shown_by_severity(tmp_path: Path) -> None:
    e = copy.deepcopy(NORMAL)

    def corr(severity: str, rank: int | None, note: str) -> dict[str, Any]:
        return {"severity": severity, "story_rank": rank, "original_text": "old " + note,
                "corrected_text": "new " + note, "reason": "reason " + note,
                "public_note": note, "approved_by": "Founder",
                "corrected_at": "2026-11-21T06:00:00+00:00"}  # fmt: skip

    e["corrections"] = [corr("critical", 1, "CRIT-NOTE"), corr("material", 2, "MAT-NOTE"),
                        corr("minor", 3, "MINOR-NOTE")]  # fmt: skip
    dist = build(tmp_path, e)
    page = read(dist, "issues/2026-11-20/index.html")
    assert page.index("CRIT-NOTE") < page.index('id="story-1"')
    story2 = page.split('id="story-2"', 1)[1].split("</li>", 1)[0]
    assert "MAT-NOTE" in story2
    assert "MINOR-NOTE" not in page
    listing = read(dist, "corrections/index.html")
    assert "CRIT-NOTE" in listing and "MAT-NOTE" in listing and "MINOR-NOTE" not in listing
    assert "2026-11-21" in read(dist, "sitemap.xml")  # lastmod follows the correction


def test_text_is_escaped_including_json_ld(tmp_path: Path) -> None:
    e = copy.deepcopy(NORMAL)
    e["stories"][0]["headline"] = 'Nimbus </script><script>alert("x")</script> & co'
    dist = build(tmp_path, e)
    page = read(dist, "issues/2026-11-20/index.html")
    assert "<script>alert" not in page
    ld = page.split('<script type="application/ld+json">', 1)[1].split("</script>", 1)[0]
    data = json.loads(ld)
    assert data["hasPart"][0]["headline"].startswith("Nimbus </script>")


def test_cli_site_build(tmp_path: Path) -> None:
    eds = write_editions(tmp_path / "editions", NORMAL, QUIET)
    args = ["site", "build", "--editions", str(eds), "--out", str(tmp_path / "dist"),
            "--config", str(ROOT / "config/site.yaml"), "--templates", str(TEMPLATES)]  # fmt: skip
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "built 2 issue(s)" in result.output and "/today -> /issues/2026-11-23/" in result.output
    bad = copy.deepcopy(NORMAL)
    bad["review"]["decision"] = "pending"
    write_editions(eds, bad)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1 and "review decision" in result.output
