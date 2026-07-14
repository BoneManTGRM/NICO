from __future__ import annotations

import hashlib
import sys
from copy import deepcopy
from typing import Any, Callable
from urllib.parse import urlencode

from nico.report_path_truth import apply_report_path_truth

EXPRESS_REPORT_PATH = "express"
EXPRESS_REPORT_LABEL = "Express Assessment"
_STORAGE_COMPAT_MARKER = "_nico_exact_express_storage_v1"


def express_run_id(result: dict[str, Any]) -> str:
    explicit = str(result.get("run_id") or result.get("assessment_id") or "").strip()
    if explicit:
        return explicit
    generated_at = str(result.get("generated_at") or "latest_express")
    return generated_at.replace(":", "_")


def express_report_id(result: dict[str, Any], run_id: str) -> str:
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    final_review = result.get("final_review") if isinstance(result.get("final_review"), dict) else {}
    explicit = str(
        result.get("report_id")
        or reports.get("report_id")
        or final_review.get("report_id")
        or ""
    ).strip()
    if explicit:
        return explicit
    material = "|".join(
        [
            "express",
            run_id,
            str(result.get("repository") or ""),
            str(result.get("generated_at") or ""),
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    return f"express_report_{digest}"


def final_review_url(run_id: str, customer_id: str, project_id: str, report_id: str = "") -> str:
    params = {
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
    }
    if report_id:
        params["report_id"] = report_id
    return f"/final-review?{urlencode(params)}"


def _refresh_requested(request_payload: dict[str, Any]) -> bool:
    marker = str(request_payload.get("authorized_by") or "").lower()
    return bool(
        request_payload.get("refresh_full_evidence")
        or "frontend-refresh-full-evidence" in marker
        or "refresh-full-evidence" in marker
    )


def _attach_express_report_path(result: dict[str, Any]) -> None:
    apply_report_path_truth(result, EXPRESS_REPORT_PATH)


def _exact_storage_record(
    req: Any,
    response_payload: dict[str, Any],
    fallback: Callable[[Any], tuple[str, dict[str, Any]]],
) -> tuple[str, dict[str, Any]]:
    if not response_payload:
        return fallback(req)
    run_id = express_run_id(response_payload)
    report_id = express_report_id(response_payload, run_id)
    customer_id = str(response_payload.get("customer_id") or getattr(req, "customer_id", "default_customer") or "default_customer")
    project_id = str(response_payload.get("project_id") or getattr(req, "project_id", "default_project") or "default_project")
    payload = deepcopy(response_payload)
    payload["run_id"] = run_id
    payload["report_id"] = report_id
    return run_id, {
        "workflow": "express",
        "customer_id": customer_id,
        "project_id": project_id,
        "status": payload.get("status") or "complete",
        "run_id": run_id,
        "report_id": report_id,
        "payload": payload,
    }


def install_express_storage_compatibility() -> dict[str, Any]:
    """Restore exact-run Express persistence after the shared storage helper regression.

    `nico.api.main` imports this module while it is still being initialized, so the
    compatibility hook is installed lazily on the first Express result. The route
    later sets `_LAST_HOSTED_ASSESSMENT` before invoking the patched storage helper,
    allowing the final response payload to be retained under its returned run ID.
    """

    api_main = sys.modules.get("nico.api.main")
    if api_main is None or not hasattr(api_main, "hosted_assessment_storage_record"):
        return {"status": "deferred", "exact_run_storage": False}
    current = getattr(api_main, "hosted_assessment_storage_record")
    if getattr(current, _STORAGE_COMPAT_MARKER, False):
        return {"status": "already_installed", "exact_run_storage": True}

    fallback = current

    def exact_hosted_assessment_storage_record(req: Any) -> tuple[str, dict[str, Any]]:
        response_payload = getattr(api_main, "_LAST_HOSTED_ASSESSMENT", {})
        payload = response_payload if isinstance(response_payload, dict) else {}
        return _exact_storage_record(req, payload, fallback)

    setattr(exact_hosted_assessment_storage_record, _STORAGE_COMPAT_MARKER, True)
    setattr(exact_hosted_assessment_storage_record, "_nico_storage_fallback", fallback)
    setattr(api_main, "hosted_assessment_storage_record", exact_hosted_assessment_storage_record)
    return {"status": "installed", "exact_run_storage": True}


def attach_express_review_target(result: dict[str, Any], request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = request_payload or {}
    install_express_storage_compatibility()
    customer_id = str(request_payload.get("customer_id") or result.get("customer_id") or "default_customer")
    project_id = str(request_payload.get("project_id") or result.get("project_id") or "default_project")
    run_id = express_run_id(result)
    report_id = express_report_id(result, run_id)
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    reports["report_id"] = report_id
    result["reports"] = reports
    result["customer_id"] = customer_id
    result["project_id"] = project_id
    result["run_id"] = run_id
    result["report_id"] = report_id
    result["authorized_by"] = str(request_payload.get("authorized_by") or result.get("authorized_by") or "unspecified")
    _attach_express_report_path(result)
    if _refresh_requested(request_payload):
        result["refresh_full_evidence_requested"] = True
    result["final_review"] = {
        "status": "required_before_client_delivery",
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "report_id": report_id,
        "url": final_review_url(run_id, customer_id, project_id, report_id),
        "rule": "Use this same run/customer/project scope when requesting and approving final review; rerun the assessment after approval so acceptance evidence can be applied.",
    }
    result.setdefault("next_steps", [])
    step = f"Final review target: run_id={run_id}; customer_id={customer_id}; project_id={project_id}; report_id={report_id}; url={result['final_review']['url']}"
    if step not in result["next_steps"]:
        result["next_steps"].append(step)
    return result
