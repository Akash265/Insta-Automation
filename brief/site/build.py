"""`brief site build`: edition records -> static site in `dist/` (P1-11, ADR-006).

Output (all paths end in `/` and are served as `<path>/index.html`):
- `/` home (latest issue and recent issues), `/issues/YYYY-MM-DD/`, `/today/`
  (meta refresh + canonical; `_redirects` sends a 302 to the newest issue),
  `/archive/` (every issue; filter by text, category and publisher in vanilla JS),
  `/corrections/`, policy page stubs (`POLICY_PAGES`, completed in P1-20), `404.html`;
- `sitemap.xml`, `feed.xml` (RSS 2.0 of issues), `search-index.json`, `robots.txt`,
  and the Cloudflare Pages `_headers` and `_redirects` files.

Which editions are built:
- `approved` and `published` editions whose review decision is `approved`;
- with `--preview`, also `in_review` editions (marked as previews; ADR-012);
- never `draft` or `skipped`. A file that fails the schema, fails a blocking `draft`-stage
  check, or whose `issue_url` doesn't match the site URL stops the build: a broken
  edition is never published silently.

The build is deterministic: the same editions and templates give byte-identical output.
Nothing depends on the clock. During the private experiment (`noindex: true` in
`config/site.yaml`) every page is noindex, robots.txt disallows crawling and Pages sends
`X-Robots-Tag: noindex`; preview builds are always noindex.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml  # type: ignore[import-untyped]
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup

from brief.edition.checks import load_edition, validate_edition
from brief.edition.schema import Correction, Edition, EventAtBasis, Story

IST = ZoneInfo("Asia/Kolkata")
PUBLISH_TIME = time(20, 0)  # ADR-005: issues go live at 20:00 IST
EDITION_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.json$")
MARKER = ".brief-site"  # only a folder carrying this marker is ever replaced
FEED_ITEMS = 30
HOME_RECENT = 7
CATEGORY_LABELS = {
    "model_release": "Model release",
    "research": "Research",
    "open_source": "Open source",
    "business": "Business",
    "policy": "Policy",
}
POLICY_PAGES = {  # slug -> title; templates in site_templates/pages/
    "about": "About",
    "editorial-standards": "Editorial standards",
    "corrections-policy": "Corrections policy",
    "privacy": "Privacy",
    "contact": "Contact",
}


class SiteBuildError(ValueError):
    """An edition or setting that must not be published as it is."""


@dataclass(frozen=True)
class SiteConfig:
    base_url: str
    site_name: str
    description: str
    language: str
    noindex: bool
    contact_email: str | None = None
    # slug -> founder approval date (P1-20U); a page without one is a draft
    policy_approved: dict[str, str] = field(default_factory=dict)


@dataclass
class BuildResult:
    out: Path
    issues: list[str]
    latest: str | None
    preview: bool
    skipped: list[tuple[str, str]] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


def load_site_config(path: Path) -> SiteConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        cfg = SiteConfig(
            base_url=str(data["base_url"]).rstrip("/"),
            site_name=str(data["site_name"]),
            description=str(data["description"]),
            language=str(data.get("language", "en")),
            noindex=bool(data["noindex"]),
            contact_email=str(data["contact_email"]) if data.get("contact_email") else None,
            policy_approved={
                str(k): str(v) for k, v in (data.get("policy_pages") or {}).items() if v
            },
        )
    except KeyError as exc:
        raise SiteBuildError(f"{path}: missing setting {exc}") from exc
    unknown = sorted(set(cfg.policy_approved) - set(POLICY_PAGES))
    if unknown:
        raise SiteBuildError(f"{path}: unknown policy pages {unknown}")
    for slug, day in cfg.policy_approved.items():
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise SiteBuildError(f"{path}: policy_pages.{slug} must be an approval date")
    if cfg.contact_email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", cfg.contact_email):
        raise SiteBuildError(f"{path}: contact_email is not an email address")
    if not re.fullmatch(r"https://[a-z0-9.-]+(:\d+)?(/[\w./-]*)?", cfg.base_url):
        raise SiteBuildError(f"{path}: base_url must be an https:// URL: {cfg.base_url!r}")
    return cfg


# ------------------------------------------------------------------ editions


def issue_path(day: date) -> str:
    return f"/issues/{day.isoformat()}/"


def collect_editions(
    editions_dir: Path, cfg: SiteConfig, preview: bool
) -> tuple[list[Edition], list[tuple[str, str]]]:
    """Editions to publish, newest first, and (file, reason) for those left out."""
    included: list[Edition] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(editions_dir.glob("*.json")):
        m = EDITION_FILE_RE.match(path.name)
        if not m:
            continue  # _template.json and other non-edition files
        edition, issues = load_edition(path)
        if edition is None:
            raise SiteBuildError(f"{path.name}: " + "; ".join(i.message for i in issues))
        if edition.issue_date.isoformat() != m.group(1):
            raise SiteBuildError(f"{path.name}: issue_date {edition.issue_date} != file name")
        if edition.status in ("draft", "skipped"):
            skipped.append((path.name, f"status {edition.status}"))
            continue
        if edition.status == "in_review" and not preview:
            skipped.append((path.name, "in review (preview builds only)"))
            continue
        decision = edition.review.decision if edition.review else "missing"
        if edition.status in ("approved", "published") and decision != "approved":
            raise SiteBuildError(
                f"{path.name}: status {edition.status} but review decision is {decision}"
            )
        blocking = validate_edition(edition, "draft").blocking
        if blocking:
            msgs = "; ".join(f"{i.code} {i.message}" for i in blocking)
            raise SiteBuildError(f"{path.name}: blocking checks fail: {msgs}")
        expected = cfg.base_url + issue_path(edition.issue_date)
        if edition.issue_url is not None and edition.issue_url != expected:
            raise SiteBuildError(
                f"{path.name}: issue_url {edition.issue_url} != site URL {expected} "
                "(fix base_url in config/site.yaml or the edition)"
            )
        included.append(edition)
    included.sort(key=lambda e: e.issue_date, reverse=True)
    return included, skipped


# ------------------------------------------------------------------ formatting


def ist(moment: datetime) -> datetime:
    return moment.astimezone(IST)


def fmt_day(day: date) -> str:
    return day.strftime("%A, %-d %B %Y")


def fmt_moment(moment: datetime) -> str:
    return ist(moment).strftime("%-d %b %Y, %H:%M IST")


def issue_moment(edition: Edition) -> datetime:
    """When the issue went (or goes) live: the recorded publication time, else 20:00 IST."""
    if edition.publication and edition.publication.published_at:
        return edition.publication.published_at
    return datetime.combine(edition.issue_date, PUBLISH_TIME, IST)


def story_dates(story: Story) -> list[str]:
    """Publication and event dates, always shown separately (EDITORIAL_PIPELINE §4)."""
    parts = [
        f"Published {fmt_moment(story.published_at)}"
        if story.published_at
        else "Publication date not stated"
    ]
    if story.event_at and story.event_at_basis is not EventAtBasis.SAME_AS_PUBLISHED:
        basis = " (inferred)" if story.event_at_basis is EventAtBasis.INFERRED else ""
        parts.append(f"Event {ist(story.event_at).strftime('%a %-d %b %Y')}{basis}")
    elif story.event_at is None:
        parts.append("Event date unknown")
    return parts


def domain(url: str) -> str:
    host = url.split("://", 1)[-1].split("/", 1)[0]
    return host.removeprefix("www.")


def correction_note(c: Correction) -> dict[str, str]:
    return {
        "when": fmt_moment(c.corrected_at),
        "at": ist(c.corrected_at).isoformat(),
        "severity": c.severity,
        "text": c.public_note or c.reason,
    }


def json_ld(data: dict[str, Any]) -> Markup:
    """JSON for a <script type="application/ld+json"> block, safe against `</script>`."""
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=1)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(text)  # noqa: S704 - escaped above; data block, never executed


# ------------------------------------------------------------------ page models


def story_view(story: Story, edition: Edition) -> dict[str, Any]:
    notes = [
        correction_note(c)
        for c in edition.corrections
        if c.severity == "material" and c.story_rank == story.rank
    ]
    return {
        "rank": story.rank,
        "anchor": f"story-{story.rank}",
        "category": CATEGORY_LABELS.get(str(story.category), str(story.category)),
        "headline": story.headline,
        "summary": story.summary,
        "why_it_matters": story.why_it_matters,
        "technical_notes": story.technical_notes,
        "limitations": story.limitations,
        "publisher": story.publisher,
        "dates": story_dates(story),
        "url": story.primary_source_url,
        "supporting": [{"url": u, "domain": domain(u)} for u in story.supporting_source_urls],
        "sponsored": story.sponsored,
        "disclosure": story.disclosure,
        "corrections": notes,
    }


def issue_ld(edition: Edition, cfg: SiteConfig, url: str) -> Markup:
    org = {"@type": "Organization", "name": cfg.site_name, "url": cfg.base_url + "/"}
    published = issue_moment(edition).isoformat()
    articles = [
        {
            "@type": "NewsArticle",
            "headline": s.headline,
            "description": s.summary,
            "url": f"{url}#story-{s.rank}",
            "datePublished": published,
            "isBasedOn": s.primary_source_url,
            "publisher": org,
            "inLanguage": cfg.language,
        }
        for s in sorted(edition.stories, key=lambda s: s.rank)
    ]
    return json_ld(
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": issue_title(edition, cfg),
            "url": url,
            "datePublished": published,
            "publisher": org,
            "hasPart": articles,
        }
    )


def issue_title(edition: Edition, cfg: SiteConfig) -> str:
    if edition.seo:
        return edition.seo.title
    return f"{cfg.site_name}, {edition.issue_date.strftime('%-d %B %Y')}"


def issue_description(edition: Edition) -> str:
    if edition.seo:
        return edition.seo.description
    return edition.daily_thesis or "; ".join(s.headline for s in edition.stories)[:160]


def issue_summary(edition: Edition, cfg: SiteConfig) -> dict[str, Any]:
    """The small record used on the home page, archive and search index."""
    return {
        "date": edition.issue_date.isoformat(),
        "day": fmt_day(edition.issue_date),
        "url": issue_path(edition.issue_date),
        "title": issue_title(edition, cfg),
        "thesis": edition.daily_thesis or "",
        "quiet_day": edition.is_quiet_day,
        "preview": edition.status == "in_review",
        "stories": [
            {
                "rank": s.rank,
                "headline": s.headline,
                "category": CATEGORY_LABELS.get(str(s.category), str(s.category)),
                "publisher": s.publisher,
                "source": s.primary_source_url,
            }
            for s in sorted(edition.stories, key=lambda s: s.rank)
        ],
    }


# ------------------------------------------------------------------ writers


class _Writer:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files: list[str] = []

    def write(self, rel: str, content: str | bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            content = content.encode("utf-8")
        path.write_bytes(content)
        self.files.append(rel)

    def page(self, url_path: str, html: str) -> None:
        rel = url_path.strip("/")
        self.write(f"{rel}/index.html" if rel else "index.html", html)


def _xml(root: ET.Element) -> str:
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, "unicode") + "\n"


def sitemap_xml(cfg: SiteConfig, entries: list[tuple[str, date | None]]) -> str:
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset", xmlns=ns)
    for path, lastmod in entries:
        u = ET.SubElement(urlset, "url")
        ET.SubElement(u, "loc").text = cfg.base_url + path
        if lastmod:
            ET.SubElement(u, "lastmod").text = lastmod.isoformat()
    return _xml(urlset)


def feed_xml(cfg: SiteConfig, editions: list[Edition]) -> str:
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = cfg.site_name
    ET.SubElement(ch, "link").text = cfg.base_url + "/"
    ET.SubElement(ch, "description").text = cfg.description
    ET.SubElement(ch, "language").text = cfg.language
    ET.SubElement(
        ch, "atom:link", href=cfg.base_url + "/feed.xml", rel="self", type="application/rss+xml"
    )
    if editions:
        ET.SubElement(ch, "lastBuildDate").text = format_datetime(
            issue_moment(editions[0]).astimezone(UTC)
        )
    for e in editions[:FEED_ITEMS]:
        item = ET.SubElement(ch, "item")
        url = cfg.base_url + issue_path(e.issue_date)
        ET.SubElement(item, "title").text = issue_title(e, cfg)
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url
        ET.SubElement(item, "pubDate").text = format_datetime(issue_moment(e).astimezone(UTC))
        ET.SubElement(item, "description").text = issue_description(e)
    return _xml(rss)


def headers_file(noindex: bool) -> str:
    lines = [
        "/*",
        "  X-Content-Type-Options: nosniff",
        "  Referrer-Policy: strict-origin-when-cross-origin",
        "  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; form-action 'none'; "
        "frame-ancestors 'none'",
    ]
    if noindex:
        lines.append("  X-Robots-Tag: noindex")
    return "\n".join(lines) + "\n"


def robots_txt(cfg: SiteConfig, noindex: bool) -> str:
    if noindex:
        return "User-agent: *\nDisallow: /\n"
    return f"User-agent: *\nAllow: /\n\nSitemap: {cfg.base_url}/sitemap.xml\n"


# ------------------------------------------------------------------ build


def _environment(templates: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(templates),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def _static(templates: Path, writer: _Writer) -> dict[str, str]:
    """Copy static files with a content hash in the name (cache busting, deterministic)."""
    urls: dict[str, str] = {}
    for src in sorted((templates / "static").iterdir()):
        data = src.read_bytes()
        digest = hashlib.sha256(data).hexdigest()[:10]
        rel = f"static/{src.stem}.{digest}{src.suffix}"
        writer.write(rel, data)
        urls[src.name] = "/" + rel
    return urls


def build_site(
    editions_dir: Path,
    out: Path,
    cfg: SiteConfig,
    templates: Path,
    preview: bool = False,
) -> BuildResult:
    editions, skipped = collect_editions(editions_dir, cfg, preview)
    if out.exists() and not (out / MARKER).exists():
        raise SiteBuildError(f"{out} exists and was not made by `brief site build`; not touching")
    staging = out.with_name(out.name + ".building")
    if staging.exists():
        shutil.rmtree(staging)
    writer = _Writer(staging)
    noindex = cfg.noindex or preview
    if not noindex:  # the public (indexable) soft-launch build, after gate G4
        drafts = [slug for slug in POLICY_PAGES if slug not in cfg.policy_approved]
        if drafts or not cfg.contact_email:
            raise SiteBuildError(
                "an indexable build needs every policy page approved and contact_email set "
                f"in config/site.yaml (P1-20U); drafts: {drafts or 'none'}, "
                f"contact_email: {'set' if cfg.contact_email else 'missing'}"
            )
    env = _environment(templates)
    static = _static(templates, writer)
    policy_links = [{"url": f"/{slug}/", "title": t} for slug, t in POLICY_PAGES.items()]
    summaries = [issue_summary(e, cfg) for e in editions]
    latest = summaries[0] if summaries else None

    def render(template: str, path: str, **ctx: Any) -> str:
        return env.get_template(template).render(
            site=cfg,
            noindex=noindex,
            preview_build=preview,
            static=static,
            policy_links=policy_links,
            canonical=cfg.base_url + path,
            path=path,
            **ctx,
        )

    for e in editions:
        path = issue_path(e.issue_date)
        stories = [story_view(s, e) for s in sorted(e.stories, key=lambda s: s.rank)]
        top_notes = [correction_note(c) for c in e.corrections if c.severity == "critical"]
        unplaced = [  # material corrections not tied to a story still appear at the top
            correction_note(c)
            for c in e.corrections
            if c.severity == "material" and c.story_rank not in {s.rank for s in e.stories}
        ]
        writer.page(
            path,
            render(
                "issue.html",
                path,
                title=issue_title(e, cfg),
                description=issue_description(e),
                issue=issue_summary(e, cfg),
                stories=stories,
                top_corrections=top_notes + unplaced,
                ld=issue_ld(e, cfg, cfg.base_url + path),
            ),
        )

    writer.page("/", render("home.html", "/", title=cfg.site_name,
                            description=cfg.description, latest=latest,
                            recent=summaries[1:HOME_RECENT]))  # fmt: skip
    if latest:
        writer.page("/today/", render("today.html", "/today/", title="Today",
                                      description=cfg.description, latest=latest))  # fmt: skip
    publishers = sorted({s["publisher"] for i in summaries for s in i["stories"]})
    categories = [c for c in CATEGORY_LABELS.values()
                  if any(s["category"] == c for i in summaries for s in i["stories"])]  # fmt: skip
    writer.page("/archive/", render("archive.html", "/archive/", title="Archive",
                                    description=f"Every {cfg.site_name} issue.",
                                    issues=summaries, publishers=publishers,
                                    categories=categories))  # fmt: skip
    corrections: list[dict[str, Any]] = [
        {"issue": issue_summary(e, cfg), **correction_note(c),
         "story_rank": c.story_rank, "original": c.original_text, "corrected": c.corrected_text}
        for e in editions for c in e.corrections if c.severity != "minor"
    ]  # fmt: skip
    corrections.sort(key=lambda c: (str(c["issue"]["date"]), str(c["at"])), reverse=True)
    writer.page("/corrections/", render("corrections.html", "/corrections/",
                                        title="Corrections",
                                        description="Every published correction.",
                                        corrections=corrections))  # fmt: skip
    for slug, title in POLICY_PAGES.items():
        about = f"{cfg.site_name}: {title.lower()}."
        writer.page(f"/{slug}/", render(f"pages/{slug}.html", f"/{slug}/", title=title,
                                        description=about,
                                        approved=cfg.policy_approved.get(slug)))  # fmt: skip
    writer.write("404.html", render("404.html", "/404.html", title="Page not found",
                                    description=cfg.description))  # fmt: skip

    index = {"version": 1, "site": cfg.site_name, "issues": summaries}
    compact = json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    writer.write("search-index.json", compact)
    lastmod = {e.issue_date.isoformat(): max([e.issue_date] + [ist(c.corrected_at).date()
               for c in e.corrections]) for e in editions}  # fmt: skip
    newest = max(lastmod.values()) if lastmod else None
    entries: list[tuple[str, date | None]] = [("/", newest), ("/archive/", newest),
                                              ("/corrections/", None)]  # fmt: skip
    entries += [(issue_path(e.issue_date), lastmod[e.issue_date.isoformat()]) for e in editions]
    entries += [(f"/{slug}/", None) for slug in POLICY_PAGES]
    writer.write("sitemap.xml", sitemap_xml(cfg, entries))
    writer.write("feed.xml", feed_xml(cfg, editions))
    writer.write("robots.txt", robots_txt(cfg, noindex))
    writer.write("_headers", headers_file(noindex))
    redirects = ""
    if latest:
        redirects = f"/today {latest['url']} 302\n/today/ {latest['url']} 302\n"
    writer.write("_redirects", redirects)
    marker = {  # read by `brief site deploy`; the folder is replaced on every build
        "built_by": "brief site build",
        "kind": "preview" if preview else "production",
        "base_url": cfg.base_url,
        "noindex": noindex,
        "latest": latest["date"] if latest else None,
        "issues": [s["date"] for s in summaries],
    }
    writer.write(MARKER, json.dumps(marker, indent=2, sort_keys=True) + "\n")

    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)
    return BuildResult(
        out=out,
        issues=[s["date"] for s in summaries],
        latest=latest["date"] if latest else None,
        preview=preview,
        skipped=skipped,
        files=sorted(writer.files),
    )
