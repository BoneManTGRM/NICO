from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

import nico.express_async_api as express
from nico.canonical_strategic_package_v1 import (
    VERSION as CANONICAL_PACKAGE_VERSION,
    attach_canonical_strategic_package,
)

VERSION = "nico.canonical_express_binding.v1"
_MARKER = "_nico_canonical_express_binding_v1"


def _is_complete_report(response: dict[str, Any]) -> bool:
    status = str(response.get("status") or "").strip().casefold()
    reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
    return status in {"complete", "completed"} and bool(
        reports.get("markdown")
        and reports.get("html")
        and (reports.get("pdf_base64") or reports.get("pdf"))
    )


def _canonical_core_response(
    run_id: str,
    request_payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    source = deepcopy(response)
    source["run_id"] = str(source.get("run_id") or run_id)
    source["repository"] = str(source.get("repository") or request_payload.get("repository") or "")
    source["customer_id"] = str(source.get("customer_id") or request_payload.get("customer_id") or "default_customer")
    source["project_id"] = str(source.get("project_id") or request_payload.get("project_id") or "default_project")
    source["assessment_type"] = "core"
    source["service_tier"] = "core"
    source["assessment_depth"] = "core"
    source["report_language"] = str(
        source.get("report_language")
        or request_payload.get("report_language")
        or request_payload.get("language")
        or "en"
    )
    source["human_review_required"] = True
    source["client_ready"] = False
    source["client_delivery_allowed"] = False
    enriched = attach_canonical_strategic_package(
        source,
        depth="core",
        language=source["report_language"],
    )
    enriched["canonical_core_contract"] = {
        "artifact_schema": VERSION,
        "canonical_package_version": CANONICAL_PACKAGE_VERSION,
        "same_contract_used_by_strategic": True,
        "independent_core_scorecard_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return enriched


def install_canonical_express_binding_v1() -> dict[str, Any]:
    current: Callable[[str, dict[str, Any], dict[str, Any]], Any] = express._record
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "canonical_package_version": CANONICAL_PACKAGE_VERSION,
            "completed_express_runs_receive_core_contract": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def record_with_canonical_contract(
        run_id: str,
        request_payload: dict[str, Any],
        response: dict[str, Any],
    ) -> Any:
        output = _canonical_core_response(run_id, request_payload, response) if _is_complete_report(response) else response
        return current(run_id, request_payload, output)

    setattr(record_with_canonical_contract, _MARKER, True)
    setattr(record_with_canonical_contract, "_nico_previous", current)
    express._record = record_with_canonical_contract
    return {
        "status": "installed",
        "version": VERSION,
        "canonical_package_version": CANONICAL_PACKAGE_VERSION,
        "completed_express_runs_receive_core_contract": True,
        "same_contract_used_by_strategic": True,
        "independent_core_scorecard_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_canonical_express_binding_v1",
]
