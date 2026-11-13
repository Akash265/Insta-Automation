"""`brief site deploy`: upload a built `dist/` to Cloudflare Pages and verify it (P1-12).

ADR-006 / ADR-012: Direct Upload with the pinned wrangler (`npx --no-install wrangler`),
never a Git-connected build.
- The project's address (`<subdomain>.pages.dev`, which can differ from the project name,
  e.g. `ai-daily-brief-7vb.pages.dev`) is read from the Cloudflare API, never guessed.
- `--preview` deploys to the branch alias `preview.<subdomain>` for review.
- `--production` deploys to the production branch (`main`, `<subdomain>`). It is
  refused for a `--preview` build (which can contain unapproved editions) and when the
  build's `base_url` isn't this project's address.
After the upload the live site is checked over HTTPS: `/` is 200; when there is an issue,
`/today` redirects to `/issues/<latest>/`, which is 200; a noindex build is served with
`X-Robots-Tag: noindex`. A failed check fails the command.

Credentials come from the environment or `.env` (git-ignored): `CLOUDFLARE_API_TOKEN`,
`CLOUDFLARE_ACCOUNT_ID`, `CF_PAGES_PROJECT`. The token is passed only to wrangler's
environment and is never printed; any output that contains it is redacted.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from brief.site.build import MARKER

REQUIRED = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CF_PAGES_PROJECT")
PRODUCTION_BRANCH = "main"
PREVIEW_BRANCH = "preview"
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,56}[a-z0-9]$")
VERIFY_ATTEMPTS = 6
VERIFY_WAIT_S = 5.0


class DeployError(RuntimeError):
    """The deploy was refused, failed, or the live site didn't pass its checks."""


SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.pages\.dev$")
API = "https://api.cloudflare.com/client/v4"


@dataclass(frozen=True)
class Credentials:
    token: str
    account_id: str
    project: str


@dataclass(frozen=True)
class Target:
    """Where the project is served: `<subdomain>` and its preview alias."""

    subdomain: str

    @property
    def production_url(self) -> str:
        return f"https://{self.subdomain}"

    @property
    def preview_url(self) -> str:
        return f"https://{PREVIEW_BRANCH}.{self.subdomain}"


@dataclass
class DeployResult:
    mode: str
    site_url: str
    deployment_url: str | None
    latest: str | None
    checks: list[str] = field(default_factory=list)


def read_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; blank lines and # comments ignored; optional surrounding quotes."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def load_credentials(dotenv: Path, environ: Mapping[str, str] | None = None) -> Credentials:
    env_now = os.environ if environ is None else environ
    env = {**read_dotenv(dotenv), **{k: v for k, v in env_now.items() if v}}
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        raise DeployError(f"missing {', '.join(missing)} (set them in {dotenv} or the env)")
    project = env["CF_PAGES_PROJECT"]
    if not PROJECT_RE.match(project):
        raise DeployError(f"CF_PAGES_PROJECT {project!r} is not a valid Pages project name")
    return Credentials(env["CLOUDFLARE_API_TOKEN"], env["CLOUDFLARE_ACCOUNT_ID"], project)


def fetch_target(creds: Credentials, client: httpx.Client | None = None) -> Target:
    """Look up the project's `*.pages.dev` subdomain (read-only API call)."""
    url = f"{API}/accounts/{creds.account_id}/pages/projects/{creds.project}"
    own = client is None
    http = client or httpx.Client(timeout=15.0)
    try:
        resp = http.get(url, headers={"Authorization": f"Bearer {creds.token}"})
        data = resp.json() if resp.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise DeployError(f"could not look up the Pages project: {exc.__class__.__name__}") from exc
    finally:
        if own:
            http.close()
    if resp.status_code != 200 or not data.get("success"):
        errors = "; ".join(f"{e.get('code')} {e.get('message')}" for e in data.get("errors", []))
        detail = redact(errors, creds) or "no detail"
        raise DeployError(
            f"Pages project {creds.project!r} lookup failed ({resp.status_code}): {detail}"
        )
    subdomain = str((data.get("result") or {}).get("subdomain", ""))
    if not SUBDOMAIN_RE.match(subdomain):
        raise DeployError(f"unexpected Pages subdomain {subdomain!r}")
    return Target(subdomain)


def read_marker(dist: Path) -> dict[str, object]:
    path = dist / MARKER
    if not path.is_file():
        raise DeployError(f"{dist} is not a `brief site build` output; run `brief site build`")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DeployError(f"{path} is from an older build; run `brief site build` again") from exc
    if not isinstance(data, dict):
        raise DeployError(f"{path} is not a build marker")
    return data


def wrangler_command(dist: Path, project: str, branch: str) -> list[str]:
    return ["npx", "--no-install", "wrangler", "pages", "deploy", str(dist),
            "--project-name", project, "--branch", branch, "--commit-dirty=true"]  # fmt: skip


def wrangler_env(creds: Credentials) -> dict[str, str]:
    """A minimal environment: no other secrets from this shell reach wrangler."""
    keep = ("PATH", "HOME", "TMPDIR", "LANG", "USER", "SHELL")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(
        CLOUDFLARE_API_TOKEN=creds.token,
        CLOUDFLARE_ACCOUNT_ID=creds.account_id,
        WRANGLER_SEND_METRICS="false",
        CI="1",  # never prompt
    )
    return env


def redact(text: str, creds: Credentials) -> str:
    return text.replace(creds.token, "[redacted]") if creds.token else text


Runner = Callable[[list[str], dict[str, str]], tuple[int, str]]
Getter = Callable[[str], httpx.Response]


def run_wrangler(args: list[str], env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        args, env=env, capture_output=True, text=True, timeout=600, check=False
    )
    return proc.returncode, proc.stdout + proc.stderr


def http_get(url: str) -> httpx.Response:
    with httpx.Client(follow_redirects=False, timeout=15.0) as client:
        return client.get(url, headers={"User-Agent": "brief-site-deploy"})


def verify_site(
    base: str,
    latest: str | None,
    noindex: bool,
    get: Getter = http_get,
    attempts: int = VERIFY_ATTEMPTS,
    wait_s: float = VERIFY_WAIT_S,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Check the live site; retries while a fresh deploy propagates. Returns what passed."""
    problems: list[str] = []
    for attempt in range(attempts):
        if attempt:
            sleep(wait_s)
        passed, problems = _verify_once(base, latest, noindex, get)
        if not problems:
            return passed
    raise DeployError(f"{base}: " + "; ".join(problems))


def _verify_once(
    base: str, latest: str | None, noindex: bool, get: Getter
) -> tuple[list[str], list[str]]:
    passed: list[str] = []
    problems: list[str] = []
    try:
        home = get(base + "/")
        if home.status_code == 200:
            passed.append("/ 200")
        else:
            problems.append(f"/ returned {home.status_code}")
        if noindex and "noindex" not in home.headers.get("x-robots-tag", "").lower():
            problems.append("/ is missing X-Robots-Tag: noindex")
        elif noindex:
            passed.append("X-Robots-Tag noindex")
        if latest:
            issue = f"/issues/{latest}/"
            today = get(base + "/today/")
            location = today.headers.get("location", "")
            if today.status_code in (301, 302, 303, 307, 308) and location.rstrip("/").endswith(
                issue.rstrip("/")
            ):
                passed.append(f"/today/ {today.status_code} -> {issue}")
            else:
                problems.append(f"/today/ returned {today.status_code} to {location or 'nowhere'}")
            page = get(base + issue)
            if page.status_code == 200 and "Read original" in page.text:
                passed.append(f"{issue} 200")
            else:
                problems.append(f"{issue} returned {page.status_code}")
    except httpx.HTTPError as exc:
        problems.append(f"request failed: {exc.__class__.__name__}")
    return passed, problems


def deploy_site(
    dist: Path,
    production: bool,
    creds: Credentials,
    target: Target,
    run: Runner = run_wrangler,
    get: Getter = http_get,
    sleep: Callable[[float], None] = time.sleep,
) -> DeployResult:
    marker = read_marker(dist)
    latest_raw = marker.get("latest")
    latest = latest_raw if isinstance(latest_raw, str) else None
    if production:
        if marker.get("kind") != "production":
            raise DeployError("refusing to deploy a --preview build to production; "
                              "run `brief site build` without --preview")  # fmt: skip
        if marker.get("base_url") != target.production_url:
            raise DeployError(f"build base_url {marker.get('base_url')} is not "
                              f"{target.production_url}; fix config/site.yaml")  # fmt: skip
    branch = PRODUCTION_BRANCH if production else PREVIEW_BRANCH
    site = target.production_url if production else target.preview_url
    code, output = run(wrangler_command(dist, creds.project, branch), wrangler_env(creds))
    output = redact(output, creds)
    if code != 0:
        tail = "\n".join(output.strip().splitlines()[-15:])
        raise DeployError(f"wrangler failed (exit {code}):\n{tail}")
    found = re.search(rf"https://[a-z0-9-]+\.{re.escape(target.subdomain)}", output)
    # Previews are always noindex (ours, and Pages adds X-Robots-Tag to preview aliases).
    noindex = bool(marker.get("noindex")) or not production
    checks = verify_site(site, latest, noindex, get, sleep=sleep)
    return DeployResult(
        mode="production" if production else "preview",
        site_url=site,
        deployment_url=found.group(0) if found else None,
        latest=latest,
        checks=checks,
    )
