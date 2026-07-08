from __future__ import annotations

from typing import Any

REQUIRED_WORKFLOW_ENDPOINTS = [
    "GET /service-catalog",
    "GET /service-catalog/{workflow}",
    "POST /service-catalog/intake-readiness",
    "POST /workflow/preflight",
    "POST /workflow/preflight/batch",
    "POST /assessment/github",
    "POST /assessment/mid",
    "POST /retainer/ops",
    "POST /worker/scan",
    "POST /client-acceptance/request",
]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _field_present(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) or isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _endpoint_status(targets: dict[str, Any]) -> dict[str, Any]:
    endpoints = [str(item) for item in _list(targets.get("workflow_endpoints"))]
    missing = [endpoint for endpoint in REQUIRED_WORKFLOW_ENDPOINTS if endpoint not in endpoints]
    return {
        "required": REQUIRED_WORKFLOW_ENDPOINTS,
        "present": [endpoint for endpoint in REQUIRED_WORKFLOW_ENDPOINTS if endpoint in endpoints],
        "missing": missing,
        "score": round(((len(REQUIRED_WORKFLOW_ENDPOINTS) - len(missing)) / len(REQUIRED_WORKFLOW_ENDPOINTS)) * 100),
    }


def _sha_status(payload: dict[str, Any]) -> dict[str, Any]:
    expected = str(payload.get("expected_main_sha") or payload.get("main_sha") or "").strip()
    deployed = str(payload.get("deployed_sha") or payload.get("runtime_sha") or "").strip()
    if not expected and not deployed:
        return {"status": "unknown", "score": 40, "evidence": [], "missing": ["expected_main_sha", "deployed_sha"]}
    if expected and deployed and expected == deployed:
        return {"status": "matches_expected_main", "score": 100, "evidence": [f"Deployed SHA matches expected main SHA {expected}."], "missing": []}
    if expected and deployed:
        return {"status": "mismatch", "score": 20, "evidence": [f"Expected main SHA {expected} but deployed SHA is {deployed}."], "missing": []}
    return {"status": "partial", "score": 55, "evidence": ["Only one deployment SHA value was supplied."], "missing": [key for key in ["expected_main_sha", "deployed_sha"] if not _field_present(payload, key)]}


def build_deployment_verification(payload: dict[str, Any]) -> dict[str, Any]:
    health = _dict(payload.get("backend_health"))
    targets = _dict(payload.get("targets"))
    frontend = _dict(payload.get("frontend_config"))
    endpoint_status = _endpoint_status(targets)
    sha_status = _sha_status(payload)

    evidence: list[str] = []
    blockers: list[str] = []
    missing: list[str] = []

    health_ok = health.get("status") == "ok"
    if health_ok:
        evidence.append("Backend health payload reports status ok.")
    else:
        blockers.append("Backend health payload is missing or does not report status ok.")
        missing.append("backend_health.status")

    if endpoint_status["missing"]:
        missing.extend([f"targets.workflow_endpoints:{endpoint}" for endpoint in endpoint_status["missing"]])
    else:
        evidence.append("Targets payload lists all required workflow endpoints.")

    backend_url = str(frontend.get("backend_url") or frontend.get("api_url") or "").strip()
    if backend_url:
        evidence.append("Frontend configuration includes a backend URL value.")
    else:
        missing.append("frontend_config.backend_url")

    evidence.extend(sha_status.get("evidence", []))
    missing.extend([f"deployment_sha:{item}" for item in sha_status.get("missing", [])])

    scores = [100 if health_ok else 0, endpoint_status["score"], 100 if backend_url else 35, sha_status["score"]]
    readiness_score = round(sum(scores) / len(scores))

    if blockers:
        status = "blocked_deployment_verification"
    elif missing:
        status = "needs_more_deployment_evidence"
    elif readiness_score >= 90:
        status = "ready_for_live_smoke_test"
    else:
        status = "needs_deployment_review"

    return {
        "artifact_schema": "nico.deployment_verification.v1",
        "status": status,
        "readiness_score": readiness_score,
        "backend_health_ok": health_ok,
        "endpoint_status": endpoint_status,
        "sha_status": sha_status,
        "frontend_backend_url_present": bool(backend_url),
        "evidence": evidence,
        "missing": missing,
        "blockers": blockers,
        "next_action": _next_action(status, missing, blockers),
        "human_review_required": True,
    }


def _next_action(status: str, missing: list[str], blockers: list[str]) -> str:
    if blockers:
        return "Fix backend health before trusting hosted assessment output."
    if missing:
        return "Collect missing deployment evidence before running a fresh client-facing report."
    if status == "ready_for_live_smoke_test":
        return "Run live smoke tests for health, targets, service catalog, workflow preflight, worker scan, and Express assessment."
    return "Review deployment evidence before relying on hosted report output."
