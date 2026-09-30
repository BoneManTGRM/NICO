"""Decide when a detached recovery's bounded status has reached a new boundary."""
from collections.abc import Mapping
import hashlib
import json
from typing import Any


def recovery_boundary_observed(view: Mapping[str, Any], *, initial_revision: int) -> bool:
    revision = view.get("revision")
    return bool(
        type(revision) is int
        and revision > initial_revision
        and (view.get("terminal") is True or view.get("current_stage_complete") is True)
    )


def retryable_recovery_read(status: int, body: str) -> bool:
    if status in {408, 425, 429, 500, 502, 503, 504}:
        return True
    if status != 404:
        return False
    try:
        value = json.loads(body)
    except (ValueError, TypeError):
        return False
    return bool(isinstance(value, dict) and value.get("code") == 404
                and value.get("message") == "Application not found")


def recovery_maintenance_tick_due(view: Mapping[str, Any], *, elapsed_seconds: float, ticks: int) -> bool:
    """Status projections do not reclaim final-report leases after worker loss."""
    return bool(
        elapsed_seconds >= 60
        and ticks < 30
        and view.get("terminal") is False
        and view.get("current_stage_complete") is False
        and view.get("current_stage") == "final_comprehensive_report_generation"
    )


def validate_recovered_pdf(data: bytes, headers: Mapping[str, str], *, run_id: str, commit_sha: str) -> dict:
    observed = {key.lower(): value for key, value in headers.items()}
    digest = hashlib.sha256(data).hexdigest()
    checks = {
        "signature": data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:],
        "content_type": observed.get("content-type", "").split(";", 1)[0] == "application/pdf",
        "run_id": observed.get("x-nico-run-id") == run_id,
        "commit_sha": observed.get("x-nico-commit-sha") == commit_sha,
        "hash": observed.get("x-nico-pdf-sha256") == digest,
        "human_review": observed.get("x-nico-human-review-required") == "true",
        "delivery": observed.get("x-nico-client-delivery-allowed") == "false",
    }
    if not all(checks.values()):
        raise ValueError("recovered_pdf_binding_invalid:" + ",".join(key for key, value in checks.items() if not value))
    return {"pdf_sha256": digest, "pdf_size_bytes": len(data), "exact_run_pdf_verified": True}
