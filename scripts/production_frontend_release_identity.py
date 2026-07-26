#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ARTIFACT_SCHEMA = "nico.frontend_production_release_identity.v1"
DEFAULT_UI_CONTRACT = "expert-engagement-v2"
DEFAULT_DEPLOYMENT_ENVIRONMENT = "production"
DEFAULT_TIMEOUT_SECONDS = 15 * 60
DEFAULT_INTERVAL_SECONDS = 15.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 45.0

WORKSPACE_MARKERS = (
    'data-workspace="assessment"',
    'data-engagement-type="comprehensive"',
    'data-canonical-assessment="strategic"',
    'data-assessment-copy-contract="expert-engagement-v2"',
    'data-assessment-action-copy="create-engagement-v2"',
)
LOCALES = {
    "en": {
        "path": "/assessment",
        "expected_label": "Create engagement and capture repository snapshot",
        "forbidden_labels": ("Run NICO Assessment",),
    },
    "es-MX": {
        "path": "/es/assessment",
        "expected_label": "Crear encargo y capturar instantánea del repositorio",
        "forbidden_labels": ("Ejecutar evaluación NICO",),
    },
}


class ReleaseIdentityError(RuntimeError):
    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: str
    headers: dict[str, str]


HttpFetcher = Callable[[urllib.request.Request, float], HttpResult]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


def _default_fetch(request: urllib.request.Request, timeout: float) -> HttpResult:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpResult(
                status=int(response.status),
                body=response.read().decode("utf-8", errors="replace"),
                headers={str(key): str(value) for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        return HttpResult(
            status=int(exc.code),
            body=exc.read().decode("utf-8", errors="replace"),
            headers={str(key): str(value) for key, value in exc.headers.items()},
        )


def _origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Production origin must be an absolute HTTPS URL.")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Production origin must not include a path, query, or fragment.")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _request_headers(*, accept: str) -> dict[str, str]:
    return {
        "Accept": accept,
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "CDN-Cache-Control": "no-store",
        "Vercel-CDN-Cache-Control": "no-store",
        "User-Agent": "nico-unified-production-release-identity",
    }


def _cache_busted_url(base: str, *, expected_sha: str, attempt: int, wall_time_ns: int) -> str:
    separator = "&" if "?" in base else "?"
    return base + separator + urllib.parse.urlencode(
        {
            "expected_sha": expected_sha,
            "attempt": attempt,
            "_nico_release_probe": wall_time_ns,
        }
    )


def probe_release(
    *,
    origin: str,
    expected_sha: str,
    attempt: int,
    fetch: HttpFetcher = _default_fetch,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    wall_time_ns: Callable[[], int] = time.time_ns,
) -> dict[str, Any]:
    url = _cache_busted_url(
        origin.rstrip("/") + "/api/release",
        expected_sha=expected_sha,
        attempt=attempt,
        wall_time_ns=wall_time_ns(),
    )
    request = urllib.request.Request(url, headers=_request_headers(accept="application/json"))
    try:
        result = fetch(request, request_timeout_seconds)
    except Exception as exc:
        return {
            "attempt": attempt,
            "url": url,
            "http_status": 0,
            "release_sha": "",
            "ui_contract": "",
            "deployment_environment": "",
            "git_ref": "",
            "error": f"{type(exc).__name__}: {exc}",
        }

    observation: dict[str, Any] = {
        "attempt": attempt,
        "url": url,
        "http_status": result.status,
        "release_sha": "",
        "ui_contract": "",
        "deployment_environment": "",
        "git_ref": "",
    }
    try:
        payload = json.loads(result.body)
    except json.JSONDecodeError as exc:
        observation["error"] = f"invalid_json: {exc}"
        observation["body_preview"] = result.body[:240]
        return observation
    if not isinstance(payload, dict):
        observation["error"] = "invalid_payload_type"
        return observation

    observation.update(
        {
            "release_sha": str(payload.get("release_sha") or "").strip(),
            "ui_contract": str(payload.get("ui_contract") or "").strip(),
            "deployment_environment": str(payload.get("deployment_environment") or "").strip(),
            "git_ref": str(payload.get("git_ref") or "").strip(),
        }
    )
    return observation


def _release_matches(
    observation: dict[str, Any],
    *,
    expected_sha: str,
    expected_ui_contract: str,
    expected_deployment_environment: str,
) -> bool:
    return bool(
        observation.get("http_status") == 200
        and observation.get("release_sha") == expected_sha
        and observation.get("ui_contract") == expected_ui_contract
        and observation.get("deployment_environment") == expected_deployment_environment
    )


def wait_for_release_identity(
    *,
    origin: str,
    expected_sha: str,
    expected_ui_contract: str = DEFAULT_UI_CONTRACT,
    expected_deployment_environment: str = DEFAULT_DEPLOYMENT_ENVIRONMENT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    fetch: HttpFetcher = _default_fetch,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
    wall_time_ns: Callable[[], int] = time.time_ns,
) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    started = clock()
    attempts: list[dict[str, Any]] = []
    attempt = 0
    while True:
        attempt += 1
        observation = probe_release(
            origin=origin,
            expected_sha=expected_sha,
            attempt=attempt,
            fetch=fetch,
            request_timeout_seconds=request_timeout_seconds,
            wall_time_ns=wall_time_ns,
        )
        elapsed = max(0.0, clock() - started)
        observation["elapsed_seconds"] = round(elapsed, 3)
        attempts.append(observation)
        print(
            "Production release observation: "
            + json.dumps(
                {
                    "origin": origin,
                    "expected_sha": expected_sha,
                    "observed_sha": observation.get("release_sha") or "",
                    "ui_contract": observation.get("ui_contract") or "",
                    "deployment_environment": observation.get("deployment_environment") or "",
                    "http_status": observation.get("http_status"),
                    "elapsed_seconds": observation["elapsed_seconds"],
                    "attempt": attempt,
                    "error": observation.get("error") or "",
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if _release_matches(
            observation,
            expected_sha=expected_sha,
            expected_ui_contract=expected_ui_contract,
            expected_deployment_environment=expected_deployment_environment,
        ):
            return observation, attempts, elapsed

        if elapsed >= timeout_seconds:
            evidence = {
                "artifact_schema": ARTIFACT_SCHEMA,
                "status": "failed",
                "stage": "release_identity",
                "origin": origin,
                "expected_sha": expected_sha,
                "expected_ui_contract": expected_ui_contract,
                "expected_deployment_environment": expected_deployment_environment,
                "elapsed_seconds": round(elapsed, 3),
                "attempts": attempts,
                "final_observation": observation,
                "error": (
                    "Production custom domain did not serve the exact expected release identity before timeout. "
                    "A successful provider deployment status is insufficient when the production alias remains stale."
                ),
            }
            raise ReleaseIdentityError(evidence["error"], evidence)

        sleep(max(0.0, min(interval_seconds, timeout_seconds - elapsed)))


def fetch_assessment_html(
    *,
    origin: str,
    path: str,
    expected_sha: str,
    locale: str,
    fetch: HttpFetcher = _default_fetch,
    request_timeout_seconds: float = 60.0,
    wall_time_ns: Callable[[], int] = time.time_ns,
) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {
            "tier": "comprehensive",
            "expected_commit_sha": expected_sha,
            "_nico_release_probe": wall_time_ns(),
        }
    )
    url = origin.rstrip("/") + path + "?" + query
    request = urllib.request.Request(url, headers=_request_headers(accept="text/html"))
    try:
        result = fetch(request, request_timeout_seconds)
    except Exception as exc:
        return {
            "locale": locale,
            "url": url,
            "http_status": 0,
            "html": "",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "locale": locale,
        "url": url,
        "http_status": result.status,
        "html": result.body,
    }


def verify_assessment_page(
    *,
    locale: str,
    page: dict[str, Any],
    expected_ui_contract: str = DEFAULT_UI_CONTRACT,
) -> dict[str, Any]:
    html = str(page.get("html") or "")
    expected = LOCALES[locale]
    expected_markers = tuple(
        marker.replace(DEFAULT_UI_CONTRACT, expected_ui_contract)
        if "data-assessment-copy-contract" in marker
        else marker
        for marker in WORKSPACE_MARKERS
    )
    missing = [marker for marker in expected_markers if marker not in html]
    expected_label = str(expected["expected_label"])
    if expected_label not in html:
        missing.append(expected_label)
    forbidden = [label for label in expected["forbidden_labels"] if str(label) in html]
    verified = page.get("http_status") == 200 and not missing and not forbidden
    evidence = {
        "locale": locale,
        "url": page.get("url") or "",
        "http_status": page.get("http_status") or 0,
        "expected_label": expected_label,
        "workspace_markers_verified": not any(marker in missing for marker in expected_markers),
        "exact_label_verified": expected_label not in missing,
        "missing": missing,
        "forbidden": forbidden,
        "verified": verified,
    }
    if page.get("error"):
        evidence["error"] = page["error"]
    if not verified:
        raise ReleaseIdentityError(
            f"Production {locale} assessment page is stale or violates the exact UI contract.",
            {
                "artifact_schema": ARTIFACT_SCHEMA,
                "status": "failed",
                "stage": "assessment_page",
                "page": evidence,
            },
        )
    return evidence


def verify_production_frontend(
    *,
    origin: str,
    expected_sha: str,
    expected_ui_contract: str = DEFAULT_UI_CONTRACT,
    expected_deployment_environment: str = DEFAULT_DEPLOYMENT_ENVIRONMENT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    fetch: HttpFetcher = _default_fetch,
    clock: Clock = time.monotonic,
    sleep: Sleeper = time.sleep,
    wall_time_ns: Callable[[], int] = time.time_ns,
) -> dict[str, Any]:
    normalized_origin = _origin(origin)
    started_epoch = time.time()
    release, attempts, elapsed = wait_for_release_identity(
        origin=normalized_origin,
        expected_sha=expected_sha,
        expected_ui_contract=expected_ui_contract,
        expected_deployment_environment=expected_deployment_environment,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
        request_timeout_seconds=request_timeout_seconds,
        fetch=fetch,
        clock=clock,
        sleep=sleep,
        wall_time_ns=wall_time_ns,
    )

    pages: dict[str, Any] = {}
    for locale, config in LOCALES.items():
        raw_page = fetch_assessment_html(
            origin=normalized_origin,
            path=str(config["path"]),
            expected_sha=expected_sha,
            locale=locale,
            fetch=fetch,
            request_timeout_seconds=max(request_timeout_seconds, 60.0),
            wall_time_ns=wall_time_ns,
        )
        try:
            pages[locale] = verify_assessment_page(
                locale=locale,
                page=raw_page,
                expected_ui_contract=expected_ui_contract,
            )
        except ReleaseIdentityError as exc:
            evidence = {
                "artifact_schema": ARTIFACT_SCHEMA,
                "status": "failed",
                "stage": "assessment_page",
                "origin": normalized_origin,
                "expected_sha": expected_sha,
                "expected_ui_contract": expected_ui_contract,
                "expected_deployment_environment": expected_deployment_environment,
                "elapsed_seconds": round(elapsed, 3),
                "release_attempts": attempts,
                "final_release_observation": release,
                "pages": {**pages, locale: exc.evidence.get("page", {})},
                "error": str(exc),
            }
            raise ReleaseIdentityError(str(exc), evidence) from exc

    return {
        "artifact_schema": ARTIFACT_SCHEMA,
        "status": "passed",
        "origin": normalized_origin,
        "expected_sha": expected_sha,
        "expected_ui_contract": expected_ui_contract,
        "expected_deployment_environment": expected_deployment_environment,
        "started_at_epoch": started_epoch,
        "finished_at_epoch": time.time(),
        "elapsed_seconds": round(elapsed, 3),
        "release_attempts": attempts,
        "final_release_observation": release,
        "pages": pages,
        "proof": {
            "exact_release_sha": True,
            "exact_ui_contract": True,
            "production_environment": True,
            "cache_busted_no_store_requests": True,
            "english_copy_contract": True,
            "spanish_copy_contract": True,
            "workspace_contract": True,
            "preview_deployment_rejected": True,
        },
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify that the NICO production domain serves an exact frontend release.")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-ui-contract", default=DEFAULT_UI_CONTRACT)
    parser.add_argument("--expected-deployment-environment", default=DEFAULT_DEPLOYMENT_ENVIRONMENT)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--interval-seconds", type=float, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--request-timeout-seconds", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = verify_production_frontend(
            origin=args.origin,
            expected_sha=str(args.expected_sha).strip(),
            expected_ui_contract=str(args.expected_ui_contract).strip(),
            expected_deployment_environment=str(args.expected_deployment_environment).strip(),
            timeout_seconds=max(0.0, args.timeout_seconds),
            interval_seconds=max(0.0, args.interval_seconds),
            request_timeout_seconds=max(1.0, args.request_timeout_seconds),
        )
    except (ReleaseIdentityError, ValueError) as exc:
        if isinstance(exc, ReleaseIdentityError):
            payload = exc.evidence
        else:
            payload = {
                "artifact_schema": ARTIFACT_SCHEMA,
                "status": "failed",
                "stage": "configuration",
                "origin": args.origin,
                "expected_sha": args.expected_sha,
                "error": str(exc),
            }
        _write(args.output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    _write(args.output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
