"""LLM calls with JSON-schema output, budget gates and usage logging (ADR-003).

Every hosted (paid) call:
1. is priced from `config/llm_routes.yaml` and checked with `Budget.check("llm", ...)`
   against the worst case (estimated input + `max_tokens` output) before it is sent;
   a blocked call is logged by the budget and raises `BudgetExceededError`;
2. asks for structured output (`output_config.format` json_schema) and validates the
   returned JSON again on our side;
3. is recorded in the usage ledger at its actual cost (from `usage`), including calls
   that end in a refusal, a truncation or invalid output, because those are billed too.
A refusal raises `RefusalError`; truncated or invalid JSON raises `InvalidOutputError`.
Nothing is retried here: the caller decides (one bounded repair at most, CLAUDE.md).

Local calls go to Ollama on 127.0.0.1 with its `format` JSON schema. They cost nothing
and are not logged to the ledger; latency and token counts are returned for P1-09.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anthropic
import httpx
import yaml  # type: ignore[import-untyped]

from brief.budget import IST, Budget, UsageEntry

DEFAULT_ROUTES = Path("config/llm_routes.yaml")
FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
CHARS_PER_TOKEN = 3.0  # conservative (over-estimates tokens) for the budget pre-check


class LLMError(RuntimeError):
    """An LLM call failed."""


class RefusalError(LLMError):
    """The model declined (stop_reason == "refusal")."""


class InvalidOutputError(LLMError):
    """Output was truncated, not JSON, or failed validation."""


@dataclass(frozen=True)
class ModelInfo:
    name: str
    provider: str
    input_usd_per_mtok: float = 0.0
    output_usd_per_mtok: float = 0.0
    max_input_tokens: int | None = None
    evaluation_only: bool = False

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        ) / 1_000_000


def load_models(path: Path = DEFAULT_ROUTES) -> dict[str, ModelInfo]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    models: dict[str, ModelInfo] = {}
    for name, raw in (data.get("models") or {}).items():
        models[str(name)] = ModelInfo(
            name=str(name),
            provider=str(raw["provider"]),
            input_usd_per_mtok=float(raw.get("input_usd_per_mtok", 0)),
            output_usd_per_mtok=float(raw.get("output_usd_per_mtok", 0)),
            max_input_tokens=raw.get("max_input_tokens"),
            evaluation_only=bool(raw.get("evaluation_only", False)),
        )
    return models


@dataclass
class LLMResult:
    model: str
    data: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    stop_reason: str | None = None
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _parse(text: str, validate: Callable[[dict[str, Any]], None] | None) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidOutputError(f"output is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidOutputError("output is not a JSON object")
    if validate is not None:
        try:
            validate(data)
        except (ValueError, TypeError, KeyError) as exc:
            raise InvalidOutputError(f"output failed validation: {exc}") from exc
    return data


class AnthropicJSON:
    """Hosted Claude calls with structured output, budget gate and ledger."""

    def __init__(
        self,
        budget: Budget,
        models: dict[str, ModelInfo],
        sdk: Any = None,  # an anthropic.Anthropic, or a fake in tests
        clock: Callable[[], datetime] = lambda: datetime.now(IST),
    ) -> None:
        self.budget = budget
        self.models = models
        self._sdk = sdk
        self.clock = clock

    @property
    def sdk(self) -> Any:
        if self._sdk is None:
            self._sdk = anthropic.Anthropic(max_retries=2, timeout=300.0)
        return self._sdk

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        operation: str,
        max_tokens: int = 8000,
        effort: str = "medium",
        validate: Callable[[dict[str, Any]], None] | None = None,
    ) -> LLMResult:
        info = self.models.get(model)
        if info is None or info.provider != "anthropic":
            raise LLMError(f"{model!r} is not a configured Anthropic model")
        est_in = int((len(system) + len(user)) / CHARS_PER_TOKEN) + 50
        if info.max_input_tokens is not None and est_in > info.max_input_tokens:
            raise LLMError(f"prompt (~{est_in} tokens) is over {model}'s limit "
                           f"{info.max_input_tokens}")  # fmt: skip
        self.budget.check("llm", info.cost(est_in, max_tokens), self.clock(),
                          provider="anthropic", operation=operation)  # fmt: skip
        started = time.monotonic()
        try:
            resp = self.sdk.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except anthropic.APIError as exc:
            self._log(model, operation, 0.0, "error", None, f"{type(exc).__name__}")
            raise LLMError(f"{model}: {type(exc).__name__}: {exc}") from exc
        latency = time.monotonic() - started
        usage = resp.usage
        in_tok = int(usage.input_tokens or 0) + int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        )
        cached = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        out_tok = int(usage.output_tokens or 0)
        cost = info.cost(in_tok, out_tok) + cached * info.input_usd_per_mtok * 0.1 / 1_000_000
        request_id = getattr(resp, "_request_id", None)
        self._log(model, operation, cost, "ok", request_id, f"stop={resp.stop_reason}")
        if resp.stop_reason == "refusal":
            details = getattr(resp, "stop_details", None)
            raise RefusalError(f"{model} declined ({getattr(details, 'category', None)})")
        if resp.stop_reason == "max_tokens":
            raise InvalidOutputError(f"{model} hit max_tokens={max_tokens}: output truncated")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = _parse(text, validate)
        return LLMResult(model, data, in_tok + cached, out_tok, cost, latency,
                         resp.stop_reason, request_id)  # fmt: skip

    def _log(self, model: str, operation: str, cost: float, status: str,
             request_id: str | None, note: str) -> None:  # fmt: skip
        self.budget.record(
            UsageEntry(
                at=self.clock(),
                category="llm",
                provider="anthropic",
                operation=operation,
                cost_usd=round(cost, 6),
                status=status,  # type: ignore[arg-type]
                model=model,
                request_id=request_id,
                note=note,
            )
        )


class OllamaJSON:
    """Local model calls through Ollama's chat API with a JSON-schema `format`."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        timeout_s: float = 15.0,
        keep_alive: str | int = "5m",
        transport: httpx.BaseTransport | None = None,
        structured: bool = True,
        think: bool | None = None,
    ) -> None:
        """structured=False: for models whose Ollama runner has no JSON-schema `format`
        (e.g. gemma4 on the MLX runner); the schema goes into the prompt and the reply is
        validated here instead. think=False turns a model's thinking off."""
        host = urlparse(base_url).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise LLMError(f"Ollama must run on this Mac (localhost), not {host!r}")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.keep_alive = keep_alive
        self.structured = structured
        self.think = think
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        validate: Callable[[dict[str, Any]], None] | None = None,
    ) -> LLMResult:
        if not self.structured:
            system = (
                f"{system}\n\nReply with only a JSON object that matches this JSON schema, "
                f"with no other text:\n{json.dumps(schema)}"
            )
        body: dict[str, Any] = {
            "model": model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.structured:
            body["format"] = schema
        if self.think is not None:
            body["think"] = self.think
        started = time.monotonic()
        try:
            resp = self._client.post(f"{self.base_url}/api/chat", json=body)
            resp.raise_for_status()
            raw = resp.json()
        except httpx.TimeoutException as exc:
            raise LLMError(f"{model}: timed out after {self.timeout_s:.0f} s") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError(f"{model}: {type(exc).__name__}: {exc}") from exc
        latency = time.monotonic() - started
        text = str((raw.get("message") or {}).get("content", ""))
        if not self.structured:  # prompt-JSON replies often come in a Markdown code fence
            text = FENCE_RE.sub(r"\1", text.strip())
        data = _parse(text, validate)
        return LLMResult(
            model, data, int(raw.get("prompt_eval_count", 0)), int(raw.get("eval_count", 0)),
            0.0, latency, str(raw.get("done_reason")),
            extra={"load_s": raw.get("load_duration", 0) / 1e9},
        )  # fmt: skip

    def unload(self, model: str) -> None:
        """Ask Ollama to unload the model now (keep_alive 0; V-06)."""
        self._client.post(f"{self.base_url}/api/generate",
                          json={"model": model, "keep_alive": 0}).raise_for_status()  # fmt: skip

    def loaded(self) -> list[dict[str, Any]]:
        resp = self._client.get(f"{self.base_url}/api/ps")
        resp.raise_for_status()
        return list(resp.json().get("models", []))
