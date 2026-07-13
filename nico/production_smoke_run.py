from __future__ import annotations

import re
import time
from typing import Any, Callable
from urllib.parse import quote, urlencode

from nico.production_smoke_config import (
    EVIDENCE_KIND,
    SCHEMA_VERSION,
    SmokeConfig,
    SmokeFailure,
    Transport,
    _REPORT_ID_KEYS,
    _REVIEW_ID_KEYS,
    utc_now,
)
from nico.production_smoke_contract import (
    _CLIENT_READY_KEYS,
    _REVIEW_KEYS,
    _explicit_boolean_boundary,
    _first_string,
    _safe_identity,
    _tier_is_stable,
    _tier_payload,
    _unavailable_evidence,
)

def run_tier(
    config: SmokeConfig,
    transport: Transport,
    tier: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    start_path = {
        "express": "/assessment/github",
        "mid": "/assessment/mid-run",
        "full": "/assessment/full-run",
    }[tier]
    start_count = 1
    current = transport.request_json("POST", start_path, _tier_payload(config, tier))
    initial_run_id = _first_string(current, ("run_id",))
    status_paths: set[str] = set()
    poll_count = 0

    if tier in {"mid", "full"}:
        expected_prefix = "midrun_" if tier == "mid" else "fullrun_"
        if not re.fullmatch(rf"{expected_prefix}[A-Za-z0-9_.-]+", initial_run_id):
            raise SmokeFailure("run_identity_missing", f"{tier.title()} start response did not retain the expected exact run ID.")
        status_path = f"/assessment/{tier}-run/{initial_run_id}/status"
        for _ in range(config.poll_attempts):
            status_paths.add(status_path)
            poll_count += 1
            current = transport.request_json("POST", status_path, _tier_payload(config, tier, current))
            returned_run_id = _first_string(current, ("run_id",))
            if returned_run_id != initial_run_id:
                raise SmokeFailure("run_identity_changed", f"{tier.title()} continuation changed the exact run identity.")
            if _tier_is_stable(tier, current):
                break
            sleep(config.poll_interval_seconds)
        else:
            raise SmokeFailure("poll_budget_exhausted", f"{tier.title()} continuation did not reach the human-review gate within the bounded poll budget.")
    elif not _tier_is_stable(tier, current):
        raise SmokeFailure("express_not_stable", "Express did not return a complete evidence-bound draft with explicit review and delivery boundaries.")

    human_review = _explicit_boolean_boundary(current, _REVIEW_KEYS, expected=True)
    client_not_ready = _explicit_boolean_boundary(current, _CLIENT_READY_KEYS, expected=False)
    if not human_review or not client_not_ready:
        raise SmokeFailure("boundary_missing", f"{tier.title()} did not preserve explicit human-review and non-client-ready boundaries.")
    report_id = _first_string(current, _REPORT_ID_KEYS)
    review_id = _first_string(current, _REVIEW_ID_KEYS)
    return {
        "tier": tier,
        "status": "passed",
        "start_count": start_count,
        "run_id": _safe_identity(initial_run_id),
        "status_path": next(iter(status_paths), ""),
        "status_poll_count": poll_count,
        "polled_single_exact_status_url": tier == "express" or len(status_paths) == 1,
        "report_id": _safe_identity(report_id),
        "report_id_status": "retained" if report_id else "not_returned",
        "review_request_id": _safe_identity(review_id),
        "review_request_id_status": "retained" if review_id else "not_returned",
        "terminal_status": str(current.get("status") or "unknown")[:80],
        "human_review_required": True,
        "client_ready": False,
        "unavailable_evidence": _unavailable_evidence(current),
    }

def _bounded_count(value: Any, label: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        raise SmokeFailure("invalid_delivery_summary", f"Delivery readiness returned an invalid {label} count.") from None
    if parsed < 0 or parsed > 1_000_000:
        raise SmokeFailure("invalid_delivery_summary", f"Delivery readiness returned an out-of-range {label} count.")
    return parsed

def verify_delivery_remains_blocked(
    config: SmokeConfig,
    transport: Transport,
    full_run_id: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"fullrun_[A-Za-z0-9_.-]+", full_run_id):
        raise SmokeFailure("delivery_run_identity_missing", "Full delivery-readiness proof requires the exact retained Full run ID.")
    query = urlencode({"customer_id": config.customer_id, "project_id": config.project_id})
    path = (
        f"/assessment/full-run/{quote(full_run_id, safe='')}/approved-delivery/readiness"
        f"?{query}"
    )
    result = transport.request_json("GET", path, admin=True)
    if result.get("status") != "blocked" or result.get("ready") is not False:
        raise SmokeFailure("delivery_boundary_weakened", "Full assessment delivery readiness was not explicitly blocked before human approval.")
    checks = result.get("checks") if isinstance(result.get("checks"), list) else []
    human_approval = next(
        (item for item in checks if isinstance(item, dict) and item.get("id") == "human_approval"),
        None,
    )
    if not isinstance(human_approval, dict) or human_approval.get("passed") is not False:
        raise SmokeFailure("delivery_boundary_unproven", "Delivery readiness did not retain the failed human-approval gate.")
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    counts = {
        "access_grant_count": _bounded_count(summary.get("access_grant_count"), "access grant"),
        "verified_receipt_count": _bounded_count(summary.get("verified_receipt_count"), "receipt"),
        "verified_acknowledgment_count": _bounded_count(summary.get("verified_acknowledgment_count"), "acknowledgment"),
    }
    if any(counts.values()):
        raise SmokeFailure("delivery_activity_detected", "The isolated production-smoke run already has delivery lifecycle activity.")
    return {
        "status": "blocked",
        "ready": False,
        "lifecycle": str(result.get("lifecycle") or "blocked")[:80],
        "human_approval_passed": False,
        **counts,
    }

def validate_browser_evidence(value: Any, expected_commit: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SmokeFailure("browser_evidence_missing", "Production browser evidence is missing or invalid.")
    if value.get("status") != "passed" or value.get("live_claim") is not True:
        raise SmokeFailure("browser_evidence_failed", "Production browser evidence did not report a passed live check.")
    if value.get("no_assessment_started") is not True:
        raise SmokeFailure("browser_started_assessment", "Browser proof must not start a second assessment path.")
    if str(value.get("frontend_commit") or "").lower() != expected_commit:
        raise SmokeFailure("browser_commit_mismatch", "Browser proof commit does not match the exact workflow commit.")
    checks = value.get("checks") if isinstance(value.get("checks"), list) else []
    if not checks or not all(isinstance(item, dict) and item.get("passed") is True for item in checks):
        raise SmokeFailure("browser_evidence_incomplete", "Production browser proof is missing a required passed check.")
    return {
        "status": "passed",
        "frontend_commit": expected_commit,
        "no_assessment_started": True,
        "checks": [{"id": str(item.get("id") or "")[:80], "passed": True} for item in checks],
    }

def build_smoke_artifact(
    config: SmokeConfig,
    transport: Transport,
    deployment: dict[str, Any],
    browser: dict[str, Any],
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    health = transport.request_json("GET", "/health")
    targets = transport.request_json("GET", "/targets")
    if health.get("status") != "ok" or targets.get("status") != "ok":
        raise SmokeFailure("production_readiness_failed", "Production health or target discovery did not report status ok.")
    tiers = [run_tier(config, transport, tier, sleep=sleep) for tier in ("express", "mid", "full")]
    full_tier = next(item for item in tiers if item["tier"] == "full")
    delivery_boundary = verify_delivery_remains_blocked(config, transport, str(full_tier.get("run_id") or ""))
    if any(item["start_count"] != 1 for item in tiers):
        raise SmokeFailure("duplicate_start", "Production smoke issued more than one start request for a tier.")
    if any(item["human_review_required"] is not True or item["client_ready"] is not False for item in tiers):
        raise SmokeFailure("boundary_missing", "A tier weakened the human-review or client-delivery boundary.")
    if any(item["polled_single_exact_status_url"] is not True for item in tiers):
        raise SmokeFailure("continuation_identity_failed", "Mid or Full did not remain on one exact run-status path.")
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_kind": EVIDENCE_KIND,
        "live_claim": True,
        "authorization_confirmed": True,
        "authorization_reference": config.authorization_reference,
        "status": "passed",
        "generated_at": utc_now(),
        "repository": config.repository,
        "customer_id": config.customer_id,
        "project_id": config.project_id,
        "deployment": deployment,
        "browser": browser,
        "delivery_boundary": delivery_boundary,
        "production_readiness": {
            "health_status": "ok",
            "targets_status": "ok",
        },
        "proof": {
            "one_start_per_tier": True,
            "exact_run_continuation": True,
            "human_review_boundary_preserved": True,
            "no_client_ready_claim": True,
            "duplicate_start_guard": True,
            "forbidden_operation_requests": 0,
            "client_delivery_blocked": True,
        },
        "tiers": tiers,
        "guardrail": "This workflow started authorized assessment drafts only. It did not approve, deliver, repair, or change production code.",
    }

