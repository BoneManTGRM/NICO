#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "nico.production_specialist_release_identity.v1"
DEFAULT_ORIGIN = "https://app.nicoaudit.com"
DEFAULT_UI_CONTRACT = "expert-engagement-v2"


def _origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("production_origin_must_be_https")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("production_origin_must_not_include_path_query_or_fragment")
    return f"https://{parsed.netloc}".rstrip("/")


def _request(url: str, *, accept: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "nico-specialist-production-release-proof",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "status": int(response.status),
                "body": response.read().decode("utf-8", errors="replace"),
                "final_url": str(response.geturl()),
                "headers": {str(key).lower(): str(value) for key, value in response.headers.items()},
            }
    except urllib.error.HTTPError as exc:
        return {
            "status": int(exc.code),
            "body": exc.read().decode("utf-8", errors="replace"),
            "final_url": str(exc.geturl()),
            "headers": {str(key).lower(): str(value) for key, value in exc.headers.items()},
        }


def _json_body(response: dict[str, Any], *, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(response.get("body") or ""))
    except json.JSONDecodeError as exc:
        raise AssertionError(code) from exc
    if not isinstance(payload, dict):
        raise AssertionError(code)
    return payload


def _wait_for_release(
    origin: str,
    expected_sha: str,
    expected_ui_contract: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    attempts: list[dict[str, Any]] = []
    while True:
        url = origin + "/api/release?" + urllib.parse.urlencode(
            {"expected_sha": expected_sha, "_nico_release_probe": time.time_ns()}
        )
        response = _request(url, accept="application/json", timeout=45)
        payload: dict[str, Any] = {}
        try:
            payload = _json_body(response, code="release_identity_invalid_json")
        except AssertionError:
            pass
        observation = {
            "http_status": response["status"],
            "release_sha": str(payload.get("release_sha") or ""),
            "ui_contract": str(payload.get("ui_contract") or ""),
            "deployment_environment": str(payload.get("deployment_environment") or ""),
            "git_ref": str(payload.get("git_ref") or ""),
        }
        attempts.append(observation)
        if (
            observation["http_status"] == 200
            and observation["release_sha"] == expected_sha
            and observation["ui_contract"] == expected_ui_contract
            and observation["deployment_environment"] == "production"
            and observation["git_ref"] == "main"
        ):
            return observation, attempts
        if time.monotonic() >= deadline:
            raise AssertionError(
                "production_release_identity_did_not_converge:" + json.dumps(observation, sort_keys=True)
            )
        time.sleep(max(0.1, interval_seconds))


def _verify_login_surface(
    origin: str,
    *,
    requested_path: str,
    expected_login_path: str,
    required_text: tuple[str, ...],
) -> dict[str, Any]:
    response = _request(
        origin + requested_path + "?tier=comprehensive&_nico_auth_probe=" + str(time.time_ns()),
        accept="text/html",
        timeout=60,
    )
    html = str(response.get("body") or "")
    final_path = urllib.parse.urlsplit(str(response.get("final_url") or "")).path
    missing = [item for item in required_text if item not in html]
    forbidden = [
        item
        for item in (
            'data-workspace="assessment"',
            'data-assessment-primary-action="true"',
            "Create engagement and capture repository snapshot",
            "Crear encargo y capturar instantánea del repositorio",
        )
        if item in html
    ]
    if response["status"] != 200 or final_path != expected_login_path or missing or forbidden:
        raise AssertionError(
            "specialist_login_boundary_invalid:"
            + json.dumps(
                {
                    "http_status": response["status"],
                    "final_path": final_path,
                    "expected_login_path": expected_login_path,
                    "missing": missing,
                    "forbidden": forbidden,
                },
                sort_keys=True,
            )
        )
    return {
        "requested_path": requested_path,
        "final_path": final_path,
        "http_status": response["status"],
        "specialist_login_rendered": True,
        "password_input_present": 'id="nico-operator-password"' in html and 'type="password"' in html,
        "assessment_workspace_hidden": not forbidden,
    }


def _verify_unauthenticated_api_block(origin: str) -> dict[str, Any]:
    response = _request(
        origin + "/api/nico/assessment/comprehensive-run/comprun_release_probe/report/pdf",
        accept="application/json",
        timeout=45,
    )
    payload = _json_body(response, code="unauthenticated_assessment_api_invalid_json")
    detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else {}
    code = str(detail.get("code") or payload.get("code") or "")
    if response["status"] != 401 or code != "specialist_authentication_required":
        raise AssertionError(
            "unauthenticated_assessment_api_not_blocked:"
            + json.dumps({"http_status": response["status"], "code": code}, sort_keys=True)
        )
    return {
        "http_status": response["status"],
        "code": code,
        "run_existence_disclosed": False,
        "assessment_data_disclosed": False,
        "blocked": True,
    }


def _verify_readiness(origin: str, expected_sha: str) -> dict[str, Any]:
    response = _request(
        origin + "/api/nico/diagnostics/specialist-readiness?_nico_auth_probe=" + str(time.time_ns()),
        accept="application/json",
        timeout=45,
    )
    payload = _json_body(response, code="specialist_readiness_invalid_json")
    release = payload.get("release_provenance") if isinstance(payload.get("release_provenance"), dict) else {}
    checks = {
        "http_ok": response["status"] == 200,
        "ready": payload.get("status") == "ready",
        "specialist_access": payload.get("specialist_access_installed") is True,
        "assessment_routes_authenticated": payload.get("authenticated_comprehensive_routes_enforced") is True,
        "session_signing": payload.get("session_signing_configured") is True,
        "credential_separation": payload.get("credential_separation_verified") is True,
        "runtime_ready": payload.get("comprehensive_runtime_ready") is True,
        "durable_storage": payload.get("durable_storage_verified") is True,
        "release_identity": payload.get("release_identity_complete") is True,
        "backend_sha": release.get("backend_build_commit") == expected_sha,
        "frontend_sha": release.get("frontend_build_commit") == expected_sha,
        "human_review_required": payload.get("human_review_required") is True,
        "automatic_delivery_blocked": payload.get("client_delivery_allowed") is False,
        "secrets_not_exposed": payload.get("secrets_exposed") is False,
        "github_actions_proof_enabled": payload.get("github_actions_production_proof_enabled") is True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise AssertionError("specialist_readiness_failed:" + ",".join(failed))
    return {"status": "ready", "checks": checks, "release_provenance": release}


def verify(
    *,
    origin: str,
    expected_sha: str,
    expected_ui_contract: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    normalized = _origin(origin)
    started = time.time()
    release, attempts = _wait_for_release(
        normalized,
        expected_sha,
        expected_ui_contract,
        timeout_seconds=timeout_seconds,
        interval_seconds=interval_seconds,
    )
    english = _verify_login_surface(
        normalized,
        requested_path="/assessment",
        expected_login_path="/specialist-login",
        required_text=(
            "Cybersecurity specialist access",
            'id="nico-operator-password"',
            'type="password"',
            "Open NICO",
        ),
    )
    spanish = _verify_login_surface(
        normalized,
        requested_path="/es/assessment",
        expected_login_path="/es/specialist-login",
        required_text=(
            "Acceso para especialistas en ciberseguridad",
            'id="nico-operator-password"',
            'type="password"',
            "Abrir NICO",
        ),
    )
    api_boundary = _verify_unauthenticated_api_block(normalized)
    readiness = _verify_readiness(normalized, expected_sha)
    return {
        "artifact_schema": VERSION,
        "status": "passed",
        "origin": normalized,
        "expected_sha": expected_sha,
        "release": release,
        "release_attempts": attempts,
        "english": english,
        "spanish": spanish,
        "unauthenticated_api": api_boundary,
        "specialist_readiness": readiness,
        "proof": {
            "exact_release_sha": True,
            "exact_ui_contract": True,
            "production_environment": True,
            "english_specialist_login_contract": True,
            "spanish_specialist_login_contract": True,
            "workspace_hidden_until_authentication": True,
            "unauthenticated_assessment_api_blocked": True,
            "run_identifier_not_a_bearer_credential": True,
            "specialist_readiness_green": True,
        },
        "started_at_epoch": started,
        "finished_at_epoch": time.time(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify NICO's exact authenticated specialist production boundary.")
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--expected-ui-contract", default=DEFAULT_UI_CONTRACT)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--interval-seconds", type=float, default=15)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = verify(
            origin=args.origin,
            expected_sha=str(args.expected_sha).strip().lower(),
            expected_ui_contract=str(args.expected_ui_contract).strip(),
            timeout_seconds=max(1.0, args.timeout_seconds),
            interval_seconds=max(0.1, args.interval_seconds),
        )
    except Exception as exc:
        payload = {
            "artifact_schema": VERSION,
            "status": "failed",
            "origin": args.origin,
            "expected_sha": args.expected_sha,
            "error": f"{type(exc).__name__}: {exc}",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
