from __future__ import annotations

from typing import Any

APPROVED_STATUSES = {"approved", "accepted", "passed", "complete", "completed"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _status(value: dict[str, Any]) -> str:
    return str(value.get("status") or value.get("state") or "unknown").strip().lower()


def _approved(value: dict[str, Any]) -> bool:
    return _status(value) in APPROVED_STATUSES


def build_report_delivery_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    report = _dict(payload.get("report"))
    readiness = _dict(payload.get("delivery_readiness") or report.get("delivery_readiness"))
    final_review = _dict(payload.get("final_review") or report.get("final_review"))
    client_acceptance = _dict(payload.get("client_acceptance") or report.get("client_acceptance"))
    evidence_bundle = _dict(payload.get("evidence_artifact_bundle") or report.get("evidence_artifact_bundle"))

    missing: list[str] = []
    blockers: list[str] = []
    evidence: list[str] = []

    readiness_allowed = bool(readiness.get("delivery_allowed")) or readiness.get("status") == "delivery_ready"
    if not readiness:
        missing.append("delivery_readiness")
        blockers.append("Delivery readiness artifact is missing.")
    elif readiness_allowed:
        evidence.append("Delivery readiness allows report delivery.")
    else:
        blockers.append(f"Delivery readiness blocks report delivery: {readiness.get('gate_status') or readiness.get('status') or 'unknown'}." )

    if not final_review:
        missing.append("final_review")
        blockers.append("Final review evidence is missing.")
    elif _approved(final_review):
        evidence.append("Final review is approved.")
    else:
        blockers.append(f"Final review is not approved: {_status(final_review)}.")

    if not client_acceptance:
        missing.append("client_acceptance")
        blockers.append("Client acceptance evidence is missing.")
    elif _approved(client_acceptance):
        evidence.append("Client acceptance is approved.")
    else:
        blockers.append(f"Client acceptance is not approved: {_status(client_acceptance)}.")

    artifacts = _list(evidence_bundle.get("artifacts"))
    if not evidence_bundle:
        missing.append("evidence_artifact_bundle")
        blockers.append("Evidence artifact bundle is missing.")
    elif artifacts:
        evidence.append("Evidence artifact bundle is present.")
    else:
        missing.append("evidence_artifact_bundle.artifacts")
        blockers.append("Evidence artifact bundle has no artifacts.")

    delivery_allowed = not blockers and not missing
    if delivery_allowed:
        status = "ready_for_client_delivery"
    elif blockers:
        status = "blocked_client_delivery"
    else:
        status = "needs_delivery_review"

    return {
        "artifact_schema": "nico.report_delivery_manifest.v1",
        "status": status,
        "delivery_allowed": delivery_allowed,
        "report_id": str(report.get("report_id") or report.get("run_id") or ""),
        "readiness_status": readiness.get("status") or readiness.get("gate_status") or "unknown",
        "final_review_status": _status(final_review),
        "client_acceptance_status": _status(client_acceptance),
        "evidence_artifact_count": len(artifacts),
        "evidence": evidence,
        "missing": sorted(set(missing)),
        "blockers": sorted(set(blockers)),
        "next_action": _next_action(status),
        "human_review_required": True,
    }


def _next_action(status: str) -> str:
    if status == "ready_for_client_delivery":
        return "Deliver the report package with the delivery manifest attached."
    if status == "blocked_client_delivery":
        return "Resolve delivery blockers before sending the report to the client."
    return "Review delivery evidence before sending the report."
