#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from comprehensive_production_run_handoff_v1 import load_source_proof
from github_actions_proof_session_v1 import request_github_oidc_token

VERSION = "nico.authenticated_completed_run_acceptance.v1"
SESSION_COOKIE = "nico-specialist-session"


def _origin(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("frontend_origin_must_be_https")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("frontend_origin_must_not_include_path_query_or_fragment")
    return f"https://{parsed.netloc}".rstrip("/")


def _request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    accept: str,
    timeout: float = 60.0,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
) -> tuple[int, bytes, dict[str, str]]:
    data = None
    headers = {
        "Accept": accept,
        "Cache-Control": "no-store",
        "User-Agent": "nico-authenticated-completed-run-proof",
    }
    if payload is not None:
        data = json.dumps(dict(payload), separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(request, timeout=timeout) as response:
            return (
                int(response.status),
                response.read(),
                {str(key).lower(): str(value) for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        return (
            int(exc.code),
            exc.read(),
            {str(key).lower(): str(value) for key, value in exc.headers.items()},
        )


def _json(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssertionError(code) from exc
    if not isinstance(value, dict):
        raise AssertionError(code)
    return value


def _find_mapping(value: Any, key: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        candidate = value.get(key)
        if isinstance(candidate, Mapping):
            return dict(candidate)
        for nested in value.values():
            found = _find_mapping(nested, key)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_mapping(nested, key)
            if found:
                return found
    return {}


def _find_text(value: Any, key: str) -> str:
    if isinstance(value, Mapping):
        candidate = value.get(key)
        if isinstance(candidate, (str, int)) and str(candidate).strip():
            return str(candidate).strip()
        for nested in value.values():
            found = _find_text(nested, key)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_text(nested, key)
            if found:
                return found
    return ""


def _find_bool(value: Any, key: str) -> bool | None:
    if isinstance(value, Mapping):
        candidate = value.get(key)
        if isinstance(candidate, bool):
            return candidate
        for nested in value.values():
            found = _find_bool(nested, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_bool(nested, key)
            if found is not None:
                return found
    return None


def _status_projection(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": _find_text(payload, "run_id"),
        "repository": _find_text(payload, "repository"),
        "commit_sha": _find_text(payload, "commit_sha").lower(),
        "evidence_ledger_id": _find_text(payload, "evidence_ledger_id"),
        "status": _find_text(payload, "status").lower(),
        "terminal": _find_bool(payload, "terminal"),
        "human_review_required": _find_bool(payload, "human_review_required"),
        "client_delivery_allowed": _find_bool(payload, "client_delivery_allowed"),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    origin = _origin(args.frontend_url)
    expected_sha = str(args.expected_sha).strip().lower()
    handoff = load_source_proof(
        args.source_proof,
        expected_sha=expected_sha,
        repository=args.repository,
        source_workflow_run_id=args.source_workflow_run_id,
        source_workflow_run_attempt=args.source_workflow_run_attempt,
        expected_proof_tool_sha=args.expected_proof_tool_sha,
    )
    run_id = str(handoff["run_id"])
    assessed_commit_sha = str(handoff["assessed_commit_sha"]).lower()

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    oidc_token = request_github_oidc_token()
    exchange_status, exchange_raw, _ = _request(
        opener,
        origin + "/api/nico/github-actions-proof-session",
        accept="application/json",
        method="POST",
        payload={"oidc_token": oidc_token},
    )
    exchange = _json(exchange_raw, "proof_session_exchange_invalid_json")
    if exchange_status != 200 or exchange.get("status") != "authenticated":
        raise AssertionError(f"proof_session_exchange_failed:http_{exchange_status}")
    sessions = [cookie for cookie in cookie_jar if cookie.name == SESSION_COOKIE and cookie.value]
    if len(sessions) != 1:
        raise AssertionError("proof_session_cookie_not_established")
    if str(exchange.get("release_sha") or "").lower() != expected_sha:
        raise AssertionError("proof_session_release_identity_mismatch")

    status_url = origin + f"/api/nico/assessment/comprehensive-run/{urllib.parse.quote(run_id)}"
    report_json_url = status_url + "/report/json"
    report_pdf_url = status_url + "/report/pdf"
    observations: list[dict[str, Any]] = []
    report_digests: list[str] = []
    pdf_digests: list[str] = []
    provenance_observations: list[dict[str, Any]] = []

    for pass_number in (1, 2):
        status_code, status_raw, _ = _request(opener, status_url, accept="application/json")
        if status_code != 200:
            raise AssertionError(f"completed_run_status_unavailable:http_{status_code}")
        status_payload = _json(status_raw, "completed_run_status_invalid_json")
        projection = _status_projection(status_payload)
        if projection["run_id"] != run_id:
            raise AssertionError("completed_run_identity_mismatch")
        if projection["repository"] != args.repository:
            raise AssertionError("completed_run_repository_mismatch")
        if projection["commit_sha"] != assessed_commit_sha:
            raise AssertionError("completed_run_commit_mismatch")
        if projection["human_review_required"] is not True:
            raise AssertionError("completed_run_human_review_boundary_missing")
        if projection["client_delivery_allowed"] is not False:
            raise AssertionError("completed_run_delivery_boundary_missing")
        observations.append({"pass": pass_number, **projection})

        report_status, report_raw, report_headers = _request(
            opener,
            report_json_url,
            accept="application/json",
        )
        if report_status != 200:
            raise AssertionError(f"completed_run_report_json_unavailable:http_{report_status}")
        report_payload = _json(report_raw, "completed_run_report_json_invalid")
        if _find_text(report_payload, "run_id") != run_id:
            raise AssertionError("report_run_identity_mismatch")
        if _find_text(report_payload, "commit_sha").lower() != assessed_commit_sha:
            raise AssertionError("report_commit_identity_mismatch")
        provenance = _find_mapping(report_payload, "nico_release_provenance")
        if provenance.get("backend_build_commit") != expected_sha:
            raise AssertionError("report_backend_release_provenance_mismatch")
        if provenance.get("frontend_build_commit") != expected_sha:
            raise AssertionError("report_frontend_release_provenance_mismatch")
        report_digest = hashlib.sha256(report_raw).hexdigest()
        header_digest = str(report_headers.get("x-nico-canonical-truth-sha256") or "").lower()
        report_digests.append(report_digest)
        provenance_observations.append(
            {
                "pass": pass_number,
                "backend_build_commit": provenance.get("backend_build_commit"),
                "frontend_build_commit": provenance.get("frontend_build_commit"),
                "canonical_truth_header": header_digest,
                "report_json_sha256": report_digest,
            }
        )

        pdf_status, pdf_raw, pdf_headers = _request(
            opener,
            report_pdf_url,
            accept="application/pdf",
        )
        if pdf_status != 200 or not pdf_raw.startswith(b"%PDF"):
            raise AssertionError(f"completed_run_report_pdf_unavailable:http_{pdf_status}")
        pdf_digest = hashlib.sha256(pdf_raw).hexdigest()
        header_pdf_digest = str(pdf_headers.get("x-nico-pdf-sha256") or "").lower()
        if header_pdf_digest and header_pdf_digest != pdf_digest:
            raise AssertionError("report_pdf_digest_header_mismatch")
        pdf_digests.append(pdf_digest)

    if observations[0] != {**observations[1], "pass": 1}:
        first = dict(observations[0]); first.pop("pass", None)
        second = dict(observations[1]); second.pop("pass", None)
        if first != second:
            raise AssertionError("completed_run_status_changed_between_read_only_passes")
    if len(set(report_digests)) != 1:
        raise AssertionError("report_json_changed_between_read_only_passes")
    if len(set(pdf_digests)) != 1:
        raise AssertionError("report_pdf_changed_between_read_only_passes")

    return {
        "artifact_schema": VERSION,
        "status": "passed",
        "frontend_url": origin,
        "expected_sha": expected_sha,
        "repository": args.repository,
        "run_id": run_id,
        "assessed_commit_sha": assessed_commit_sha,
        "source_workflow_run_id": str(args.source_workflow_run_id),
        "source_workflow_run_attempt": str(args.source_workflow_run_attempt),
        "authenticated_production_proof": True,
        "github_actions_proof_session": {
            "authority": exchange.get("authority"),
            "release_sha": exchange.get("release_sha"),
            "workflow_file": exchange.get("workflow_file"),
            "run_id": exchange.get("run_id"),
            "run_attempt": exchange.get("run_attempt"),
            "session_cookie_present": True,
            "session_cookie_value_exposed": False,
            "oidc_token_exposed": False,
        },
        "status_observations": observations,
        "report_provenance_observations": provenance_observations,
        "report_json_sha256": report_digests[0],
        "report_pdf_sha256": pdf_digests[0],
        "read_only_pass_count": 2,
        "status_stable_across_passes": True,
        "report_json_stable_across_passes": True,
        "report_pdf_stable_across_passes": True,
        "exact_release_provenance_verified": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "finished_at_epoch": time.time(),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify one completed NICO run twice through an authenticated production session.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--source-proof", type=Path, required=True)
    parser.add_argument("--source-workflow-run-id", required=True)
    parser.add_argument("--source-workflow-run-attempt", required=True)
    parser.add_argument("--expected-proof-tool-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = run(args)
    except Exception as exc:
        payload = {
            "artifact_schema": VERSION,
            "status": "failed",
            "expected_sha": args.expected_sha,
            "repository": args.repository,
            "error": f"{type(exc).__name__}: {exc}",
            "finished_at_epoch": time.time(),
        }
        args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
