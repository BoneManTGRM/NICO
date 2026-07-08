from __future__ import annotations

from typing import Any

from nico.deployment_verification import build_deployment_verification
from nico.hosted_smoke_test import build_hosted_smoke_test


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_report_readiness_gate(payload: dict[str, Any]) -> dict[str, Any]:
    deployment_payload = _dict(payload.get("deployment"))
    smoke_payload = _dict(payload.get("smoke_test"))
    assessment_payload = _dict(payload.get("assessment_request"))

    deployment = build_deployment_verification(deployment_payload)
    smoke_test = build_hosted_smoke_test(smoke_payload)

    blockers: list[str] = []
    missing: list[str] = []
    evidence: list[str] = []

    if deployment.get("status") not in {"ready_for_live_smoke_test", "needs_deployment_review"}:
        blockers.append(f"Deployment verification is not ready: {deployment.get('status')}.")
    if deployment.get("missing"):
        missing.extend([f"deployment:{item}" for item in deployment.get("missing", [])])
    if deployment.get("blockers"):
        blockers.extend([f"deployment:{item}" for item in deployment.get("blockers", [])])

    if smoke_test.get("status") != "passed_smoke_test":
        blockers.append(f"Hosted smoke test has not passed: {smoke_test.get('status')}.")
    if smoke_test.get("missing_evidence"):
        missing.extend([f"smoke_test:{item}" for item in smoke_test.get("missing_evidence", [])])
    if smoke_test.get("failed_evidence"):
        blockers.extend([f"smoke_test:{item}" for item in smoke_test.get("failed_evidence", [])])

    authorized = bool(assessment_payload.get("authorized"))
    repository = str(assessment_payload.get("repository") or "").strip()
    client_name = str(assessment_payload.get("client_name") or "").strip()
    if not authorized:
        blockers.append("Assessment request is missing explicit authorization.")
        missing.append("assessment_request.authorized")
    else:
        evidence.append("Assessment request includes explicit authorization.")
    if not repository:
        blockers.append("Assessment request is missing repository.")
        missing.append("assessment_request.repository")
    else:
        evidence.append("Assessment request includes repository.")
    if not client_name:
        missing.append("assessment_request.client_name")

    readiness_score = round((deployment.get("readiness_score", 0) + smoke_test.get("readiness_score", 0)) / 2)
    report_delivery_allowed = not blockers and not missing and readiness_score >= 90

    if blockers:
        status = "blocked_report_readiness"
    elif missing:
        status = "needs_more_report_readiness_evidence"
    elif report_delivery_allowed:
        status = "ready_for_fresh_express_report"
    else:
        status = "needs_report_readiness_review"

    return {
        "artifact_schema": "nico.report_readiness_gate.v1",
        "status": status,
        "readiness_score": readiness_score,
        "report_delivery_allowed": report_delivery_allowed,
        "deployment_verification": deployment,
        "hosted_smoke_test": smoke_test,
        "assessment_request_summary": {
            "authorized": authorized,
            "repository": repository,
            "client_name_present": bool(client_name),
        },
        "evidence": evidence,
        "missing": sorted(set(missing)),
        "blockers": sorted(set(blockers)),
        "next_action": _next_action(status),
        "human_review_required": True,
    }


def _next_action(status: str) -> str:
    if status == "ready_for_fresh_express_report":
        return "Run a fresh Express report and attach this readiness gate artifact to the evidence bundle."
    if status == "blocked_report_readiness":
        return "Resolve blockers before generating or trusting a client-facing Express report."
    if status == "needs_more_report_readiness_evidence":
        return "Collect missing readiness evidence before generating a client-facing report."
    return "Review readiness evidence before report delivery."
