from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

import nico.express_async_api as express
from nico.canonical_assessment_contract_v1 import (
    VERSION as CANONICAL_CONTRACT_VERSION,
    attach_canonical_assessment_contract,
)

VERSION = "nico.canonical_express_contract_binding.v1"
_MARKER = "_nico_canonical_express_contract_binding_v1"
_TERMINAL_SUCCESS = {"complete", "completed"}


def _reports_ready(response: dict[str, Any]) -> bool:
    reports = response.get("reports") if isinstance(response.get("reports"), dict) else {}
    return bool(
        str(reports.get("markdown") or "").strip()
        and str(reports.get("html") or "").strip()
        and (reports.get("pdf_base64") or reports.get("pdf"))
    )


def _eligible_completed_response(response: dict[str, Any]) -> bool:
    status = str(response.get("status") or "").strip().casefold()
    return status in _TERMINAL_SUCCESS and _reports_ready(response)


def canonical_core_response(
    run_id: str,
    request_payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    """Attach the shared assessment contract without replacing legacy API fields."""

    source = deepcopy(response)
    source["run_id"] = str(source.get("run_id") or run_id)
    source["repository"] = str(source.get("repository") or request_payload.get("repository") or "")
    source["customer_id"] = str(
        source.get("customer_id") or request_payload.get("customer_id") or "default_customer"
    )
    source["project_id"] = str(
        source.get("project_id") or request_payload.get("project_id") or "default_project"
    )

    # Preserve the established transport identity while making the customer-facing
    # depth explicit. A later route migration can remove the legacy aliases after
    # both backends consume the same canonical continuation contract.
    source.setdefault("assessment_type", "express")
    source.setdefault("service_tier", "express")
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

    enriched = attach_canonical_assessment_contract(
        source,
        depth="core",
        language=source["report_language"],
    )
    enriched["canonical_core_contract"] = {
        "schema_version": VERSION,
        "canonical_contract_version": CANONICAL_CONTRACT_VERSION,
        "assessment_depth": "core",
        "same_contract_used_by_strategic": True,
        "independent_core_scorecard_allowed": False,
        "legacy_transport_identity_preserved": True,
        "human_review_required": True,
        "automatic_approval": False,
        "client_delivery_allowed": False,
    }
    return enriched


def install_canonical_express_contract_binding_v1() -> dict[str, Any]:
    current: Callable[[str, dict[str, Any], dict[str, Any]], Any] = express._record
    if bool(getattr(current, _MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "canonical_contract_version": CANONICAL_CONTRACT_VERSION,
            "completed_express_runs_receive_core_contract": True,
            "same_contract_used_by_strategic": True,
            "independent_core_scorecard_allowed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def record_with_canonical_core_contract(
        run_id: str,
        request_payload: dict[str, Any],
        response: dict[str, Any],
    ) -> Any:
        candidate = (
            canonical_core_response(run_id, request_payload, response)
            if _eligible_completed_response(response)
            else response
        )
        return current(run_id, request_payload, candidate)

    setattr(record_with_canonical_core_contract, _MARKER, True)
    setattr(record_with_canonical_core_contract, "_nico_previous", current)
    express._record = record_with_canonical_core_contract

    return {
        "status": "installed",
        "version": VERSION,
        "canonical_contract_version": CANONICAL_CONTRACT_VERSION,
        "completed_express_runs_receive_core_contract": True,
        "same_contract_used_by_strategic": True,
        "independent_core_scorecard_allowed": False,
        "running_or_failed_responses_modified": False,
        "legacy_transport_identity_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "canonical_core_response",
    "install_canonical_express_contract_binding_v1",
]
