"""`brief report phase1` (P1-14) and `brief report experiment` (P1-19).

The reports *measure*; they don't decide. The continue / pivot / stop decision is the
founder's, using docs/VALIDATION_EXPERIMENT.md §8. Thresholds below mirror the
pre-registered §3 values exactly; a test pins them so they can't drift.
"""

from __future__ import annotations

import csv
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path

from brief.edition.checks import load_edition, validate_edition
from brief.edition.schema import Edition
from brief.experiment.errorlog import read_rows, summarize, verify

# Pre-registered thresholds (docs/VALIDATION_EXPERIMENT.md §3). Do not edit after Day 1.
THRESHOLDS = {
    "complete_editions_min": 10,
    "h1_days_with_5_eligible_min": 10,
    "h1_min_eligible_every_day": 3,
    "h2_evidence_share_min": 1.0,
    "h2_unresolved_max": 0,
    "h2_total_material_max": 1,
    "h2_minor_per_10_max": 3,
    "h3_median_all_max": 150,
    "h3_median_last5_max": 130,
    "h4_d1_mean_min": 3.8,
    "h4_response_rate_min": 0.5,
    "h4_d5_share_min": 0.6,
    "h5_w1_share_min": 0.5,
    "h5_misses_max": 2,
    "h6_render_ok_share_min": 0.9,
    "h6_deploy_share_min": 1.0,
    "w2_share_follow": 0.5,
    "w2_share_stop": 0.3,
}
STEP_FIELDS = (
    "minutes_research",
    "minutes_verify",
    "minutes_script",
    "minutes_render",
    "minutes_site",
    "minutes_review",
    "minutes_publish",
)
CAVEAT = (
    "Panel scores are an early qualitative signal from a small, non-random, friendly "
    "sample. They are not evidence of product-market fit."
)


@dataclass
class Section:
    title: str
    lines: list[str] = field(default_factory=list)
    verdict: str | None = None  # PASS / FAIL / INVALID / n/a

    def render(self) -> list[str]:
        head = f"{self.title}: {self.verdict}" if self.verdict else self.title
        return [head, *[f"  {ln}" for ln in self.lines], ""]


def _pf(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def load_editions(directory: Path) -> tuple[list[Edition], list[str]]:
    editions: list[Edition] = []
    problems: list[str] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("_"):
            continue
        edition, issues = load_edition(path)
        if edition is None:
            problems.append(f"{path.name}: {issues[0].message if issues else 'unreadable'}")
        else:
            editions.append(edition)
    editions.sort(key=lambda e: e.issue_date)
    return editions, problems


def _experiment_editions(editions: Sequence[Edition]) -> list[Edition]:
    return [e for e in editions if e.experiment is not None and e.experiment.day is not None]


def _minutes(e: Edition) -> int | None:
    log = e.production_log
    if log is None:
        return None
    values = [getattr(log, f) for f in STEP_FIELDS]
    return None if any(v is None for v in values) else sum(values)


# --------------------------------------------------------------------------- phase 1


def phase1_sections(editions: Sequence[Edition], problems: Sequence[str]) -> list[Section]:
    t = THRESHOLDS
    exp = _experiment_editions(editions)
    sections: list[Section] = []

    s = Section("Editions")
    complete = [e for e in exp if validate_edition(e, "published").ok]
    s.lines += [
        f"files read: {len(editions)} (experiment editions: {len(exp)})",
        f"complete (pass `validate --stage published`): {len(complete)} "
        f"(need >= {t['complete_editions_min']})",
    ]
    s.lines += [f"unreadable: {p}" for p in problems]
    s.verdict = _pf(len(complete) >= t["complete_editions_min"])
    sections.append(s)

    s = Section("H1 supply (should-pass)")
    counts = [e.experiment.eligible_count for e in exp if e.experiment is not None]
    known = [c for c in counts if c is not None]
    if not known:
        s.lines.append("no eligible_count recorded")
        s.verdict = "n/a"
    else:
        with5 = sum(1 for c in known if c >= 5)
        low = min(known)
        s.lines += [
            f"days with >= 5 eligible: {with5} (need >= {t['h1_days_with_5_eligible_min']})",
            f"lowest day: {low} (need >= {t['h1_min_eligible_every_day']} every day)",
        ]
        if len(known) < len(counts):
            s.lines.append(f"missing eligible_count on {len(counts) - len(known)} editions")
        ok = (
            with5 >= t["h1_days_with_5_eligible_min"]
            and low >= t["h1_min_eligible_every_day"]
            and len(known) == len(counts)
        )
        s.verdict = _pf(ok)
    sections.append(s)

    s = Section("H3 time (should-pass)")
    minutes = [(e, _minutes(e)) for e in exp]
    timed = [m for _, m in minutes if m is not None]
    if not timed:
        s.lines.append("no complete production_log recorded")
        s.verdict = "n/a"
    else:
        med_all = statistics.median(timed)
        last5 = timed[-5:]
        med_last5 = statistics.median(last5)
        s.lines += [
            f"median minutes per edition: {med_all:g} (need <= {t['h3_median_all_max']})",
            f"median of final {len(last5)}: {med_last5:g} (need <= {t['h3_median_last5_max']})",
        ]
        for f in STEP_FIELDS:
            vals = [
                getattr(e.production_log, f)
                for e, m in minutes
                if m is not None and e.production_log is not None
            ]
            s.lines.append(f"  {f.removeprefix('minutes_'):<9} median {statistics.median(vals):g}")
        untimed = len(minutes) - len(timed)
        if untimed:
            s.lines.append(f"editions without a complete time log: {untimed} (excluded)")
        s.verdict = _pf(
            med_all <= t["h3_median_all_max"]
            and len(last5) == 5
            and med_last5 <= t["h3_median_last5_max"]
        )
    sections.append(s)

    s = Section("H6 production stability (must-pass)")
    n = len(exp)
    if n == 0:
        s.lines.append("no experiment editions")
        s.verdict = "n/a"
    else:
        no_fix = sum(1 for e in exp if e.experiment and e.experiment.render_manual_fix is False)
        need = ceil(t["h6_render_ok_share_min"] * n)
        tail = exp[-5:]
        first_time = sum(1 for e in tail if e.experiment and e.experiment.render_attempts == 1)
        deployed = sum(1 for e in exp if e.deployment and e.deployment.production_deploy_id)
        s.lines += [
            f"renders without a manual fix: {no_fix}/{n} (need >= {need})",
            f"final {len(tail)} renders passed first time: {first_time}/{len(tail)}",
            f"deploys succeeded: {deployed}/{n} (need all)",
        ]
        s.verdict = _pf(no_fix >= need and len(tail) == 5 and first_time == 5 and deployed == n)
    sections.append(s)

    s = Section("Checks across editions (stage: published)")
    codes: Counter[str] = Counter()
    for e in exp:
        for issue in validate_edition(e, "published").issues:
            codes[f"{issue.code} {issue.severity}"] += 1
    s.lines += [f"{k}: {v}" for k, v in sorted(codes.items())] or ["no issues"]
    sections.append(s)

    s = Section("Review regimes and full-review counters")
    private = [e for e in editions if e.publication is None or e.publication.method == "private"]
    public = [
        e
        for e in editions
        if e.publication
        and e.publication.method in ("manual", "api")
        and e.publication.published_at is not None
    ]
    regimes = Counter(e.review.regime for e in editions if e.review)
    s.lines += [
        f"regimes: full {regimes.get('full', 0)}, exception {regimes.get('exception', 0)}",
        f"EXP private editions: {len(private)} (not counted toward FR-M, PD-03)",
        f"FR-M manual public editions: {sum(1 for e in public if e.production_epoch == 1)} / 30",
        f"FR-A automated public editions: {sum(1 for e in public if e.production_epoch == 2)} / 30",
    ]
    corrections = Counter(c.severity for e in editions for c in e.corrections)
    s.lines.append(
        "corrections: " + (", ".join(f"{k} {v}" for k, v in sorted(corrections.items())) or "none")
    )
    sections.append(s)
    return sections


def render_sections(title: str, sections: Sequence[Section], footer: Sequence[str] = ()) -> str:
    out = [title, ""]
    for s in sections:
        out += s.render()
    out += list(footer)
    return "\n".join(out).rstrip() + "\n"


def phase1_report(editions_dir: Path) -> str:
    editions, problems = load_editions(editions_dir)
    return render_sections(
        f"brief report phase1: {editions_dir}", phase1_sections(editions, problems)
    )


# --------------------------------------------------------------------------- experiment


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _score(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    score = int(value)
    if not 1 <= score <= 5:
        raise ValueError(f"rating {score} is outside 1-5")
    return score


def _share_at_least_4(values: Sequence[int]) -> float:
    return sum(1 for v in values if v >= 4) / len(values) if values else 0.0


@dataclass(frozen=True)
class ExperimentResult:
    text: str
    integrity_ok: bool


def experiment_report(experiment_dir: Path, editions_dir: Path) -> ExperimentResult:
    t = THRESHOLDS
    rows = read_rows(experiment_dir / "error-log.csv")
    problems = verify(rows)
    title = f"brief report experiment: {experiment_dir}"
    if problems:
        text = (
            "\n".join(
                [
                    title,
                    "",
                    "REFUSED: the error log is not intact (rows were edited, "
                    "deleted or reordered). Restore it from git; never rewrite it.",
                    *[f"  - {p}" for p in problems],
                ]
            )
            + "\n"
        )
        return ExperimentResult(text, False)

    editions, _ = load_editions(editions_dir)
    exp = _experiment_editions(editions)
    sections: list[Section] = []

    s = Section("H2 accuracy and provenance (must-pass a, b)")
    material = [
        c
        for e in exp
        for st in e.stories
        for c in st.claims
        if c.materiality == "material" and c.status.value != "withdrawn"
    ]
    evidenced = sum(1 for c in material if c.evidence)
    share = evidenced / len(material) if material else 0.0
    summary = summarize(rows)
    per10 = summary.minor / len(exp) * 10 if exp else 0.0
    s.lines += [
        f"(a) material claims with evidence: {evidenced}/{len(material)} ({share:.0%}; need 100%)",
        f"(b) unresolved material/critical errors: {summary.unresolved_material_or_critical} "
        f"(need 0) {list(summary.unresolved_ids) or ''}".rstrip(),
        f"(c) material/critical errors in total, corrected or not: "
        f"{summary.total_material_or_critical} (<= 1; >= 2 triggers stop rule 1)",
        f"minor errors per 10 editions: {per10:.1f} (<= {t['h2_minor_per_10_max']})",
        f"caught before publication: {summary.caught_pre_publication}",
    ]
    ok_ab = share >= t["h2_evidence_share_min"] and summary.unresolved_material_or_critical == 0
    s.verdict = _pf(ok_ab and bool(material))
    if summary.total_material_or_critical > t["h2_total_material_max"]:
        s.lines.append("STOP RULE 1 CONDITION MET: two or more material/critical errors")
    sections.append(s)

    responses = _read_csv(experiment_dir / "panel-responses.csv")
    roster = [
        r
        for r in _read_csv(experiment_dir / "panel-roster.csv")
        if r.get("active", "").strip().lower() in ("true", "yes", "1")
    ]
    d1 = [(r["panel_code"], v) for r in responses if (v := _score(r.get("D1", ""))) is not None]
    s = Section("H4 usefulness (must-pass; early qualitative signal)")
    panel_days = len(roster) * len(exp)
    rate = len(d1) / panel_days if panel_days else 0.0
    if not d1:
        s.lines.append("no D1 responses recorded")
        s.verdict = "INVALID"
    else:
        values = [v for _, v in d1]
        mean = statistics.fmean(values)
        dist = Counter(values)
        per_panelist: dict[str, list[int]] = {}
        for code, v in d1:
            per_panelist.setdefault(code, []).append(v)
        averages = [statistics.fmean(v) for v in per_panelist.values()]
        d5 = [v for r in responses if (v := _score(r.get("D5", ""))) is not None]
        s.lines += [
            f"D1 mean: {mean:.2f} (need >= {t['h4_d1_mean_min']}); n = {len(values)}",
            "D1 distribution: " + ", ".join(f"{k}: {dist.get(k, 0)}" for k in range(1, 6)),
            f"response rate: {len(d1)}/{panel_days} panel-days = {rate:.0%} "
            f"(need >= {t['h4_response_rate_min']:.0%})",
            f"median of per-panelist averages: {statistics.median(averages):.2f}; "
            f"panelists averaging >= 3.5: {sum(1 for a in averages if a >= 3.5)}/{len(averages)}",
            f"D5 'learned something new' rated >= 4: {_share_at_least_4(d5):.0%} "
            f"(diagnostic; target >= {t['h4_d5_share_min']:.0%})",
        ]
        if rate < t["h4_response_rate_min"]:
            s.verdict = "INVALID"
            s.lines.append("response rate below 50%: the measure is invalid, not passed")
        else:
            s.verdict = _pf(mean >= t["h4_d1_mean_min"])
    sections.append(s)

    w1 = [v for r in responses if (v := _score(r.get("W1", ""))) is not None]
    w2 = [v for r in responses if (v := _score(r.get("W2", ""))) is not None]
    misses = [
        r
        for r in _read_csv(experiment_dir / "coverage-misses.csv")
        if r.get("met_our_rules", "").strip().upper() == "Y"
    ]
    s = Section("H5 distinctiveness and coverage (should-pass)")
    s.lines += [
        f"(a) W1 'different from my sources' rated >= 4: {_share_at_least_4(w1):.0%} "
        f"of {len(w1)} (need >= {t['h5_w1_share_min']:.0%})",
        f"(b) major-story misses that met our rules: {len(misses)} (need <= {t['h5_misses_max']})",
        f"W2 'would watch regularly' rated >= 4: {_share_at_least_4(w2):.0%} of {len(w2)} "
        f"(stop rule 2 uses < {t['w2_share_stop']:.0%})",
    ]
    s.verdict = _pf(
        bool(w1)
        and _share_at_least_4(w1) >= t["h5_w1_share_min"]
        and len(misses) <= t["h5_misses_max"]
    )
    sections.append(s)

    audits = _read_csv(experiment_dir / "audit-log.csv")
    independent = {r["issue_key"] for r in audits if r.get("auditor_type") == "independent"}
    self_only = {r["issue_key"] for r in audits if r.get("auditor_type") == "self"} - independent
    s = Section("Audit coverage")
    s.lines += [
        f"editions audited by the independent auditor: {len(independent)} (target >= 10)",
        f"editions with only a self-audit (weaker evidence): {len(self_only)}",
        f"audited stories: {len({(r['issue_key'], r['story_rank']) for r in audits})}",
    ]
    sections.append(s)

    return ExperimentResult(render_sections(title, sections, [CAVEAT]), True)
