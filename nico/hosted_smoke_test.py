from __future__ import annotations

from typing import Any

SMOKE_TESTS = [
    {"id": "health", "label": "Health endpoint", "evidence_key": "health", "required_status": "ok"},
    {"id": "targets", "label": "Target discovery", "evidence_key": "targets", "required_status": "ok"},
    {"id": "service_catalog", "label": "Service catalog", "evidence_key": "service_catalog", "required_status": None},
    {"id": "workflow_preflight", "label": "Workflow preflight", "evidence_key": "workflow_preflight", "required_status": None},
    {"id": "release_readiness", "label": "Release readiness", "evidence_key": "release_readiness", "required_status": None},
    {"id": "worker_scan", "label": "Worker scan", "evidence_key": "worker_scan", "required_status": None},
    {"id": "express_assessment", "label": "Express assessment", "evidence_key": "express_assessment", "required_status": None},
]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _has_payload(value: Any) -> bool:
    if isinstance(value, dict) or isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _case_result(case: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    key = case["evidence_key"]
    payload = evidence.get(key)
    present = _has_payload(payload)
    status_value = _dict(payload).get("status") if present else None
    required_status = case.get("required_status")

    if not present:
        result = "missing"
        passed = False
        note = f"Missing evidence for {case['label']}."
    elif required_status and status_value != required_status:
        result = "failed"
        passed = False
        note = f"Expected status {required_status} for {case['label']}."
    else:
        result = "passed"
        passed = True
        note = f"Evidence supplied for {case['label']}."

    return {
        "id": case["id"],
        "label": case["label"],
        "evidence_key": key,
        "result": result,
        "passed": passed,
        "observed_status": status_value,
        "note": note,
    }


def build_hosted_smoke_test(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = _dict(payload.get("evidence"))
    cases = [_case_result(case, evidence) for case in SMOKE_TESTS]
    passed_count = sum(1 for case in cases if case["passed"])
    missing = [case["evidence_key"] for case in cases if case["result"] == "missing"]
    failed = [case["evidence_key"] for case in cases if case["result"] == "failed"]
    readiness_score = round((passed_count / len(cases)) * 100)

    if failed:
        status = "failed_smoke_test"
    elif missing:
        status = "incomplete_smoke_test"
    elif readiness_score == 100:
        status = "passed_smoke_test"
    else:
        status = "needs_smoke_test_review"

    return {
        "artifact_schema": "nico.hosted_smoke_test.v1",
        "status": status,
        "readiness_score": readiness_score,
        "passed_count": passed_count,
        "required_count": len(cases),
        "cases": cases,
        "missing_evidence": missing,
        "failed_evidence": failed,
        "next_action": _next_action(status, missing, failed),
        "human_review_required": True,
    }


def _next_action(status: str, missing: list[str], failed: list[str]) -> str:
    if failed:
        return "Fix failed smoke-test evidence before trusting hosted output."
    if missing:
        return "Collect missing smoke-test evidence before generating a client-facing report."
    if status == "passed_smoke_test":
        return "Run a fresh Express assessment and attach the smoke-test artifact to the report evidence bundle."
    return "Review smoke-test evidence before report delivery."
