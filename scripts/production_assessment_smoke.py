#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

CONFIRMATION = "I_CONFIRM_AUTHORIZED_PRODUCTION_SMOKE"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
FAILURES = {"blocked", "failed", "error", "rejected", "timed_out", "timeout", "unavailable", "not_found"}
FULL_TOOLS = ["pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog"]
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
DEFAULT_EXPRESS_TIMEOUT_SECONDS = 900.0
Transport = Callable[[str, str, dict[str, Any] | None, dict[str, str], float], tuple[int, Any]]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def origin(value: str, label: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https":
        raise ValueError(f"{label} must use https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label} must be an unauthenticated origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not contain a path, query, or fragment")
    return f"https://{parsed.hostname.lower()}{f':{parsed.port}' if parsed.port else ''}"


def allowed_hosts(value: str) -> frozenset[str]:
    hosts = frozenset(part.strip().lower() for part in str(value or "").split(",") if part.strip())
    if not hosts or any("/" in host or "://" in host or "@" in host for host in hosts):
        raise ValueError("Allowed hosts must be comma-separated bare hostnames")
    return hosts


def validate(config: dict[str, Any]) -> dict[str, Any]:
    if config["confirmation"] != CONFIRMATION:
        raise ValueError("Explicit production-smoke confirmation is required")
    if config["repository"] != config["allowlisted_repository"]:
        raise ValueError("Requested repository does not match the authorized demonstration repository")
    if not REPO_RE.fullmatch(config["repository"]) or not REPO_RE.fullmatch(config["github_repository"]):
        raise ValueError("Repositories must use owner/name form")
    if not config["authorization_reference"]:
        raise ValueError("An authorization reference is required")
    if not SHA_RE.fullmatch(config["commit_sha"]):
        raise ValueError("Commit SHA must be an exact lowercase 40-character SHA")
    if not config["admin_token"] or not config["github_token"]:
        raise ValueError("Required secret credentials are unavailable")
    if not config["customer_id"].startswith("production_smoke_") or not config["project_id"].startswith("production_smoke_"):
        raise ValueError("Production smoke must use an isolated production_smoke tenant")
    for label in ("frontend_origin", "backend_origin"):
        host = (urlparse(config[label]).hostname or "").lower()
        if host not in config["allowed_hosts"]:
            raise ValueError(f"{label} host is not explicitly allowlisted")
    if not 1 <= config["max_polls"] <= 300 or not 0 <= config["poll_interval"] <= 30:
        raise ValueError("Polling limits are outside the safe bounded range")
    if not 5 <= config["request_timeout"] <= 120:
        raise ValueError("General request timeout must be between 5 and 120 seconds")
    if not 120 <= config["express_timeout"] <= 1200:
        raise ValueError("Express start timeout must be between 120 and 1200 seconds")
    return config


def request_json(method: str, url: str, payload: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    safe_headers = {"Accept": "application/json", "User-Agent": "nico-production-smoke/1", **headers}
    if body is not None:
        safe_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=safe_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read(2_000_000)
    except HTTPError as exc:
        status, raw = exc.code, exc.read(2_000_000)
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return 0, {"status": "unavailable", "error_type": type(reason).__name__}
    try:
        return int(status), json.loads(raw.decode()) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return int(status), {"status": "invalid_json", "body_length": len(raw)}


def payload_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return value["detail"] if isinstance(value.get("detail"), dict) else value


def nested(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def first(*values: Any) -> str:
    return next((str(value).strip() for value in values if str(value or "").strip()), "")


def run_id(payload: dict[str, Any]) -> str:
    return first(payload.get("run_id"), nested(payload, "assessment").get("run_id"))


def report_id(payload: dict[str, Any]) -> str:
    return first(payload.get("report_id"), nested(payload, "reports").get("report_id"), nested(payload, "mid_report").get("report_id"), nested(payload, "approval").get("report_id"), nested(payload, "final_review").get("report_id"))


def review_id(payload: dict[str, Any]) -> str:
    return first(payload.get("review_request_id"), nested(payload, "approval_request").get("approval_id"), nested(payload, "approval").get("approval_id"), nested(payload, "final_review").get("approval_id"))


def explicit_bool(payload: dict[str, Any], key: str) -> bool | None:
    for candidate in (payload, nested(payload, "assessment"), nested(payload, "reports")):
        if isinstance(candidate.get(key), bool):
            return candidate[key]
    return None


def progress(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in payload.get("progress") or [] if isinstance(item, dict)]


def failed(payload: dict[str, Any]) -> bool:
    observed = {
        str(payload.get("status") or "").lower(),
        str(payload.get("report_generation_status") or "").lower(),
        str(payload.get("approval_request_status") or "").lower(),
        str(nested(payload, "approval_request").get("status") or "").lower(),
        str(nested(payload, "approval").get("status") or "").lower(),
        *{str(item.get("status") or "").lower() for item in progress(payload)},
    }
    return bool(observed & FAILURES)


def terminal(tier: str, payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    if failed(payload):
        return True
    if tier == "express":
        return bool(payload)
    if tier == "mid":
        report_status = str(payload.get("report_generation_status") or "").lower()
        review_status = str(nested(payload, "approval_request").get("status") or payload.get("approval_request_status") or "").lower()
        return status == "complete" and report_status == "complete" and review_status in {"pending", "pending_review", "requested", "review_required"}
    return status == "complete" and bool(report_id(payload)) and bool(review_id(payload))


def unavailable(payload: dict[str, Any]) -> list[str]:
    notes: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "").strip().replace("\n", " ")[:240]
        if text and text not in notes:
            notes.append(text)

    for source in (payload, nested(payload, "assessment")):
        for key in ("unavailable_data_notes", "limitations", "warnings"):
            for item in source.get(key) or []:
                add(item)
    for item in progress(payload):
        if str(item.get("status") or "").lower() in {"unavailable", "failed", "blocked", "timed_out"}:
            add(item.get("message"))
    return notes[:20]


def common(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": config["repository"], "customer_id": config["customer_id"], "project_id": config["project_id"],
        "client_name": "Authorized Production Smoke", "project_name": "Controlled Demonstration",
        "authorized_by": "github_actions_production_smoke", "authorization_scope": "authorized defensive repository assessment",
        "authorization_confirmed": True, "authorized": True, "timeframe_days": 180, "refresh_full_evidence": True,
    }


def run_tier(tier: str, config: dict[str, Any], transport: Transport = request_json, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    base = common(config)
    if tier == "express":
        start_path, start_payload = "/assessment/github", {**base, "assessment_mode": "express"}
    elif tier == "mid":
        start_path, start_payload = "/assessment/mid-run", {**base, "run_scanners": True, "auto_continue": True}
    elif tier == "full":
        start_path = "/assessment/full-run"
        start_payload = {**base, "mode": "full", "run_scanners": True, "build_reports": True, "create_final_review_request": True, "auto_continue": True, "tools": FULL_TOOLS}
    else:
        raise ValueError(f"Unsupported tier: {tier}")

    headers = {"X-NICO-Admin-Token": config["admin_token"]}
    start_timeout = config["express_timeout"] if tier == "express" else config["request_timeout"]
    started = now()
    start_status, raw = transport("POST", config["backend_origin"] + start_path, start_payload, headers, start_timeout)
    current = payload_dict(raw)
    initial_id = run_id(current)
    continuation_ids: list[str] = []
    status_paths: list[str] = []
    status_codes: list[int] = []

    if tier in {"mid", "full"} and initial_id:
        status_path = f"/assessment/{tier}-run/{initial_id}/status"
        for _ in range(config["max_polls"]):
            sleep(config["poll_interval"])
            status_payload = {**base, "auto_continue": True, "run_scanners": True, "scan_id": first(nested(current, "scanner").get("scan_id"), nested(current, "scanner_evidence").get("scan_id"))}
            if tier == "full":
                status_payload.update({"mode": "full", "build_reports": True, "create_final_review_request": True, "tools": FULL_TOOLS})
            code, raw = transport("POST", config["backend_origin"] + status_path, status_payload, headers, config["request_timeout"])
            status_paths.append(status_path)
            status_codes.append(code)
            candidate = payload_dict(raw)
            if run_id(candidate):
                continuation_ids.append(run_id(candidate))
            if candidate:
                current = candidate
            if terminal(tier, current):
                break

    final_id = run_id(current) or initial_id
    exact = True
    if tier in {"mid", "full"}:
        exact = bool(initial_id and status_paths and continuation_ids and final_id == initial_id and all(item == initial_id for item in continuation_ids) and all(path.endswith(f"/{initial_id}/status") for path in status_paths))
    rid, vid = report_id(current), review_id(current)
    human, client = explicit_bool(current, "human_review_required"), explicit_bool(current, "client_ready")
    identities = bool(rid) and (tier == "express" or bool(vid))
    passed = 200 <= start_status < 300 and terminal(tier, current) and not failed(current) and identities and human is True and client is False and (tier == "express" or exact)
    return {
        "tier": tier, "status": "passed" if passed else "failed", "assessment_terminal_status": str(current.get("status") or "unknown"),
        "start_count": 1, "start_http_status": start_status, "start_timeout_seconds": start_timeout, "started_at": started, "finished_at": now(),
        "run_id": final_id, "initial_run_id": initial_id, "continuation_run_ids": list(dict.fromkeys(continuation_ids)),
        "continuation_status_paths": status_paths, "continuation_http_statuses": status_codes,
        "polled_single_exact_status_url": exact, "report_id": rid, "review_request_id": vid,
        "human_review_required": human, "client_ready": client, "unavailable_or_failed_evidence": unavailable(current),
    }


def deployment(config: dict[str, Any], transport: Transport = request_json) -> dict[str, Any]:
    code, raw = transport("GET", f"https://api.github.com/repos/{config['github_repository']}/commits/{config['commit_sha']}/status", None, {"Authorization": f"Bearer {config['github_token']}", "X-GitHub-Api-Version": "2022-11-28"}, config["request_timeout"])
    observed: dict[str, str] = {}
    for item in payload_dict(raw).get("statuses") or []:
        if isinstance(item, dict) and item.get("context") not in observed:
            observed[str(item.get("context") or "")] = str(item.get("state") or "unknown")
    required = {"frontend": config["frontend_status_context"], "backend": config["backend_status_context"]}
    return {"http_status": code, "commit_sha": config["commit_sha"], "required_contexts": required, "observed_contexts": {value: observed.get(value, "missing") for value in required.values()}, "verified": code == 200 and all(observed.get(value) == "success" for value in required.values())}


def preflight(config: dict[str, Any], transport: Transport = request_json) -> dict[str, Any]:
    front_code, _ = transport("GET", config["frontend_origin"] + "/assessment", None, {}, config["request_timeout"])
    health_code, raw = transport("GET", config["backend_origin"] + "/health", None, {"X-NICO-Admin-Token": config["admin_token"]}, config["request_timeout"])
    health = payload_dict(raw)
    return {
        "frontend": {"origin": config["frontend_origin"], "assessment_http_status": front_code},
        "backend": {"origin": config["backend_origin"], "health_http_status": health_code, "health_status": str(health.get("status") or "unknown"), "system": str(health.get("system") or "")},
        "verified": 200 <= front_code < 400 and health_code == 200 and health.get("status") == "ok",
    }


def artifact(config: dict[str, Any], deploy: dict[str, Any], ready: dict[str, Any], tiers: list[dict[str, Any]]) -> dict[str, Any]:
    proof = {
        "one_start_per_tier": len(tiers) == 3 and all(item.get("start_count") == 1 for item in tiers),
        "exact_run_continuation": all(item.get("polled_single_exact_status_url") is True for item in tiers if item.get("tier") in {"mid", "full"}),
        "human_review_boundary_preserved": all(item.get("human_review_required") is True for item in tiers),
        "no_client_ready_claim": all(item.get("client_ready") is False for item in tiers),
    }
    passed = deploy.get("verified") is True and ready.get("verified") is True and len(tiers) == 3 and all(proof.values()) and all(item.get("status") == "passed" for item in tiers)
    return {
        "schema_version": 1, "evidence_kind": "authorized_live_production_smoke", "live_claim": True,
        "authorization_confirmed": True, "status": "passed" if passed else "failed", "generated_at": now(),
        "source_commit_sha": config["commit_sha"], "authorization_reference_sha256": hashlib.sha256(config["authorization_reference"].encode()).hexdigest(),
        "repository": config["repository"], "tenant": {"customer_id": config["customer_id"], "project_id": config["project_id"]},
        "deployment": deploy, "preflight": ready, "proof": proof, "tiers": tiers,
        "limitations": [
            "The workflow sends exactly one start request per tier and does not issue a second start as a destructive duplicate probe.",
            "This artifact records defensive assessment behavior only; it does not approve, deliver, repair, or modify production code.",
            "A passed artifact remains subject to human review and does not establish that all defects are absent.",
        ],
    }


def markdown(result: dict[str, Any]) -> str:
    lines = ["# NICO Authorized Production Assessment Smoke", "", f"- Status: `{result['status']}`", f"- Commit: `{result['source_commit_sha']}`", f"- Repository: `{result['repository']}`", f"- Generated: `{result['generated_at']}`", "- Human review remains required.", "- Client delivery and production changes were not authorized.", "", "## Tier evidence", "", "| Tier | Proof | Run ID | Report ID | Review request ID | Human review | Client ready |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in result.get("tiers") or []:
        lines.append(f"| {item.get('tier')} | {item.get('status')} | `{item.get('run_id') or 'unavailable'}` | `{item.get('report_id') or 'unavailable'}` | `{item.get('review_request_id') or 'unavailable'}` | {item.get('human_review_required')} | {item.get('client_ready')} |")
    return "\n".join(lines + ["", "## Limitations", "", *[f"- {item}" for item in result["limitations"]], ""])


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one guarded production assessment per NICO tier.")
    for name in ("frontend-url", "backend-url", "repository", "allowlisted-repository", "allowed-hosts", "authorization-reference", "confirmation", "commit-sha", "github-repository", "backend-status-context"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--customer-id", default="production_smoke_customer")
    parser.add_argument("--project-id", default="production_smoke_project")
    parser.add_argument("--frontend-status-context", default="Vercel")
    parser.add_argument("--output-json", default="audit-results/production-assessment-smoke.json")
    parser.add_argument("--output-markdown", default="audit-results/production-assessment-smoke.md")
    parser.add_argument("--max-polls", type=int, default=200)
    parser.add_argument("--poll-interval-seconds", type=float, default=3.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--express-timeout-seconds", type=float, default=DEFAULT_EXPRESS_TIMEOUT_SECONDS)
    return parser.parse_args(argv)


def config_from(args: argparse.Namespace) -> dict[str, Any]:
    return validate({
        "frontend_origin": origin(args.frontend_url, "frontend URL"), "backend_origin": origin(args.backend_url, "backend URL"),
        "repository": args.repository.strip(), "allowlisted_repository": args.allowlisted_repository.strip(), "allowed_hosts": allowed_hosts(args.allowed_hosts),
        "customer_id": args.customer_id.strip(), "project_id": args.project_id.strip(), "authorization_reference": args.authorization_reference.strip(),
        "confirmation": args.confirmation, "commit_sha": args.commit_sha.strip().lower(), "github_repository": args.github_repository.strip(),
        "frontend_status_context": args.frontend_status_context.strip(), "backend_status_context": args.backend_status_context.strip(),
        "admin_token": os.environ.get("NICO_PRODUCTION_SMOKE_ADMIN_TOKEN", ""), "github_token": os.environ.get("GITHUB_TOKEN", ""),
        "output_json": Path(args.output_json), "output_markdown": Path(args.output_markdown), "max_polls": args.max_polls,
        "poll_interval": args.poll_interval_seconds, "request_timeout": args.request_timeout_seconds, "express_timeout": args.express_timeout_seconds,
    })


def main(argv: list[str] | None = None) -> int:
    config = config_from(parse(argv))
    deploy, ready = deployment(config), preflight(config)
    tiers = [run_tier(tier, config) for tier in ("express", "mid", "full")] if deploy["verified"] and ready["verified"] else []
    result = artifact(config, deploy, ready, tiers)
    config["output_json"].parent.mkdir(parents=True, exist_ok=True)
    config["output_markdown"].parent.mkdir(parents=True, exist_ok=True)
    config["output_json"].write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config["output_markdown"].write_text(markdown(result), encoding="utf-8")
    print(f"Production assessment smoke status: {result['status']}")
    print(f"Evidence written to: {config['output_json']}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
