"""P1-13 (caption part): the caption is generated from the edition record."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from brief.cli import app
from brief.edition.caption import GENERIC_SPONSOR_LINE, build_caption, caption_for_posting
from brief.edition.checks import validate_edition
from brief.edition.schema import Edition
from tests.conftest import FIXTURES

Data = dict[str, Any]


def test_matches_fixture_captions(normal: Data, quiet: Data) -> None:
    for data in (normal, quiet):
        assert build_caption(Edition.model_validate(data)) == data["caption"]


def test_deterministic(normal: Data) -> None:
    edition = Edition.model_validate(normal)
    assert build_caption(edition) == build_caption(Edition.model_validate(normal))


def test_quiet_day_title(quiet: Data) -> None:
    assert build_caption(Edition.model_validate(quiet)).splitlines()[0].endswith("(quiet day)")


def test_generated_caption_passes_checks(normal: Data) -> None:
    normal["caption"] = "placeholder"
    edition = Edition.model_validate(normal)
    edition = edition.model_copy(update={"caption": build_caption(edition)})
    report = validate_edition(edition, "published")
    assert report.ok and not report.warnings, report.render()


def test_sponsored_story_disclosure_line_satisfies_c11(normal: Data) -> None:
    normal["stories"][2]["sponsored"] = True
    normal["stories"][2]["disclosure"] = "Example Toolkit maintainers supported this segment."
    edition = Edition.model_validate(normal)
    text = build_caption(edition)
    assert "Sponsored: Example Toolkit maintainers supported this segment." in text
    edition = edition.model_copy(update={"caption": text})
    assert not [i for i in validate_edition(edition, "published").issues if i.code == "C11"]


def test_sponsor_flag_without_story_uses_generic_line(normal: Data) -> None:
    normal["sponsor_flag"] = True
    assert GENERIC_SPONSOR_LINE in build_caption(Edition.model_validate(normal))


def test_posting_text_appends_hashtags(normal: Data) -> None:
    text = caption_for_posting(Edition.model_validate(normal))
    assert text.endswith("\n\n#AI #AINews")


def test_cli_write_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "edition.json"
    data = json.loads((FIXTURES / "normal.json").read_text(encoding="utf-8"))
    data["caption"] = None
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(app, ["caption", str(path), "--write"]).exit_code == 0
    first = path.read_text(encoding="utf-8")
    assert runner.invoke(app, ["caption", str(path), "--write"]).exit_code == 0
    assert path.read_text(encoding="utf-8") == first
    assert (
        json.loads(first)["caption"]
        == json.loads((FIXTURES / "normal.json").read_text(encoding="utf-8"))["caption"]
    )
