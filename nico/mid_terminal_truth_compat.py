from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from fastapi import HTTPException

MID_TERMINAL_TRUTH_COMPAT_VERSION = "nico.mid_terminal_truth_compat.v2"
_NORMALIZE_MARKER = "_nico_mid_terminal_truth_compat_normalize_v1"
_LIVE_MARKER = "_nico_mid_terminal_truth_compat_live_v1"
_INSTALLER_MARKER = "_nico_mid_terminal_truth_compat_installer_v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_scope_matches(record: dict[str, Any], customer_id: str, project_id: str) -> bool:
    request = _dict(record.get("request"))
    stored_customer = str(record.get("customer_id") or request.get("customer_id") or "default_customer")
    stored_project = str(record.get("project_id") or request.get("project_id") or "default_project")
    if customer_id and customer_id != stored_customer:
        return False
    if project_id and project_id != stored_project:
        return False
    return True


def _route_count(app: Any, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def _report_payload(report: dict[str, Any]) -> dict[str, Any]:
    formats = _dict(report.get("formats"))
    payload = _dict(formats.get("json"))
    if payload:
        return payload
    package = _dict(report.get("report_package"))
    package_formats = _dict(package.get("formats"))
    return _dict(package_formats.get("json")) or package


def _enrich_blocked_report_summary(result: dict[str, Any]) -> dict[str, Any]:
    from nico import mid_terminal_truth_patch as terminal

    output = deepcopy(result)
    if str(output.get("report_generation_status") or "").lower() != "blocked":
        return output
    report = terminal._quality_report_for_run(output)
    payload = _report_payload(report)
    if not payload:
        return output

    technical_score = payload.get("technical_score")
    maturity = deepcopy(_dict(payload.get("maturity_signal")))
    if isinstance(technical_score, (int, float)):
        output["technical_score"] = technical_score
        maturity.setdefault("score", technical_score)
    if maturity:
        output["maturity_signal"] = maturity

    coverage = deepcopy(_dict(payload.get("evidence_coverage")))
    if coverage:
        output["evidence_coverage"] = coverage

    decision = deepcopy(_dict(payload.get("decision_summary")))
    if decision:
        output["decision_summary"] = decision

    assessment = deepcopy(_dict(output.get("assessment")))
    if maturity:
        assessment["maturity_signal"] = deepcopy(maturity)
    if coverage:
        assessment["evidence_coverage"] = deepcopy(coverage)
    if assessment:
        output["assessment"] = assessment

    mid_report = deepcopy(_dict(output.get("mid_report")))
    mid_report.update(
        {
            "status": "blocked",
            "report_id": str(report.get("report_id") or mid_report.get("report_id") or ""),
            "report_path": str(report.get("report_path") or mid_report.get("report_path") or "mid_run"),
            "report_version": str(report.get("report_version") or mid_report.get("report_version") or ""),
            "technical_score": technical_score,
            "evidence_coverage_percent": coverage.get("percent") if coverage else None,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    output["mid_report"] = mid_report
    output["blocked_report_summary_projected"] = True
    return output


def install_mid_terminal_truth_compat() -> dict[str, Any]:
    from nico import lifecycle_status_hardening as lifecycle
    from nico import mid_live_status_api
    from nico import mid_terminal_truth_patch as terminal
    from nico.storage import STORE

    current_normalize: Callable[[dict[str, Any]], dict[str, Any]] = terminal.normalize_mid_terminal_truth
    normalize_installed = False
    if not getattr(current_normalize, _NORMALIZE_MARKER, False):
        @wraps(current_normalize)
        def compatible_normalize(result: dict[str, Any]) -> dict[str, Any]:
            return _enrich_blocked_report_summary(current_normalize(result))

        setattr(compatible_normalize, _NORMALIZE_MARKER, True)
        setattr(compatible_normalize, "_nico_previous", current_normalize)
        terminal.normalize_mid_terminal_truth = compatible_normalize
        normalize_installed = True

    current_live: Callable[..., dict[str, Any]] = mid_live_status_api.mid_live_status_response
    live_installed = False
    if not getattr(current_live, _LIVE_MARKER, False):
        @wraps(current_live)
        def strict_live_status(run_id: str, customer_id: str = "", project_id: str = "") -> dict[str, Any]:
            record = STORE.get("assessment_runs", run_id)
            if isinstance(record, dict) and str(record.get("workflow") or "") == "mid_assessment":
                if not _optional_scope_matches(record, str(customer_id or ""), str(project_id or "")):
                    raise HTTPException(
                        status_code=404,
                        detail={"status": "not_found", "message": "Mid Assessment run not found in this scope."},
                    )
            return current_live(run_id, customer_id=customer_id, project_id=project_id)

        setattr(strict_live_status, _LIVE_MARKER, True)
        setattr(strict_live_status, "_nico_previous", current_live)
        mid_live_status_api.mid_live_status_response = strict_live_status
        lifecycle.mid_live_status_response = strict_live_status
        live_installed = True

    current_installer: Callable[[Any], dict[str, Any]] = lifecycle.install_lifecycle_status_hardening
    installer_installed = False
    if not getattr(current_installer, _INSTALLER_MARKER, False):
        @wraps(current_installer)
        def fresh_app_safe_installer(app: Any) -> dict[str, Any]:
            count = _route_count(app, "POST", terminal.MID_STATUS_PATH)
            if count == 0:
                app.add_api_route(
                    terminal.MID_STATUS_PATH,
                    terminal.mid_status_endpoint,
                    methods=["POST"],
                    tags=["assessment", "mid", "status"],
                )
                app.openapi_schema = None
            elif count > 1:
                raise RuntimeError(
                    f"Expected at most one POST {terminal.MID_STATUS_PATH} route before lifecycle hardening; found={count}"
                )
            result = dict(current_installer(app))
            result["mid_fresh_app_status_route_supported"] = True
            return result

        setattr(fresh_app_safe_installer, _INSTALLER_MARKER, True)
        setattr(fresh_app_safe_installer, "_nico_previous", current_installer)
        lifecycle.install_lifecycle_status_hardening = fresh_app_safe_installer
        installer_installed = True

    return {
        "status": "installed" if normalize_installed or live_installed or installer_installed else "already_installed",
        "version": MID_TERMINAL_TRUTH_COMPAT_VERSION,
        "blocked_report_summary_projected": True,
        "optional_scope_fields_validated_independently": True,
        "partial_wrong_scope_allowed": False,
        "fresh_app_status_route_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_TERMINAL_TRUTH_COMPAT_VERSION",
    "install_mid_terminal_truth_compat",
]
