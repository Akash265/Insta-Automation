"""P1-02: edition models, the committed JSON Schema, fixtures and template."""

from __future__ import annotations

import json
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from brief.cli import app
from brief.edition.schema import Edition, json_schema_text
from tests.conftest import FIXTURES, ROOT

SCHEMA_FILE = ROOT / "schemas" / "edition.schema.json"


def test_committed_schema_is_up_to_date() -> None:
    assert SCHEMA_FILE.read_text(encoding="utf-8") == json_schema_text()


def test_schema_generation_is_deterministic() -> None:
    assert json_schema_text() == json_schema_text()


def test_schema_export_check_command() -> None:
    result = CliRunner().invoke(app, ["schema", "export", "--check", "--out", str(SCHEMA_FILE)])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "path",
    [FIXTURES / "normal.json", FIXTURES / "quiet_day.json", ROOT / "editions/_template.json"],
)
def test_files_validate_against_models_and_json_schema(path: Any) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    Edition.model_validate(data)
    jsonschema.validate(data, json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))


def test_http_url_rejected(normal: dict[str, Any]) -> None:
    normal["stories"][0]["primary_source_url"] = "http://example.com/labs/news/nimbus-2"
    with pytest.raises(ValidationError):
        Edition.model_validate(normal)


def test_issue_key_must_match_date(normal: dict[str, Any]) -> None:
    normal["issue_key"] = "ADB-2026-11-21"
    with pytest.raises(ValidationError):
        Edition.model_validate(normal)


def test_event_basis_must_agree_with_event_at(normal: dict[str, Any]) -> None:
    normal["stories"][0]["event_at"] = None  # basis still 'same_as_published'
    with pytest.raises(ValidationError):
        Edition.model_validate(normal)


def test_timestamps_need_timezone(normal: dict[str, Any]) -> None:
    normal["stories"][0]["collected_at"] = "2026-11-20T05:10:00"
    with pytest.raises(ValidationError):
        Edition.model_validate(normal)


def test_unknown_fields_rejected(normal: dict[str, Any]) -> None:
    normal["stories"][0]["surprise"] = True
    with pytest.raises(ValidationError):
        Edition.model_validate(normal)


def test_score_total(normal: dict[str, Any]) -> None:
    edition = Edition.model_validate(normal)
    assert edition.stories[0].score is not None
    assert edition.stories[0].score.total == 92
