"""P1-13 `brief script draft` with a fake model (no network, no spend)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import brief.llm.client as client_mod
from brief.budget import Budget, load_config
from brief.cli import app
from brief.edition.checks import parse_edition
from brief.edition.schema import Edition
from brief.llm.client import AnthropicJSON, LLMResult, load_models
from brief.llm.script_draft import (
    STORY_FIELDS,
    TASK,
    DraftError,
    apply_draft,
    draft_script,
    load_route,
    script_input,
)
from tests.conftest import ROOT
from tests.test_llm_client import NOW, FakeSDK

Data = dict[str, Any]
MODELS = load_models(ROOT / "config" / "llm_routes.yaml")
ROUTE = load_route(TASK, MODELS, ROOT / "config" / "llm_routes.yaml")


def edition_of(data: Data) -> Edition:
    edition, issues = parse_edition(data)
    assert edition is not None, issues
    return edition


def good_reply(data: Data) -> Data:
    """A valid model reply: the fixture's own (check-passing) copy."""
    return {
        "hook": data["script"]["hook"],
        "outro": data["script"]["outro"],
        "stories": [
            {"rank": s["rank"], "story_id": s["story_id"]}
            | {f: s.get(f) or "" for f in STORY_FIELDS}
            for s in data["stories"]
        ],
    }


class SequenceSDK(FakeSDK):
    """Returns each reply text in turn."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self.replies = replies

    def create(self, **kwargs: Any) -> Any:
        self.text = self.replies[len(self.calls)]
        return super().create(**kwargs)


def hosted(tmp: Path, sdk: FakeSDK) -> AnthropicJSON:
    budget = Budget(load_config(ROOT / "config" / "budget_periods.yaml"),
                    usage_path=tmp / "usage.jsonl", cash_path=tmp / "cash.csv")  # fmt: skip
    return AnthropicJSON(budget, MODELS, sdk=sdk, clock=lambda: NOW)


def test_route_is_haiku_with_script_v2() -> None:
    assert (ROUTE.model, ROUTE.effort, ROUTE.prompt) == ("claude-haiku-5-5", "medium", "script.v2")


def test_route_refuses_an_evaluation_only_model(tmp_path: Path) -> None:
    routes = tmp_path / "routes.yaml"
    routes.write_text(
        "routes:\n  T6_script: {primary: claude-opus-5-5, prompt: script.v2}\n", encoding="utf-8"
    )
    with pytest.raises(DraftError, match="evaluation only"):
        load_route(TASK, MODELS, routes)


def test_input_has_only_supported_claims_and_no_urls(normal: Data) -> None:
    normal["stories"][0]["claims"][1]["status"] = "contested"
    contested = normal["stories"][0]["claims"][1]["claim_text"]
    text = script_input(edition_of(normal))
    assert normal["stories"][0]["claims"][0]["claim_text"] in text
    assert contested not in text
    assert "http" not in text
    assert 'event="2026-11-20"' in text and 'edition_date="2026-11-20"' in text


def test_input_refuses_a_story_without_supported_claims(normal: Data) -> None:
    for c in normal["stories"][3]["claims"]:
        c["status"] = "unverified"
    with pytest.raises(DraftError, match=r"stories \[4\]"):
        script_input(edition_of(normal))


def test_draft_success_is_applied_and_logged(normal: Data, tmp_path: Path) -> None:
    sdk = SequenceSDK([json.dumps(good_reply(normal))])
    draft = draft_script(edition_of(normal), hosted(tmp_path, sdk), ROUTE)
    assert draft.attempts == 1 and draft.model == "claude-haiku-5-5"
    call = sdk.calls[0]
    assert call["model"] == "claude-haiku-5-5" and call["output_config"]["effort"] == "medium"
    assert "AI Daily Brief" in call["system"]  # the script.v2 prompt
    updated = apply_draft(normal, draft)
    assert updated["script"]["version"] == 2
    assert updated["stories"][1]["narration"] == normal["stories"][1]["narration"]
    assert edition_of(updated).script is not None
    [row] = [json.loads(x) for x in (tmp_path / "usage.jsonl").read_text().splitlines()]
    assert row["operation"] == "script_draft:ADB-2026-11-20" and row["status"] == "ok"


def test_one_repair_then_success(normal: Data, tmp_path: Path) -> None:
    bad = good_reply(normal)
    bad["stories"][0]["narration"] = "Read more at https://example.com/today."
    sdk = SequenceSDK([json.dumps(bad), json.dumps(good_reply(normal))])
    draft = draft_script(edition_of(normal), hosted(tmp_path, sdk), ROUTE)
    assert draft.attempts == 2
    repair_prompt = sdk.calls[1]["messages"][0]["content"]
    assert "<rejected_reason>" in repair_prompt and "URL" in repair_prompt


def test_fails_explicitly_after_one_repair(normal: Data, tmp_path: Path) -> None:
    wrong = good_reply(normal)
    wrong["stories"] = wrong["stories"][:3]  # stories missing
    sdk = SequenceSDK([json.dumps(wrong), "not json"])
    with pytest.raises(DraftError, match="after 1 repair"):
        draft_script(edition_of(normal), hosted(tmp_path, sdk), ROUTE)
    assert len(sdk.calls) == 2
    assert len((tmp_path / "usage.jsonl").read_text().splitlines()) == 2  # both billed


def test_cli_refuses_non_draft_and_existing_script(normal: Data, tmp_path: Path) -> None:
    path = tmp_path / "e.json"
    path.write_text(json.dumps(normal), encoding="utf-8")
    result = CliRunner().invoke(app, ["script", "draft", str(path)])
    assert result.exit_code == 2 and "only a draft" in result.output
    normal["status"] = "draft"
    path.write_text(json.dumps(normal), encoding="utf-8")
    result = CliRunner().invoke(app, ["script", "draft", str(path), "--write"])
    assert result.exit_code == 2 and "--force" in result.output


def test_cli_writes_the_draft(
    normal: Data, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    normal["status"] = "draft"
    path = tmp_path / "e.json"
    path.write_text(json.dumps(normal), encoding="utf-8")
    reply = good_reply(normal)
    reply["hook"] = "A drafted hook about five AI developments this Friday."

    class FakeHosted:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def complete(self, model: str, *args: Any, **kwargs: Any) -> LLMResult:
            kwargs["validate"](reply)
            return LLMResult(model, reply, 4000, 6000, 0.0034, 1.0)

    monkeypatch.setattr(client_mod, "AnthropicJSON", FakeHosted)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    result = CliRunner().invoke(
        app, ["script", "draft", str(path), "--write", "--force", "--env-file", "/nonexistent"]
    )
    assert result.exit_code == 0, result.output
    assert "A drafted hook" in result.output and "script version 2" in result.output
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["script"]["hook"] == reply["hook"] and stored["script"]["version"] == 2
