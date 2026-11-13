"""P1-12: `brief site deploy` with a fake wrangler and a fake HTTP client (no network)."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import brief.cli as cli_mod
from brief.cli import app
from brief.site.build import build_site
from brief.site.deploy import (
    Credentials,
    DeployError,
    DeployResult,
    Target,
    deploy_site,
    fetch_target,
    load_credentials,
    verify_site,
)
from tests.test_site import CFG, NORMAL, QUIET, TEMPLATES, write_editions

TOKEN = "tok_" + "x" * 40  # synthetic
CREDS = Credentials(TOKEN, "0" * 32, "ai-daily-brief")
TARGET = Target("ai-daily-brief-7vb.pages.dev")
PROD = "https://ai-daily-brief-7vb.pages.dev"
PREV = "https://preview.ai-daily-brief-7vb.pages.dev"
Getter = Callable[[str], httpx.Response]


def built(tmp: Path, preview: bool = False) -> Path:
    eds = write_editions(tmp / "editions", NORMAL, QUIET)
    build_site(eds, tmp / "dist", CFG, TEMPLATES, preview)
    return tmp / "dist"


class FakeWrangler:
    def __init__(self, code: int = 0, output: str = "") -> None:
        self.code = code
        self.output = output or "Deployment complete! https://1a2b3c4d.ai-daily-brief-7vb.pages.dev"
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def __call__(self, args: list[str], env: dict[str, str]) -> tuple[int, str]:
        self.calls.append((args, env))
        return self.code, self.output


def site(latest: str = "2026-11-23", noindex: bool = True, today_to: str | None = None) -> Getter:
    """A fake live site as Cloudflare would serve it."""
    headers = {"x-robots-tag": "noindex"} if noindex else {}

    def get(url: str) -> httpx.Response:
        req = httpx.Request("GET", url)
        path = url.split(".pages.dev", 1)[1]
        if path == "/":
            return httpx.Response(200, headers=headers, text="home", request=req)
        if path == "/today/":
            loc = today_to or f"/issues/{latest}/"
            return httpx.Response(302, headers={**headers, "location": loc}, request=req)
        if path == f"/issues/{latest}/":
            return httpx.Response(200, headers=headers, text="Read original", request=req)
        return httpx.Response(404, request=req)

    return get


def no_sleep(_s: float) -> None:
    return None


def test_credentials_from_dotenv_with_env_override(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(f"# c\nCLOUDFLARE_API_TOKEN='{TOKEN}'\nexport CLOUDFLARE_ACCOUNT_ID=abc\n"
                   "CF_PAGES_PROJECT=ai-daily-brief\n", encoding="utf-8")  # fmt: skip
    c = load_credentials(env, {"CLOUDFLARE_ACCOUNT_ID": "fromenv"})
    assert (c.token, c.account_id, c.project) == (TOKEN, "fromenv", "ai-daily-brief")
    with pytest.raises(DeployError, match="missing CLOUDFLARE_API_TOKEN"):
        load_credentials(tmp_path / "none", {})
    with pytest.raises(DeployError, match="not a valid"):
        load_credentials(env, {"CF_PAGES_PROJECT": "Bad_Name"})


def test_preview_deploy_uses_the_preview_branch_and_checks_the_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOME_OTHER_SECRET", "must-not-leak")
    wrangler = FakeWrangler()
    result = deploy_site(
        built(tmp_path, preview=True), False, CREDS, TARGET, wrangler, site(), no_sleep
    )
    args, env = wrangler.calls[0]
    assert args[:5] == ["npx", "--no-install", "wrangler", "pages", "deploy"]
    assert args[args.index("--branch") + 1] == "preview"
    assert args[args.index("--project-name") + 1] == "ai-daily-brief"
    assert env["CLOUDFLARE_API_TOKEN"] == TOKEN and "SOME_OTHER_SECRET" not in env
    assert result.site_url == PREV and result.latest == "2026-11-23"
    assert result.deployment_url == "https://1a2b3c4d.ai-daily-brief-7vb.pages.dev"
    assert "/today/ 302 -> /issues/2026-11-23/" in result.checks


def test_production_deploy(tmp_path: Path) -> None:
    wrangler = FakeWrangler()
    result = deploy_site(built(tmp_path), True, CREDS, TARGET, wrangler, site(), no_sleep)
    args, _ = wrangler.calls[0]
    assert args[args.index("--branch") + 1] == "main" and result.site_url == PROD


def test_production_refuses_a_preview_build(tmp_path: Path) -> None:
    wrangler = FakeWrangler()
    with pytest.raises(DeployError, match="preview build"):
        deploy_site(built(tmp_path, preview=True), True, CREDS, TARGET, wrangler, site(), no_sleep)
    assert wrangler.calls == []


def test_production_refuses_a_build_for_another_address(tmp_path: Path) -> None:
    with pytest.raises(DeployError, match="base_url"):
        deploy_site(
            built(tmp_path),
            True,
            CREDS,
            Target("another.pages.dev"),
            FakeWrangler(),
            site(),
            no_sleep,
        )


def test_refuses_a_folder_that_is_not_a_build(tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    with pytest.raises(DeployError, match="not a `brief site build` output"):
        deploy_site(tmp_path / "dist", False, CREDS, TARGET, FakeWrangler(), site(), no_sleep)


def test_wrangler_failure_is_reported_without_the_token(tmp_path: Path) -> None:
    wrangler = FakeWrangler(code=1, output=f"Authentication error for token {TOKEN}")
    with pytest.raises(DeployError) as err:
        deploy_site(built(tmp_path), False, CREDS, TARGET, wrangler, site(), no_sleep)
    assert TOKEN not in str(err.value) and "[redacted]" in str(err.value)


def test_verify_fails_when_today_points_at_the_wrong_issue() -> None:
    sleeps: list[float] = []
    with pytest.raises(DeployError, match="/today/ returned 302 to /issues/2026-11-20/"):
        verify_site(PROD, "2026-11-23", True, site(today_to="/issues/2026-11-20/"),
                    attempts=3, wait_s=1.0, sleep=sleeps.append)  # fmt: skip
    assert sleeps == [1.0, 1.0]


def test_verify_requires_noindex_when_the_build_is_noindex() -> None:
    with pytest.raises(DeployError, match="X-Robots-Tag"):
        verify_site(PROD, "2026-11-23", True, site(noindex=False), attempts=1)
    assert verify_site(PROD, "2026-11-23", False, site(noindex=False), attempts=1)


def test_verify_retries_while_the_deploy_propagates() -> None:
    calls = {"n": 0}
    live = site()

    def flaky(url: str) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 3:
            return httpx.Response(404, request=httpx.Request("GET", url))
        return live(url)

    assert "/ 200" in verify_site(PROD, "2026-11-23", True, flaky, attempts=3, sleep=no_sleep)


def test_empty_site_checks_only_the_home_page() -> None:
    assert verify_site(PROD, None, True, site(), attempts=1) == ["/ 200", "X-Robots-Tag noindex"]


def test_cli_deploy_and_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = built(tmp_path, preview=True)
    env = tmp_path / ".env"
    env.write_text(f"CLOUDFLARE_API_TOKEN={TOKEN}\nCLOUDFLARE_ACCOUNT_ID={'0' * 32}\n"
                   "CF_PAGES_PROJECT=ai-daily-brief\n", encoding="utf-8")  # fmt: skip
    for key in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CF_PAGES_PROJECT"):
        monkeypatch.delenv(key, raising=False)

    def fake_deploy(d: Path, production: bool, creds: Credentials, t: Target) -> DeployResult:
        return deploy_site(d, production, creds, t, FakeWrangler(), site(), no_sleep)

    monkeypatch.setattr(cli_mod, "deploy_site", fake_deploy)
    monkeypatch.setattr(cli_mod, "fetch_target", lambda _c: TARGET)
    edition = tmp_path / "edition.json"
    edition.write_text(json.dumps(copy.deepcopy(NORMAL)), encoding="utf-8")
    base = ["site", "deploy", "--dist", str(dist), "--env-file", str(env)]
    assert CliRunner().invoke(app, base).exit_code == 2  # neither flag
    result = CliRunner().invoke(app, [*base, "--preview", "--record", str(edition)])
    assert result.exit_code == 0, result.output
    assert TOKEN not in result.output
    assert json.loads(edition.read_text(encoding="utf-8"))["deployment"]["preview_url"] == PREV


def test_fetch_target_reads_the_subdomain_and_hides_the_token() -> None:
    def api(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert request.url.path.endswith("/pages/projects/ai-daily-brief")
        result = {"subdomain": "ai-daily-brief-7vb.pages.dev"}
        return httpx.Response(200, json={"success": True, "result": result})

    with httpx.Client(transport=httpx.MockTransport(api)) as client:
        assert fetch_target(CREDS, client) == TARGET

    def denied(request: httpx.Request) -> httpx.Response:
        body = {"success": False, "errors": [{"code": 9109, "message": f"bad {TOKEN}"}]}
        return httpx.Response(403, json=body)

    with (
        httpx.Client(transport=httpx.MockTransport(denied)) as client,
        pytest.raises(DeployError, match="9109") as err,
    ):
        fetch_target(CREDS, client)
    assert TOKEN not in str(err.value)
