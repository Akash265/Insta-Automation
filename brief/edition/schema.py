"""Edition record models (task P1-02).

One edition JSON file (`editions/YYYY-MM-DD.json`) carries everything needed for the
mandatory editorial audit trail (docs/EDITORIAL_PIPELINE.md §14). The models enforce
*structure and types*; whether an edition is complete enough for a given stage
(draft / review / published) is checked by `brief.edition.checks` (check C01), so a
draft can be saved before every field is known.

Timestamps must include a timezone. Event time (`event_at`) and the article's
publication time (`published_at`) are always separate fields.
"""

from __future__ import annotations

import json
import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION: Literal["1.0"] = "1.0"
ISSUE_KEY_RE = re.compile(r"^ADB-(\d{4}-\d{2}-\d{2})$")
SHA256_RE = r"^[0-9a-f]{64}$"
CHECKLIST_KEYS = (
    "headlines_match_sources",
    "script_matches_evidence",
    "dates_and_time_words_correct",
    "caption_page_reel_agree",
    "audio_video_quality_ok",
    "no_unlicensed_media_or_undisclosed_promotion",
)


def _require_https(url: str) -> str:
    if not url.startswith("https://") or len(url) <= len("https://"):
        raise ValueError(f"must be an https:// URL: {url!r}")
    if any(ch.isspace() for ch in url):
        raise ValueError(f"URL must not contain whitespace: {url!r}")
    return url


HttpsUrl = Annotated[str, Field(min_length=9, max_length=2048)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Category(StrEnum):
    MODEL_RELEASE = "model_release"
    RESEARCH = "research"
    OPEN_SOURCE = "open_source"
    BUSINESS = "business"
    POLICY = "policy"


class SourceType(StrEnum):
    RSS = "rss"
    ATOM = "atom"
    GITHUB_RELEASES = "github_releases"
    ARXIV = "arxiv"
    HTML_PAGE = "html_page"
    APIFY = "apify"
    MANUAL = "manual"


class ClaimType(StrEnum):
    FACT = "fact"
    VENDOR_CLAIM = "vendor_claim"
    BENCHMARK_VENDOR = "benchmark_vendor"
    BENCHMARK_INDEPENDENT = "benchmark_independent"
    AVAILABILITY = "availability"
    INTERPRETATION = "interpretation"
    FORECAST = "forecast"
    QUOTE = "quote"


class ClaimStatus(StrEnum):
    UNVERIFIED = "unverified"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    UNSUPPORTED = "unsupported"
    WITHDRAWN = "withdrawn"


class EventAtBasis(StrEnum):
    STATED = "stated"
    INFERRED = "inferred"
    SAME_AS_PUBLISHED = "same_as_published"
    UNKNOWN = "unknown"


Tier = Annotated[int, Field(ge=1, le=3)]


class Evidence(_Model):
    url: HttpsUrl
    publisher: str = Field(min_length=1)
    source_tier: Tier
    stance: Literal["supports", "contradicts", "context"]
    excerpt: str = Field(min_length=1, max_length=300)
    # When the URL was actually fetched and read. Missing = not fetched (fails C03).
    retrieved_at: AwareDatetime | None = None

    @field_validator("url")
    @classmethod
    def _url_https(cls, v: str) -> str:
        return _require_https(v)


class Claim(_Model):
    claim_text: str = Field(min_length=1, max_length=400)
    claim_type: ClaimType
    materiality: Literal["material", "minor"]
    status: ClaimStatus = ClaimStatus.UNVERIFIED
    confidence: Literal["high", "medium", "low"] | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    verified_by: str | None = None
    verified_at: AwareDatetime | None = None


class Score(_Model):
    """Rubric v1.1 sub-scores (docs/EDITORIAL_PIPELINE.md §5)."""

    rubric_version: str = "1.1"
    significance: int = Field(ge=0, le=25)
    source_confidence: int = Field(ge=0, le=25)
    freshness: int = Field(ge=0, le=20)
    practical_relevance: int = Field(ge=0, le=15)
    novelty: int = Field(ge=0, le=10)
    audience_fit: int = Field(ge=0, le=5)
    origin: dict[str, Literal["rule", "llm", "editor"]] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return (
            self.significance
            + self.source_confidence
            + self.freshness
            + self.practical_relevance
            + self.novelty
            + self.audience_fit
        )


class Story(_Model):
    story_id: str = Field(min_length=1)
    rank: int = Field(ge=1, le=7)
    category: Category
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    technical_notes: str | None = None
    limitations: str | None = None
    publisher: str = Field(min_length=1)
    source_type: SourceType
    source_tier: Tier
    primary_source_url: HttpsUrl
    supporting_source_urls: list[HttpsUrl] = Field(default_factory=list)
    published_at: AwareDatetime | None = None
    event_at: AwareDatetime | None = None
    event_at_basis: EventAtBasis
    collected_at: AwareDatetime
    selected_reason: str | None = None
    score: Score | None = None
    claims: list[Claim] = Field(default_factory=list)
    card_text: str | None = None
    narration: str | None = None
    sponsored: bool = False
    disclosure: str | None = None

    @field_validator("primary_source_url")
    @classmethod
    def _primary_https(cls, v: str) -> str:
        return _require_https(v)

    @field_validator("supporting_source_urls")
    @classmethod
    def _supporting_https(cls, v: list[str]) -> list[str]:
        return [_require_https(u) for u in v]

    @model_validator(mode="after")
    def _event_basis_consistent(self) -> Story:
        if self.event_at is None and self.event_at_basis is not EventAtBasis.UNKNOWN:
            raise ValueError("event_at is missing, so event_at_basis must be 'unknown'")
        if self.event_at is not None and self.event_at_basis is EventAtBasis.UNKNOWN:
            raise ValueError("event_at is set, so event_at_basis cannot be 'unknown'")
        return self


class Script(_Model):
    version: int = Field(ge=1)
    hook: str = Field(min_length=1)
    outro: str = Field(min_length=1)


class Review(_Model):
    regime: Literal["full", "exception"]
    regime_reason: str = Field(min_length=1)
    reviewer: str | None = None
    decision: Literal["pending", "approved", "changes_requested", "rejected"] = "pending"
    checklist: dict[str, bool] = Field(default_factory=dict)
    reviewed_at: AwareDatetime | None = None

    @field_validator("checklist")
    @classmethod
    def _known_keys(cls, v: dict[str, bool]) -> dict[str, bool]:
        unknown = set(v) - set(CHECKLIST_KEYS)
        if unknown:
            raise ValueError(f"unknown checklist items: {sorted(unknown)}")
        return v


class Correction(_Model):
    severity: Literal["critical", "material", "minor"]
    story_rank: int | None = Field(default=None, ge=1, le=7)
    original_text: str = Field(min_length=1)
    corrected_text: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    public_note: str | None = None
    approved_by: str = Field(min_length=1)
    corrected_at: AwareDatetime


class NarrationRef(_Model):
    segment: int = Field(ge=0)
    file: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_RE)
    tts_provider: str = Field(min_length=1)
    tts_model: str = Field(min_length=1)
    voice: str = Field(min_length=1)


class MediaRef(_Model):
    key: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_RE)


class Media(_Model):
    narration: list[NarrationRef] = Field(default_factory=list)
    mp4: MediaRef | None = None
    cover: MediaRef | None = None


class Deployment(_Model):
    preview_url: HttpsUrl | None = None
    production_deploy_id: str | None = None
    deployed_at: AwareDatetime | None = None
    linkcheck: Literal["pass", "fail", "not_run"] = "not_run"


class Publication(_Model):
    """Where the edition went. During the private experiment: method 'private'."""

    platform: Literal["instagram", "none"]
    method: Literal["private", "manual", "api"]
    permalink: HttpsUrl | None = None
    media_id: str | None = None
    published_at: AwareDatetime | None = None


class Seo(_Model):
    title: str = Field(min_length=1, max_length=70)
    description: str = Field(min_length=1, max_length=160)


class ProductionLog(_Model):
    minutes_research: int | None = Field(default=None, ge=0)
    minutes_verify: int | None = Field(default=None, ge=0)
    minutes_script: int | None = Field(default=None, ge=0)
    minutes_render: int | None = Field(default=None, ge=0)
    minutes_site: int | None = Field(default=None, ge=0)
    minutes_review: int | None = Field(default=None, ge=0)
    minutes_publish: int | None = Field(default=None, ge=0)
    minutes_audit: int | None = Field(default=None, ge=0)


class Candidate(_Model):
    url: HttpsUrl
    title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    source_type: SourceType
    published_at: AwareDatetime | None = None
    event_at: AwareDatetime | None = None
    collected_at: AwareDatetime
    rule_code: str | None = Field(default=None, pattern=r"^R(0[1-9]|1[0-2])$")
    eligible: bool

    @field_validator("url")
    @classmethod
    def _url_https(cls, v: str) -> str:
        return _require_https(v)


class Experiment(_Model):
    day: int | None = Field(default=None, ge=1, le=14)
    candidates: list[Candidate] = Field(default_factory=list)
    eligible_count: int | None = Field(default=None, ge=0)
    quiet_day: bool = False
    notes: str | None = None


class Edition(_Model):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    issue_key: str
    issue_date: date
    timezone: str = "Asia/Kolkata"
    cutoff_at: AwareDatetime
    status: Literal["draft", "in_review", "approved", "published", "skipped"] = "draft"
    production_epoch: Literal[1, 2] = 1
    is_quiet_day: bool = False
    daily_thesis: str | None = None
    seo: Seo | None = None
    stories: list[Story] = Field(default_factory=list, max_length=7)
    script: Script | None = None
    caption: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    issue_url: HttpsUrl | None = None
    sponsor_flag: bool = False
    review: Review | None = None
    corrections: list[Correction] = Field(default_factory=list)
    media: Media | None = None
    deployment: Deployment | None = None
    publication: Publication | None = None
    production_log: ProductionLog | None = None
    experiment: Experiment | None = None

    @model_validator(mode="after")
    def _issue_key_matches_date(self) -> Edition:
        m = ISSUE_KEY_RE.match(self.issue_key)
        if not m:
            raise ValueError("issue_key must look like ADB-YYYY-MM-DD")
        if m.group(1) != self.issue_date.isoformat():
            raise ValueError("issue_key date must equal issue_date")
        return self


def json_schema_text() -> str:
    """The committed JSON Schema text (`schemas/edition.schema.json`), deterministic."""
    schema = Edition.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "AI Daily Brief edition"
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
