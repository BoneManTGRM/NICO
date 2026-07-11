from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

EXPRESS_REPORT_PATH = "express"
EXPRESS_REPORT_LABEL = "Express Assessment"
EXPRESS_MARKDOWN_BANNER = "> Report path: Express Assessment (`express`). This is not Full Assessment output.\n\n"
EXPRESS_HTML_BANNER = (
    '<aside data-nico-report-path="express" style="margin:12px 0;padding:12px;border:1px solid #38bdf8;'
    'border-radius:10px;background:#e0f2fe;color:#0c4a6e;font-weight:700">'
    'Report path: Express Assessment (<code>express</code>). This is not Full Assessment output.'
    '</aside>'
)


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


def _label_markdown(markdown: Any) -> Any:
    if not isinstance(markdown, str) or not markdown.strip():
        return markdown
    if "Report path: Express Assessment" in markdown:
        return markdown
    return EXPRESS_MARKDOWN_BANNER + markdown


def _label_html(html: Any) -> Any:
    if not isinstance(html, str) or not html.strip():
        return html
    if 'data-nico-report-path="express"' in html:
        return html
    lower = html.lower()
    body_index = lower.find("<body")
    if body_index >= 0:
        close_index = html.find(">", body_index)
        if close_index >= 0:
            return html[: close_index + 1] + EXPRESS_HTML_BANNER + html[close_index + 1 :]
    return EXPRESS_HTML_BANNER + html


def _attach_express_report_path(result: dict[str, Any]) -> None:
    result["report_path"] = EXPRESS_REPORT_PATH
    result["report_path_label"] = EXPRESS_REPORT_LABEL
    reports = result.get("reports")
    if isinstance(reports, dict):
        reports["report_path"] = EXPRESS_REPORT_PATH
        reports["report_path_label"] = EXPRESS_REPORT_LABEL
        reports["markdown"] = _label_markdown(reports.get("markdown"))
        reports["html"] = _label_html(reports.get("html"))


def attach_express_review_target(result: dict[str, Any], request_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request_payload = request_payload or {}
    customer_id = str(request_payload.get("customer_id") or result.get("customer_id") or "default_customer")
    project_id = str(request_payload.get("project_id") or result.get("project_id") or "default_project")
    run_id = express_run_id(result)
    report_id = str(result.get("report_id") or result.get("reports", {}).get("report_id") or "")
    result["customer_id"] = customer_id
    result["project_id"] = project_id
    result["run_id"] = run_id
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
    step = f"Final review target: run_id={run_id}; customer_id={customer_id}; project_id={project_id}; url={result['final_review']['url']}"
    if step not in result["next_steps"]:
        result["next_steps"].append(step)
    return result
