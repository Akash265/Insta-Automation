"""brief/llm/client.py with a fake Anthropic SDK and a mock Ollama (no network, no spend)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from brief.budget import IST, Budget, BudgetExceededError, UsageEntry, load_config
from brief.llm.client import (
    AnthropicJSON,
    InvalidOutputError,
    LLMError,
    OllamaJSON,
    RefusalError,
    load_models,
)
from tests.conftest import ROOT

MODELS = load_models(ROOT / "config" / "llm_routes.yaml")
SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
          "additionalProperties": False}  # fmt: skip
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=IST)


class FakeSDK:
    def __init__(
        self,
        text: str = '{"ok": true}',
        stop: str = "end_turn",
        in_tok: int = 1000,
        out_tok: int = 200,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self.text, self.stop, self.error = text, stop, error
        self.in_tok, self.out_tok = in_tok, out_tok
        self.messages = self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        usage = SimpleNamespace(
            input_tokens=self.in_tok,
            output_tokens=self.out_tok,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=self.text),
            ],
            stop_reason=self.stop,
            stop_details=SimpleNamespace(category="cyber") if self.stop == "refusal" else None,
            usage=usage,
            _request_id="req_test",
        )


def budget(tmp: Path) -> Budget:
    return Budget(load_config(ROOT / "config" / "budget_periods.yaml"),
                  usage_path=tmp / "usage.jsonl", cash_path=tmp / "cash.csv")  # fmt: skip


def ledger(tmp: Path) -> list[dict[str, Any]]:
    path = tmp / "usage.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def client(tmp: Path, sdk: FakeSDK) -> AnthropicJSON:
    return AnthropicJSON(budget(tmp), MODELS, sdk=sdk, clock=lambda: NOW)


def test_call_uses_structured_output_and_logs_actual_cost(tmp_path: Path) -> None:
    sdk = FakeSDK(in_tok=10_000, out_tok=2_000)
    r = client(tmp_path, sdk).complete("claude-sonnet-5-5", "sys", "user", SCHEMA, "bakeoff:T5")
    assert r.data == {"ok": True} and r.request_id == "req_test"
    assert r.cost_usd == pytest.approx(10_000 * 2 / 1e6 + 2_000 * 10 / 1e6)
    call = sdk.calls[0]
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert call["output_config"]["effort"] == "medium" and "temperature" not in call
    [row] = ledger(tmp_path)
    assert row["status"] == "ok" and row["model"] == "claude-sonnet-5-5"
    assert row["cost_usd"] == pytest.approx(0.04) and row["operation"] == "bakeoff:T5"


def test_budget_blocks_before_any_request(tmp_path: Path) -> None:
    b = budget(tmp_path)
    b.record(UsageEntry(NOW, "llm", "anthropic", "earlier", 2.95))  # near the $3.00 prep daily cap
    sdk = FakeSDK()
    c = AnthropicJSON(b, MODELS, sdk=sdk, clock=lambda: NOW)
    with pytest.raises(BudgetExceededError, match="daily LLM cap"):
        c.complete("claude-opus-5-5", "s", "u", SCHEMA, "bakeoff:T5", max_tokens=8000)
    assert sdk.calls == []
    assert ledger(tmp_path)[-1]["status"] == "blocked_by_budget"


def test_refusal_is_billed_logged_and_raised(tmp_path: Path) -> None:
    c = client(tmp_path, FakeSDK(stop="refusal"))
    with pytest.raises(RefusalError, match="cyber"):
        c.complete("claude-haiku-5-5", "s", "u", SCHEMA, "t")
    assert ledger(tmp_path)[0]["cost_usd"] > 0


def test_truncated_and_invalid_output_fail(tmp_path: Path) -> None:
    with pytest.raises(InvalidOutputError, match="max_tokens"):
        client(tmp_path, FakeSDK(stop="max_tokens")).complete(
            "claude-haiku-5-5", "s", "u", SCHEMA, "t"
        )
    with pytest.raises(InvalidOutputError, match="not JSON"):
        client(tmp_path, FakeSDK(text="nope")).complete("claude-haiku-5-5", "s", "u", SCHEMA, "t")

    def must_be_false(d: dict[str, Any]) -> None:
        if d["ok"]:
            raise ValueError("ok must be false")

    with pytest.raises(InvalidOutputError, match="validation"):
        client(tmp_path, FakeSDK()).complete(
            "claude-haiku-5-5", "s", "u", SCHEMA, "t", validate=must_be_false
        )


def test_api_errors_are_logged_without_cost(tmp_path: Path) -> None:
    err = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    with pytest.raises(LLMError, match="APIConnectionError"):
        client(tmp_path, FakeSDK(error=err)).complete("claude-haiku-5-5", "s", "u", SCHEMA, "t")
    [row] = ledger(tmp_path)
    assert row["status"] == "error" and row["cost_usd"] == 0


def test_guards(tmp_path: Path) -> None:
    c = client(tmp_path, FakeSDK())
    with pytest.raises(LLMError, match="over claude-haiku-5-5's limit"):
        c.complete("claude-haiku-5-5", "s", "x" * 400_000, SCHEMA, "t")
    with pytest.raises(LLMError, match="not a configured Anthropic model"):
        c.complete("qwen2.5:7b", "s", "u", SCHEMA, "t")
    assert MODELS["claude-opus-5-5"].evaluation_only


def test_ollama_local_only_and_parses() -> None:
    with pytest.raises(LLMError, match="localhost"):
        OllamaJSON("http://10.0.0.5:11434")
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        body = {"message": {"content": '{"ok": false}'}, "prompt_eval_count": 50,
                "eval_count": 5, "load_duration": 2e9, "done_reason": "stop"}  # fmt: skip
        return httpx.Response(200, json=body)

    r = OllamaJSON(transport=httpx.MockTransport(handler)).complete("qwen2.5:7b", "s", "u", SCHEMA)
    assert r.data == {"ok": False} and r.input_tokens == 50 and r.extra["load_s"] == 2.0
    assert seen["format"] == SCHEMA and seen["options"]["temperature"] == 0

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError, match="timed out"):
        OllamaJSON(transport=httpx.MockTransport(slow)).complete("qwen2.5:7b", "s", "u", SCHEMA)


def test_ollama_prompt_json_mode_strips_code_fences() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": '```json\n{"ok": true}\n```'}})

    o = OllamaJSON(transport=httpx.MockTransport(handler), structured=False, think=False)
    assert o.complete("gemma4:e4b", "s", "u", SCHEMA).data == {"ok": True}
    assert "format" not in seen and seen["think"] is False
    assert '"required": ["ok"]' in seen["messages"][0]["content"]
