from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

CONFIRMATION = "RUN AUTHORIZED NICO PRODUCTION SMOKE"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
START_PATHS = {
    "express": "/assessment/github",
    "mid": "/assessment/mid-run",
    "full": "/assessment/full-run",
}
STATUS_PATHS = {
    "mid": "/assessment/mid-run/{run_id}/status",
    "full": "/assessment/full-run/{run_id}/status",
}
FULL_TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
]
TERMINAL_FAILURES = {"blocked", "failed", "error", "rejected", "timed_out", "timeout"}


class SmokeError(RuntimeError):
    pass


@dataclass(frozen=True)
class SmokeConfig:
    frontend_url: str
    backend_url: str
    repository: str
    customer_id: str
    project_id: str
    frontend_commit: str
    backend_commit: str
    confirmation: str
    expected_frontend_url: str
    expected_backend_url: str
    expected_repository: str
    admin_token: str
    poll_seconds: float = 3.0
    max_polls: int = 200


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_origin(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise SmokeError("Production URLs must be absolute HTTPS origins.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SmokeError("Production URLs must not contain credentials, queries, or fragments.")
    if parsed.path not in {"", "/"}:
        raise SmokeError("Production URLs must be origins without a path.")
    host = parsed.hostname.lower()
    port = parsed.port
    netloc = host if port in {None, 443} else f"{host}:{port}"
    return urlunsplit(("https", netloc, "", "", ""))


def validate_config(config: SmokeConfig) -> SmokeConfig:
    frontend = canonical_origin(config.frontend_url)
    backend = canonical_origin(config.backend_url)
    expected_frontend = canonical_origin(config.expected_frontend_url)
    expected_backend = canonical_origin(config.expected_backend_url)
    if frontend != expected_frontend:
        raise SmokeError("Frontend URL does not match the configured production allowlist.")
    if backend != expected_backend:
        raise SmokeError("Backend URL does not match the configured production allowlist.")
    repository = config.repository.strip()
    if not repository or repository != config.expected_repository.strip():
        raise SmokeError("Repository does not match the configured authorized demonstration repository.")
    if config.confirmation != CONFIRMATION:
        raise SmokeError(f"Operator confirmation must exactly equal: {CONFIRMATION}")
    if not config.admin_token:
        raise SmokeError("NICO_PRODUCTION_SMOKE_ADMIN_TOKEN is not configured.")
    if not HEX_SHA.fullmatch(config.frontend_commit.strip().lower()):
        raise SmokeError("Frontend deployment commit must be a 40-character lowercase hexadecimal SHA.")
    if not HEX_SHA.fullmatch(config.backend_commit.strip().lower()):
        raise SmokeError("Backend deployment commit must be a 40-character lowercase hexadecimal SHA.")
    if config.max_polls < 1 or config.max_polls > 400:
        raise SmokeError("max_polls must be between 1 and 400.")
    if config.poll_seconds < 0.1 or config.poll_seconds > 30:
        raise SmokeError("poll_seconds must be between 0.1 and 30 seconds.")
    return SmokeConfig(
        frontend_url=frontend,
        backend_url=backend,
        repository=repository,
        customer_id=config.customer_id.strip() or "nico_production_smoke",
        project_id=config.project_id.strip() or "nico_production_smoke",
        frontend_commit=config.frontend_commit.strip().lower(),
        backend_commit=config.backend_commit.strip().lower(),
        confirmation=config.confirmation,
        expected_frontend_url=expected_frontend,
        expected_backend_url=expected_backend,
        expected_repository=config.expected_repository.strip(),
        admin_token=config.admin_token,
        poll_seconds=config.poll_seconds,
        max_polls=config.max_polls,
    )


def bounded_text(value: Any, limit: int = 500) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def report_id(tier: str, payload: dict[str, Any]) -> str:
    candidates = [
        nested(payload, "reports", "report_id"),
        nested(payload, "mid_report", "report_id"),
        payload.get("report_id"),
        nested(payload, "approval", "report_id"),
    ]
    return next((bounded_text(item, 160) for item in candidates if bounded_text(item, 160)), "")


def review_request_id(tier: str, payload: dict[str, Any]) -> str:
    candidates = [
        nested(payload, "approval_request", "approval_id"),
        nested(payload, "approval", "approval_id"),
        payload.get("review_request_id"),
    ]
    return next((bounded_text(item, 160) for item in candidates if bounded_text(item, 160)), "")


def progress_evidence(payload: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for value in payload.get("progress") or []:
        if not isinstance(value, dict):
            continue
        status = bounded_text(value.get("status"), 80).lower()
        if status in {"unavailable", "failed", "blocked", "timed_out", "timeout", "error", "skipped"}:
            items.append(
                {
                    "step": bounded_text(value.get("step"), 120),
                    "status": status,
                    "message": bounded_text(value.get("message"), 500),
                }
            )
    return items[:50]


def human_review_required(payload: dict[str, Any]) -> bool:
    values = [
        payload.get("human_review_required"),
        nested(payload, "assessment", "human_review_required"),
        nested(payload, "mid_report", "human_review_required"),
        nested(payload, "reports", "human_review_required"),
    ]
    return any(value is True for value in values)


def client_ready(payload: dict[str, Any]) -> bool:
    values = [
        payload.get("client_ready"),
        nested(payload, "assessment", "client_ready"),
        nested(payload, "mid_report", "client_delivery_allowed"),
        nested(payload, "reports", "client_delivery_allowed"),
    ]
    return any(value is True for value in values)


def is_stable(tier: str, payload: dict[str, Any]) -> bool:
    status = bounded_text(payload.get("status"), 80).lower()
    if status in TERMINAL_FAILURES:
        return True
    if tier == "express":
        return True
    if tier == "mid":
        return status == "complete" and bool(report_id(tier, payload)) and bool(review_request_id(tier, payload))
    return status == "complete" and bool(report_id(tier, payload)) and bool(review_request_id(tier, payload))


def tier_summary(
    tier: str,
    payload: dict[str, Any],
    *,
    start_count: int,
    continuation_run_ids: list[str],
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    run_id = bounded_text(payload.get("run_id"), 160)
    exact_continuation = tier == "express" or bool(run_id) and all(item == run_id for item in continuation_run_ids)
    review_required = human_review_required(payload)
    delivery_blocked = not client_ready(payload)
    rid = report_id(tier, payload)
    review_id = review_request_id(tier, payload)
    terminal_status = bounded_text(payload.get("status"), 80).lower() or "unknown"
    required_ids = bool(rid) and (tier == "express" or bool(review_id))
    passed = (
        start_count == 1
        and exact_continuation
        and review_required
        and delivery_blocked
        and terminal_status not in TERMINAL_FAILURES
        and required_ids
    )
    return {
        "tier": tier,
        "status": "passed" if passed else "failed",
        "terminal_status": terminal_status,
        "start_count": start_count,
        "run_id": run_id,
        "continuation_run_ids": continuation_run_ids,
        "polled_single_exact_status_url": exact_continuation,
        "report_id": rid,
        "review_request_id": review_id,
        "human_review_required": review_required,
        "client_ready": not delivery_blocked,
        "started_at": started_at,
        "finished_at": finished_at,
        "scanner_evidence": progress_evidence(payload),
    }


class ProductionSmokeRunner:
    def __init__(self, config: SmokeConfig) -> None:
        self.config = validate_config(config)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "NICO-controlled-production-smoke/1"})
        self.start_counts = {tier: 0 for tier in START_PATHS}

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            raise SmokeError("Internal smoke-test path must be absolute.")
        return f"{self.config.backend_url}{path}"

    def _json_request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(
            method,
            self._url(path),
            json=payload,
            timeout=90,
            allow_redirects=False,
        )
        if response.is_redirect:
            raise SmokeError(f"Redirects are blocked for production API requests ({path}).")
        try:
            body = response.json()
        except ValueError as exc:
            raise SmokeError(f"Production API returned non-JSON data for {path} ({response.status_code}).") from exc
        if not response.ok:
            detail = body.get("detail") if isinstance(body, dict) else None
            message = detail.get("message") if isinstance(detail, dict) else None
            raise SmokeError(f"Production API request failed for {path} ({response.status_code}): {bounded_text(message or 'bounded detail unavailable')}")
        if not isinstance(body, dict):
            raise SmokeError(f"Production API returned an invalid JSON object for {path}.")
        return body

    def verify_deployment_surfaces(self) -> dict[str, Any]:
        frontend = self.session.get(self.config.frontend_url, timeout=30, allow_redirects=False)
        if frontend.is_redirect or not frontend.ok:
            raise SmokeError(f"Production frontend did not return a direct successful response ({frontend.status_code}).")
        health = self._json_request("GET", "/health")
        if health.get("status") != "ok" or health.get("system") != "NICO":
            raise SmokeError("Production backend health response did not identify a healthy NICO service.")
        diagnostic = self.session.get(
            self._url("/diagnostics/backend-config"),
            headers={"X-NICO-Admin-Token": self.config.admin_token},
            timeout=30,
            allow_redirects=False,
        )
        if diagnostic.is_redirect or not diagnostic.ok:
            raise SmokeError(f"Read-only backend diagnostics check failed ({diagnostic.status_code}).")
        return {
            "frontend_status": frontend.status_code,
            "backend_health_status": health.get("status"),
            "backend_system": health.get("system"),
            "diagnostics_status": diagnostic.status_code,
        }

    def _common_payload(self) -> dict[str, Any]:
        return {
            "repository": self.config.repository,
            "customer_id": self.config.customer_id,
            "project_id": self.config.project_id,
            "client_name": "NICO controlled production smoke",
            "project_name": "NICO controlled production smoke",
            "authorized_by": "github_actions_production_smoke_operator",
            "authorization_scope": "authorized defensive repository assessment",
            "authorization_confirmed": True,
            "authorized": True,
            "timeframe_days": 180,
            "refresh_full_evidence": True,
        }

    def run_tier(self, tier: str) -> dict[str, Any]:
        if tier not in START_PATHS:
            raise SmokeError(f"Unsupported tier: {tier}")
        if self.start_counts[tier] != 0:
            raise SmokeError(f"Duplicate start attempt blocked for {tier}.")
        payload = self._common_payload()
        if tier == "express":
            payload["assessment_mode"] = "express"
        elif tier == "mid":
            payload.update({"run_scanners": True, "auto_continue": True})
        else:
            payload.update(
                {
                    "mode": "full",
                    "run_scanners": True,
                    "build_reports": True,
                    "create_final_review_request": True,
                    "auto_continue": True,
                    "tools": FULL_TOOLS,
                }
            )

        started_at = utc_now()
        self.start_counts[tier] += 1
        current = self._json_request("POST", START_PATHS[tier], payload)
        continuation_ids: list[str] = []
        if tier != "express":
            run_id = bounded_text(current.get("run_id"), 160)
            if not run_id:
                raise SmokeError(f"{tier.title()} start response did not include a run ID.")
            status_path = STATUS_PATHS[tier].format(run_id=run_id)
            for _ in range(self.config.max_polls):
                if is_stable(tier, current):
                    break
                time.sleep(self.config.poll_seconds)
                status_payload = self._common_payload()
                status_payload.update({"auto_continue": True, "run_scanners": True})
                if tier == "full":
                    status_payload.update(
                        {
                            "mode": "full",
                            "build_reports": True,
                            "create_final_review_request": True,
                            "tools": FULL_TOOLS,
                        }
                    )
                current = self._json_request("POST", status_path, status_payload)
                observed = bounded_text(current.get("run_id"), 160)
                continuation_ids.append(observed)
                if observed != run_id:
                    raise SmokeError(f"{tier.title()} continuation changed exact run identity.")
            else:
                raise SmokeError(f"{tier.title()} continuation exceeded the bounded polling limit.")

        return tier_summary(
            tier,
            current,
            start_count=self.start_counts[tier],
            continuation_run_ids=continuation_ids,
            started_at=started_at,
            finished_at=utc_now(),
        )

    def run(self) -> dict[str, Any]:
        started_at = utc_now()
        surfaces = self.verify_deployment_surfaces()
        tiers = [self.run_tier(tier) for tier in ("express", "mid", "full")]
        proof = {
            "one_start_per_tier": all(item["start_count"] == 1 for item in tiers),
            "exact_run_continuation": all(item["polled_single_exact_status_url"] is True for item in tiers),
            "human_review_boundary_preserved": all(item["human_review_required"] is True for item in tiers),
            "no_client_ready_claim": all(item["client_ready"] is False for item in tiers),
        }
        passed = all(item["status"] == "passed" for item in tiers) and all(proof.values())
        return {
            "schema_version": 1,
            "evidence_kind": "authorized_live_production_smoke",
            "live_claim": True,
            "authorization_confirmed": True,
            "status": "passed" if passed else "failed",
            "started_at": started_at,
            "finished_at": utc_now(),
            "deployment": {
                "frontend_origin": self.config.frontend_url,
                "backend_origin": self.config.backend_url,
                "frontend_commit": self.config.frontend_commit,
                "backend_commit": self.config.backend_commit,
                "surfaces": surfaces,
            },
            "scope": {
                "repository": self.config.repository,
                "customer_id": self.config.customer_id,
                "project_id": self.config.project_id,
            },
            "proof": proof,
            "tiers": tiers,
            "prohibited_actions": {
                "approval_transition_attempted": False,
                "client_delivery_attempted": False,
                "repair_attempted": False,
                "production_change_attempted": False,
            },
            "human_review_required": True,
        }


def config_from_args(args: argparse.Namespace) -> SmokeConfig:
    return SmokeConfig(
        frontend_url=args.frontend_url,
        backend_url=args.backend_url,
        repository=args.repository,
        customer_id=args.customer_id,
        project_id=args.project_id,
        frontend_commit=args.frontend_commit,
        backend_commit=args.backend_commit,
        confirmation=args.confirmation,
        expected_frontend_url=os.getenv("NICO_PRODUCTION_FRONTEND_URL", ""),
        expected_backend_url=os.getenv("NICO_PRODUCTION_BACKEND_URL", ""),
        expected_repository=os.getenv("NICO_PRODUCTION_SMOKE_REPOSITORY", ""),
        admin_token=os.getenv("NICO_PRODUCTION_SMOKE_ADMIN_TOKEN", ""),
        poll_seconds=args.poll_seconds,
        max_polls=args.max_polls,
    )


def write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one controlled production assessment per NICO tier.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--frontend-commit", required=True)
    parser.add_argument("--backend-commit", required=True)
    parser.add_argument("--confirmation", required=True)
    parser.add_argument("--output", default="audit-results/production-assessment-smoke.json")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-polls", type=int, default=200)
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        artifact = ProductionSmokeRunner(config_from_args(args)).run()
        write_artifact(output, artifact)
        return 0 if artifact.get("status") == "passed" else 1
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "evidence_kind": "authorized_live_production_smoke",
            "live_claim": True,
            "authorization_confirmed": args.confirmation == CONFIRMATION,
            "status": "failed",
            "started_at": utc_now(),
            "finished_at": utc_now(),
            "error": bounded_text(exc, 800),
            "human_review_required": True,
            "prohibited_actions": {
                "approval_transition_attempted": False,
                "client_delivery_attempted": False,
                "repair_attempted": False,
                "production_change_attempted": False,
            },
        }
        write_artifact(output, failure)
        print(f"Production smoke failed: {failure['error']}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
