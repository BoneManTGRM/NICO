from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

MID_APPROVAL_TRUTH_FREEZE_VERSION = "nico.mid_approval_truth_freeze.v1"
_APPROVAL_MARKER = "_nico_mid_approval_truth_freeze_v1"
_TERMINAL_MARKER = "_nico_mid_approval_truth_freeze_terminal_v1"
_STATUS_MARKER = "_nico_mid_approval_truth_freeze_status_v1"
_STALE_MARKERS = (
    "stale relative to the current truth model",
    "stale relative to the current review packet",
)
_COMPLETE = {"complete", "completed", "attached", "verified"}
_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _stale(value: Any) -> bool:
    text = " ".join(str(value or "").lower().split())
    return any(marker in text for marker in _STALE_MARKERS)


def _approval_error(response: dict[str, Any]) -> str:
    for key in ("approval_request_error", "error", "message"):
        value = str(response.get(key) or "")
        if value:
            return value
    for item in _list(response.get("progress")):
        if not isinstance(item, dict):
            continue
        if str(item.get("step") or "") in {"approval_request", "human_review_request"}:
            return str(item.get("message") or "")
    return ""


def _progress_status(response: dict[str, Any], step: str) -> str:
    for item in _list(response.get("progress")):
        if isinstance(item, dict) and str(item.get("step") or "") == step:
            return str(item.get("status") or "").lower()
    return ""


def _scope_matches(record: dict[str, Any], customer_id: str, project_id: str) -> bool:
    request = _dict(record.get("request"))
    stored_customer = str(record.get("customer_id") or request.get("customer_id") or "default_customer")
    stored_project = str(record.get("project_id") or request.get("project_id") or "default_project")
    return stored_customer == customer_id and stored_project == project_id


def _weighted_score(truth: dict[str, Any]) -> int | None:
    sections = {
        str(item.get("id") or ""): item
        for item in _list(truth.get("sections"))
        if isinstance(item, dict)
    }
    weighted = 0
    total = 0
    for section_id, weight in _WEIGHTS.items():
        section = sections.get(section_id)
        if not section:
            return None
        try:
            score = int(section.get("score"))
        except (TypeError, ValueError):
            return None
        if not 0 <= score <= 100:
            return None
        weighted += score * weight
        total += weight
    return round(weighted / total) if total == 100 else None


def _maturity_level(score: int) -> str:
    return "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"


def _truth_hash(value: Any) -> str:
    from nico.mid_truth_identity_consistency import semantic_mid_truth_hash

    return semantic_mid_truth_hash(value)


def stabilize_mid_approval_truth(
    record: dict[str, Any],
    *,
    store: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze one canonical truth snapshot before report and approval identity work.

    This does not change scanner findings or section scores. It persists the
    current canonical truth model and reconciles only duplicated display-score
    fields to the already-retained seven-section weighted score.
    """

    from nico import mid_assessment_approval, mid_assessment_runs
    from nico.storage import utc_now

    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        return record, {"status": "not_applicable"}

    current_truth = mid_assessment_approval._current_truth(record, store)
    if not isinstance(current_truth, dict) or not current_truth.get("sections"):
        return record, {"status": "unavailable"}

    updated = deepcopy(record)
    response = deepcopy(_dict(updated.get("response")))
    retained_truth = deepcopy(_dict(response.get("mid_truth_status")))
    prior_hash = _truth_hash(retained_truth) if retained_truth else ""
    current_hash = _truth_hash(current_truth)
    weighted_score = _weighted_score(current_truth)

    response["mid_truth_status"] = deepcopy(current_truth)
    response["evidence_coverage"] = deepcopy(_dict(current_truth.get("evidence_coverage")))

    assessment = deepcopy(_dict(response.get("assessment")))
    if assessment:
        assessment["sections"] = deepcopy(_list(current_truth.get("sections")))
        assessment["evidence_coverage"] = deepcopy(_dict(current_truth.get("evidence_coverage")))
        assessment["truth_status_summary"] = deepcopy(_dict(current_truth.get("summary")))
        if weighted_score is not None:
            maturity = deepcopy(_dict(assessment.get("maturity_signal")))
            previous_score = maturity.get("score")
            maturity["score"] = weighted_score
            maturity["level"] = _maturity_level(weighted_score)
            maturity["score_source"] = "seven_weighted_technical_sections"
            maturity["display_score_reconciled"] = previous_score != weighted_score
            assessment["maturity_signal"] = maturity
        response["assessment"] = assessment

    if weighted_score is not None:
        maturity = deepcopy(_dict(assessment.get("maturity_signal")))
        response["technical_score"] = weighted_score
        response["maturity_signal"] = maturity

    changed = prior_hash != current_hash
    prior_display_score = _dict(_dict(record.get("response")).get("assessment")).get("maturity_signal", {})
    prior_display_score = _dict(prior_display_score).get("score")
    score_reconciled = weighted_score is not None and prior_display_score != weighted_score
    response["mid_approval_truth_freeze"] = {
        "status": "frozen",
        "version": MID_APPROVAL_TRUTH_FREEZE_VERSION,
        "prior_truth_sha256": prior_hash,
        "current_truth_sha256": current_hash,
        "truth_changed": changed,
        "weighted_technical_score": weighted_score,
        "prior_display_score": prior_display_score,
        "display_score_reconciled": score_reconciled,
        "scanner_rerun": False,
        "repository_recaptured": False,
        "section_scores_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    updated["response"] = mid_assessment_runs._retained_response(response)
    updated["updated_at"] = utc_now()
    store.put("assessment_runs", str(updated.get("run_id") or ""), updated)
    return updated, deepcopy(response["mid_approval_truth_freeze"])


def _quality_allows_review(report: dict[str, Any]) -> bool:
    if str(report.get("status") or "").lower() != "complete":
        return False
    manifest = _dict(report.get("report_quality_manifest"))
    return not manifest or str(manifest.get("status") or "").lower() in {
        "ready_for_human_review",
        "review_required",
        "complete",
        "passed",
    }


def _repairable_stale_record(record: Any, store: Any) -> bool:
    if not isinstance(record, dict) or str(record.get("workflow") or "") != "mid_assessment":
        return False
    response = _dict(record.get("response"))
    if str(response.get("report_generation_status") or "").lower() != "complete":
        return False
    if str(response.get("approval_request_status") or "").lower() != "blocked":
        return False
    if not _stale(_approval_error(response)):
        return False
    if _progress_status(response, "scoring") not in _COMPLETE:
        return False
    report_id = str(_dict(response.get("mid_report")).get("report_id") or record.get("report_id") or "")
    report = store.get("reports", report_id) if report_id else None
    return isinstance(report, dict) and _quality_allows_review(report)


async def _request_scope(request: Any) -> tuple[str, str]:
    payload: dict[str, Any] = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = {}
    query = getattr(request, "query_params", {})
    customer_id = str(payload.get("customer_id") or query.get("customer_id") or "default_customer")[:120]
    project_id = str(payload.get("project_id") or query.get("project_id") or "default_project")[:120]
    return customer_id, project_id


def install_mid_approval_truth_freeze() -> dict[str, Any]:
    from nico import mid_assessment_api, mid_assessment_approval
    from nico import mid_terminal_truth_patch as terminal
    from nico import mid_truth_identity_consistency as consistency
    from nico import mid_truth_identity_transport as transport
    from nico.storage import STORE

    installed: dict[str, bool] = {}

    current_approval: Callable[..., dict[str, Any]] = mid_assessment_approval.request_mid_approval
    if not getattr(current_approval, _APPROVAL_MARKER, False):
        @wraps(current_approval)
        def approval_with_frozen_truth(
            run_id: str,
            customer_id: str,
            project_id: str,
            admin_token: str = "",
            store: Any = None,
        ) -> dict[str, Any]:
            active = store or STORE
            record = active.get("assessment_runs", run_id)
            freeze: dict[str, Any] = {"status": "not_run"}
            if isinstance(record, dict) and _scope_matches(record, customer_id, project_id):
                _, freeze = stabilize_mid_approval_truth(record, store=active)
            result = current_approval(
                run_id,
                customer_id,
                project_id,
                admin_token=admin_token,
                store=active,
            )
            if result.get("status") == "blocked" and _stale(result.get("error")):
                refreshed = active.get("assessment_runs", run_id)
                if isinstance(refreshed, dict) and _scope_matches(refreshed, customer_id, project_id):
                    _, freeze = stabilize_mid_approval_truth(refreshed, store=active)
                    result = current_approval(
                        run_id,
                        customer_id,
                        project_id,
                        admin_token=admin_token,
                        store=active,
                    )
            output = deepcopy(result)
            output["truth_freeze"] = freeze
            return output

        setattr(approval_with_frozen_truth, _APPROVAL_MARKER, True)
        setattr(approval_with_frozen_truth, "_nico_previous", current_approval)
        mid_assessment_approval.request_mid_approval = approval_with_frozen_truth
        mid_assessment_api.request_mid_approval = approval_with_frozen_truth
        installed["approval_truth_freeze"] = True

    current_terminal: Callable[[dict[str, Any]], dict[str, Any] | None] = terminal._terminal_retained_response
    if not getattr(current_terminal, _TERMINAL_MARKER, False):
        @wraps(current_terminal)
        def terminal_with_repair_projection(record: dict[str, Any]) -> dict[str, Any] | None:
            if _repairable_stale_record(record, STORE):
                return transport.project_stale_mid_approval_repair(record)
            return current_terminal(record)

        setattr(terminal_with_repair_projection, _TERMINAL_MARKER, True)
        setattr(terminal_with_repair_projection, "_nico_previous", current_terminal)
        terminal._terminal_retained_response = terminal_with_repair_projection
        installed["terminal_repair_projection"] = True

    current_status: Callable[..., Any] = terminal.mid_status_endpoint
    if not getattr(current_status, _STATUS_MARKER, False):
        @wraps(current_status)
        async def status_with_truth_freeze_repair(run_id: str, request: Any) -> dict[str, Any]:
            customer_id, project_id = await _request_scope(request)
            record = STORE.get("assessment_runs", run_id)
            if (
                isinstance(record, dict)
                and _scope_matches(record, customer_id, project_id)
                and _repairable_stale_record(record, STORE)
            ):
                stabilized, freeze = stabilize_mid_approval_truth(record, store=STORE)
                repaired = consistency.repair_stale_mid_approval(stabilized, store=STORE)
                if isinstance(repaired, dict):
                    repaired["truth_freeze"] = freeze
                    repaired["status_read_path"] = {
                        "version": MID_APPROVAL_TRUTH_FREEZE_VERSION,
                        "mode": "same_run_truth_freeze_and_approval_repair",
                        "read_only": False,
                        "tenant_scope_validated": True,
                        "repository_recaptured": False,
                        "scanner_rerun": False,
                        "replacement_run_created": False,
                    }
                    return repaired
            return await current_status(run_id, request)

        setattr(status_with_truth_freeze_repair, _STATUS_MARKER, True)
        setattr(status_with_truth_freeze_repair, "_nico_previous", current_status)
        terminal.mid_status_endpoint = status_with_truth_freeze_repair
        installed["post_status_repair"] = True

    return {
        "status": "installed" if installed else "already_installed",
        "version": MID_APPROVAL_TRUTH_FREEZE_VERSION,
        "installed": installed,
        "canonical_truth_frozen_before_report_approval": True,
        "display_score_source": "seven_weighted_technical_sections",
        "section_scores_changed": False,
        "repository_recaptured": False,
        "scanner_rerun": False,
        "replacement_run_created": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_APPROVAL_TRUTH_FREEZE_VERSION",
    "install_mid_approval_truth_freeze",
    "stabilize_mid_approval_truth",
]
