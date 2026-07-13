from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen


class SmokeFailure(RuntimeError):
    """Raised when production smoke evidence cannot be proved truthfully."""


@dataclass(frozen=True)
class TierSpec:
    name: str
    start_path: str
    status_path: str | None
    expected_mode: str
    requires_run_id: bool


@dataclass(frozen=True)
class SmokeConfig:
    api_url: str
    repository: str
    customer_id: str
    project_id: str
    authorized_by: str
    authorization_scope: str
    request_timeout_seconds: float = 45.0
    poll_interval_seconds: float = 5.0
    max_polls: int = 60


TIER_SPECS: dict[str, TierSpec] = {
    "express": TierSpec(
        name="express",
        start_path="/assessment/github",
        status_path=None,
        expected_mode="express",
        requires_run_id=False,
    ),
    "mid": TierSpec(
        name="mid",
        start_path="/assessment/mid-run",
        status_path="/assessment/mid-run/{run_id}/status",
        expected_mode="mid",
        requires_run_id=True,
    ),
    "full": TierSpec(
        name="full",
        start_path="/assessment/full-run",
        status_path="/assessment/full-run/{run_id}/status",
        expected_mode="full",
        requires_run_id=True,
    ),
}

PENDING_STATUSES = {
    "queued",
    "running",
    "pending",
    "in_progress",
    "planned",
    "continuing",
    "collecting",
}
FAILURE_STATUSES = {
    "blocked",
    "error",
    "failed",
    "failure",
    "unavailable",
    "not_found",
    "rejected",
}
SUCCESS_STATUSES = {
    "complete",
    "completed",
    "ok",
    "partial",
    "human_review_required",
    "pending_review",
    "ready_for_review",
    "accepted",
}

RequestJson = Callable[[str, str, dict[str, Any] | None, float], dict[str, Any]]
Sleep = Callable[[float], None]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_base_url(value: str, *, allow_http: bool = False) -> str:
    text = str(value or "").strip().rstrip("/")
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        raise SmokeFailure("A complete API URL is required.")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (
        allow_http and parsed.scheme == "http" and parsed.hostname in local_hosts
    ):
        raise SmokeFailure("Production smoke targets must use HTTPS. HTTP is allowed only for explicit localhost testing.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SmokeFailure("API and frontend URLs must not contain credentials, query strings, or fragments.")
    return text


def join_url(base_url: str, path: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def response_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def response_identity(payload: dict[str, Any]) -> str:
    for key in ("run_id", "assessment_id", "report_id", "generated_at"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    for key in ("run_id", "assessment_id", "report_id", "generated_at"):
        value = str(assessment.get(key) or "").strip()
        if value:
            return value
    return ""


def response_run_id(payload: dict[str, Any]) -> str:
    direct = str(payload.get("run_id") or "").strip()
    if direct:
        return direct
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    return str(assessment.get("run_id") or "").strip()


def response_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def safe_error_summary(payload: dict[str, Any]) -> str:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        for key in ("message", "code", "status"):
            value = str(detail.get(key) or "").strip()
            if value:
                return value[:240]
    for key in ("message", "code", "status"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value[:240]
    return "No safe error summary was returned."


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {}
        summary = safe_error_summary(parsed if isinstance(parsed, dict) else {})
        raise SmokeFailure(f"{method.upper()} request returned HTTP {exc.code}: {summary}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SmokeFailure(f"{method.upper()} request could not reach the configured endpoint: {type(exc).__name__}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SmokeFailure("Endpoint returned a non-JSON response.") from exc
    if not isinstance(parsed, dict):
        raise SmokeFailure("Endpoint returned JSON that was not an object.")
    return parsed


def request_frontend(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, method="GET", headers={"Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(getattr(response, "status", 200))
            body = response.read(1_000_000).decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise SmokeFailure(f"Frontend assessment page returned HTTP {exc.code}.") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SmokeFailure(f"Frontend assessment page was unreachable: {type(exc).__name__}") from exc

    required_labels = ("Express", "Mid", "Full")
    missing = [label for label in required_labels if label not in body]
    if status_code != 200 or missing:
        raise SmokeFailure(
            f"Frontend assessment page proof failed: status={status_code}, missing_labels={','.join(missing) or 'none'}."
        )
    return {
        "status": "passed",
        "http_status": status_code,
        "required_labels": list(required_labels),
        "response_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def base_payload(config: SmokeConfig) -> dict[str, Any]:
    return {
        "repository": config.repository,
        "target": config.repository,
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": config.authorized_by,
        "authorization_scope": config.authorization_scope,
        "customer_id": config.customer_id,
        "project_id": config.project_id,
        "client_name": "NICO authorized production smoke",
        "project_name": "NICO production assessment proof",
    }


def start_payload(tier: str, config: SmokeConfig) -> dict[str, Any]:
    payload = base_payload(config)
    if tier == "express":
        payload.update({"assessment_mode": "express", "timeframe_days": 30})
    elif tier == "mid":
        payload.update(
            {
                "timeframe_days": 30,
                "run_scanners": True,
                "refresh_full_evidence": True,
                "auto_continue": True,
                "tools": [],
            }
        )
    elif tier == "full":
        payload.update(
            {
                "mode": "full",
                "timeframe_days": 30,
                "run_scanners": True,
                "refresh_full_evidence": True,
                "build_reports": True,
                "create_final_review_request": True,
                "auto_continue": True,
                "tools": [],
            }
        )
    else:  # pragma: no cover - guarded by parse_tiers
        raise SmokeFailure(f"Unsupported tier: {tier}")
    return payload


def status_payload(tier: str, config: SmokeConfig, initial: dict[str, Any]) -> dict[str, Any]:
    payload = base_payload(config)
    payload.update(
        {
            "timeframe_days": 30,
            "auto_continue": True,
            "run_scanners": True,
            "refresh_full_evidence": True,
        }
    )
    if tier == "full":
        payload.update(
            {
                "mode": "full",
                "scan_id": str(initial.get("scan_id") or ""),
                "build_reports": True,
                "create_final_review_request": True,
                "tools": [],
            }
        )
    elif tier == "mid":
        payload["tools"] = []
    return payload


def mode_values(payload: dict[str, Any]) -> list[str]:
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    values: list[str] = []
    for candidate in (
        payload.get("mode"),
        payload.get("assessment_mode"),
        payload.get("assessment_type"),
        payload.get("service_tier"),
        payload.get("report_path"),
        assessment.get("mode"),
        assessment.get("assessment_mode"),
        assessment.get("assessment_type"),
        assessment.get("service_tier"),
        assessment.get("report_path"),
    ):
        value = str(candidate or "").strip().lower()
        if value and value not in values:
            values.append(value)
    return values


def validate_mode(tier: str, payload: dict[str, Any]) -> None:
    aliases = {
        "express": {"express"},
        "mid": {"mid", "mid_run"},
        "full": {"full", "full_run"},
    }
    observed = mode_values(payload)
    conflicts = [value for value in observed if value in {"express", "mid", "mid_run", "full", "full_run"} and value not in aliases[tier]]
    if conflicts:
        raise SmokeFailure(
            f"{tier.title()} response contained conflicting tier metadata: {', '.join(conflicts)}."
        )


def validate_terminal_response(tier: str, payload: dict[str, Any]) -> None:
    status = response_status(payload)
    if status in FAILURE_STATUSES:
        raise SmokeFailure(f"{tier.title()} ended with status={status}: {safe_error_summary(payload)}")
    if status in PENDING_STATUSES:
        raise SmokeFailure(f"{tier.title()} remained pending after the bounded polling window.")
    if status and status not in SUCCESS_STATUSES:
        raise SmokeFailure(f"{tier.title()} returned an unrecognized terminal status={status}.")
    if not response_identity(payload):
        raise SmokeFailure(f"{tier.title()} response did not provide a run, assessment, report, or generation identity.")
    validate_mode(tier, payload)


def run_tier(
    tier: str,
    config: SmokeConfig,
    *,
    requester: RequestJson = request_json,
    sleeper: Sleep = time.sleep,
) -> dict[str, Any]:
    spec = TIER_SPECS[tier]
    start_url = join_url(config.api_url, spec.start_path)
    start = requester("POST", start_url, start_payload(tier, config), config.request_timeout_seconds)
    start_status = response_status(start)
    if start_status in FAILURE_STATUSES:
        raise SmokeFailure(f"{tier.title()} start failed with status={start_status}: {safe_error_summary(start)}")

    identity = response_identity(start)
    run_id = response_run_id(start)
    if spec.requires_run_id and not run_id:
        raise SmokeFailure(f"{tier.title()} start response did not return the exact run_id required for continuation.")
    if not identity:
        raise SmokeFailure(f"{tier.title()} start response did not return a stable identity.")
    validate_mode(tier, start)

    final = start
    poll_count = 0
    polled_urls: list[str] = []
    if spec.status_path is not None:
        status_url = join_url(config.api_url, spec.status_path.format(run_id=quote(run_id, safe="")))
        for attempt in range(1, config.max_polls + 1):
            poll_count += 1
            polled_urls.append(status_url)
            current = requester(
                "POST",
                status_url,
                status_payload(tier, config, start),
                config.request_timeout_seconds,
            )
            current_run_id = response_run_id(current)
            if current_run_id and current_run_id != run_id:
                raise SmokeFailure(
                    f"{tier.title()} continuation changed run identity from {run_id} to {current_run_id}."
                )
            final = current
            current_status = response_status(current)
            if current_status in FAILURE_STATUSES:
                raise SmokeFailure(
                    f"{tier.title()} continuation failed with status={current_status}: {safe_error_summary(current)}"
                )
            if current_status not in PENDING_STATUSES:
                break
            if attempt < config.max_polls:
                sleeper(config.poll_interval_seconds)

    validate_terminal_response(tier, final)
    final_run_id = response_run_id(final)
    if run_id and final_run_id and final_run_id != run_id:
        raise SmokeFailure(f"{tier.title()} final response did not preserve exact run identity.")

    return {
        "tier": tier,
        "status": "passed",
        "start_count": 1,
        "poll_count": poll_count,
        "identity": identity,
        "run_id": run_id,
        "start_status": start_status or "unspecified",
        "final_status": response_status(final) or "unspecified",
        "start_path": spec.start_path,
        "status_path": spec.status_path or "",
        "polled_single_exact_status_url": len(set(polled_urls)) <= 1,
        "final_response_sha256": response_hash(final),
        "human_review_required": bool(final.get("human_review_required", True)),
        "client_ready": bool(final.get("client_ready", False)),
    }


def parse_tiers(value: str) -> list[str]:
    requested = [item.strip().lower() for item in str(value or "").split(",") if item.strip()]
    if not requested:
        raise SmokeFailure("At least one tier is required.")
    unknown = [item for item in requested if item not in TIER_SPECS]
    if unknown:
        raise SmokeFailure(f"Unsupported tier selection: {', '.join(unknown)}")
    result: list[str] = []
    for item in requested:
        if item not in result:
            result.append(item)
    return result


def run_smoke(
    config: SmokeConfig,
    tiers: list[str],
    *,
    authorization_confirmed: bool,
    frontend_url: str = "",
    requester: RequestJson = request_json,
    sleeper: Sleep = time.sleep,
    frontend_requester: Callable[[str, float], dict[str, Any]] = request_frontend,
) -> dict[str, Any]:
    if not authorization_confirmed:
        raise SmokeFailure("Explicit authorization confirmation is required before production assessment smoke execution.")
    if not config.repository.strip():
        raise SmokeFailure("An explicitly authorized repository is required.")

    started_at = utc_now()
    frontend_evidence: dict[str, Any] = {"status": "not_requested"}
    if frontend_url:
        frontend_evidence = frontend_requester(
            join_url(frontend_url, "/assessment"),
            config.request_timeout_seconds,
        )

    tier_results = [
        run_tier(tier, config, requester=requester, sleeper=sleeper)
        for tier in tiers
    ]
    finished_at = utc_now()
    return {
        "schema_version": 1,
        "evidence_kind": "authorized_live_production_smoke",
        "live_claim": True,
        "authorization_confirmed": True,
        "authorization_scope": config.authorization_scope,
        "repository": config.repository,
        "customer_id": config.customer_id,
        "project_id": config.project_id,
        "api_origin": config.api_url,
        "frontend_origin": frontend_url,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": "passed",
        "frontend": frontend_evidence,
        "tiers": tier_results,
        "proof": {
            "one_start_per_tier": all(item["start_count"] == 1 for item in tier_results),
            "exact_run_continuation": all(
                item["polled_single_exact_status_url"] for item in tier_results if item["tier"] in {"mid", "full"}
            ),
            "human_review_boundary_preserved": all(item["human_review_required"] for item in tier_results),
            "no_client_ready_claim": all(not item["client_ready"] for item in tier_results),
        },
        "config": {
            "request_timeout_seconds": config.request_timeout_seconds,
            "poll_interval_seconds": config.poll_interval_seconds,
            "max_polls": config.max_polls,
        },
    }


def write_evidence(path: str, evidence: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one authorized, exact-identity production smoke assessment per selected NICO tier."
    )
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--frontend-url", default="")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tiers", default="express,mid,full")
    parser.add_argument("--customer-id", default="nico_production_smoke")
    parser.add_argument("--project-id", default="nico_production_smoke")
    parser.add_argument("--authorized-by", default="github_actions_manual_dispatch")
    parser.add_argument("--authorization-scope", default="authorized production assessment smoke only")
    parser.add_argument("--request-timeout-seconds", type=float, default=45.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int, default=60)
    parser.add_argument("--output", default="audit-results/production-assessment-smoke.json")
    parser.add_argument("--confirm-authorized", action="store_true")
    parser.add_argument("--allow-http-localhost", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        api_url = normalize_base_url(args.api_url, allow_http=args.allow_http_localhost)
        frontend_url = (
            normalize_base_url(args.frontend_url, allow_http=args.allow_http_localhost)
            if args.frontend_url
            else ""
        )
        config = SmokeConfig(
            api_url=api_url,
            repository=args.repository.strip(),
            customer_id=args.customer_id.strip() or "nico_production_smoke",
            project_id=args.project_id.strip() or "nico_production_smoke",
            authorized_by=args.authorized_by.strip() or "github_actions_manual_dispatch",
            authorization_scope=args.authorization_scope.strip() or "authorized production assessment smoke only",
            request_timeout_seconds=max(1.0, args.request_timeout_seconds),
            poll_interval_seconds=max(0.0, args.poll_interval_seconds),
            max_polls=max(1, args.max_polls),
        )
        evidence = run_smoke(
            config,
            parse_tiers(args.tiers),
            authorization_confirmed=bool(args.confirm_authorized),
            frontend_url=frontend_url,
        )
        write_evidence(args.output, evidence)
        print(json.dumps({"status": "passed", "output": args.output, "tiers": args.tiers}, sort_keys=True))
        return 0
    except SmokeFailure as exc:
        failure = {
            "schema_version": 1,
            "evidence_kind": "authorized_live_production_smoke",
            "live_claim": True,
            "authorization_confirmed": bool(args.confirm_authorized),
            "status": "failed",
            "error": str(exc),
            "finished_at": utc_now(),
        }
        write_evidence(args.output, failure)
        print(json.dumps({"status": "failed", "output": args.output, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
