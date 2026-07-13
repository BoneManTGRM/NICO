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
    {
        "id": "production_assessment_tiers",
        "label": "Authorized deployed Express, Mid, and Full proof",
        "evidence_key": "production_assessment_smoke",
        "required_status": "passed",
        "validator": "production_assessment_smoke",
    },
]

_REQUIRED_TIERS = ("express", "mid", "full")
_REQUIRED_PROOF_FLAGS = (
    "one_start_per_tier",
    "exact_run_continuation",
    "human_review_boundary_preserved",
    "no_client_ready_claim",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _has_payload(value: Any) -> bool:
    if isinstance(value, dict) or isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _production_assessment_smoke_validation(payload: Any) -> tuple[bool, str]:
    artifact = _dict(payload)
    if artifact.get("status") != "passed":
        return False, "Production assessment smoke artifact does not report status passed."
    if artifact.get("evidence_kind") != "authorized_live_production_smoke":
        return False, "Production assessment smoke evidence kind is missing or not authorized live proof."
    if artifact.get("live_claim") is not True:
        return False, "Synthetic or non-live assessment smoke evidence cannot satisfy deployed tier proof."
    if artifact.get("authorization_confirmed") is not True:
        return False, "Repository authorization was not confirmed in the production smoke artifact."

    proof = _dict(artifact.get("proof"))
    missing_flags = [flag for flag in _REQUIRED_PROOF_FLAGS if proof.get(flag) is not True]
    if missing_flags:
        return False, f"Production smoke proof flags are not satisfied: {', '.join(missing_flags)}."

    tiers: dict[str, dict[str, Any]] = {}
    for item in _list(artifact.get("tiers")):
        if not isinstance(item, dict):
            continue
        tier = str(item.get("tier") or "").strip().lower()
        if tier and tier not in tiers:
            tiers[tier] = item

    missing_tiers = [tier for tier in _REQUIRED_TIERS if tier not in tiers]
    if missing_tiers:
        return False, f"Production smoke artifact is missing tier proof: {', '.join(missing_tiers)}."

    for tier in _REQUIRED_TIERS:
        result = tiers[tier]
        if result.get("status") != "passed":
            return False, f"{tier.title()} smoke result does not report status passed."
        if result.get("start_count") != 1:
            return False, f"{tier.title()} smoke result did not prove exactly one start request."
        if result.get("human_review_required") is not True:
            return False, f"{tier.title()} smoke result did not preserve the human-review boundary."
        if result.get("client_ready") is not False:
            return False, f"{tier.title()} smoke result made or omitted the required non-client-ready boundary."

    for tier in ("mid", "full"):
        result = tiers[tier]
        if not str(result.get("run_id") or "").strip():
            return False, f"{tier.title()} smoke result did not retain an exact run ID."
        if result.get("polled_single_exact_status_url") is not True:
            return False, f"{tier.title()} smoke result did not prove exact-run status continuation."

    return True, "Authorized live Express, Mid, and Full smoke proof passed with one start per tier and exact-run continuation."


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
    elif case.get("validator") == "production_assessment_smoke":
        passed, note = _production_assessment_smoke_validation(payload)
        result = "passed" if passed else "failed"
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
        "contract_version": 2,
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
        return "Attach the authorized Express, Mid, and Full smoke artifact and deployment evidence to the human-review package."
    return "Review smoke-test evidence before report delivery."
