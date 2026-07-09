from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


def express_run_id(result: dict[str, Any]) -> str:
    explicit = str(result.get("run_id") or result.get("assessment_id") or "").strip()
    if explicit:
        return explicit
    generated_at = str(result.get("generated_at") or "latest_express")
    return generated_at.replace(":", "_")


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


def attach_express_review_target(result: dict[str, Any], request_payload: dict[str, Any]) -> dict[str, Any]:
    customer_id = str(request_payload.get("customer_id") or result.get("customer_id") or "default_customer")
    project_id = str(request_payload.get("project_id") or result.get("project_id") or "default_project")
    run_id = express_run_id(result)
    report_id = str(result.get("report_id") or result.get("reports", {}).get("report_id") or "")
    result["customer_id"] = customer_id
    result["project_id"] = project_id
    result["run_id"] = run_id
    result["authorized_by"] = str(request_payload.get("authorized_by") or result.get("authorized_by") or "unspecified")
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
    step = f"Final review target: run_id={run_id}; customer_id={customer_id}; project_id={project_id}; url={result['final_review']['url']}"
    if step not in result["next_steps"]:
        result["next_steps"].append(step)
    return result
