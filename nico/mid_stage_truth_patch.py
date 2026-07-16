from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from nico.mid_score_intelligence import attach_mid_score_intelligence
from nico.mid_static_score_accuracy import install_mid_static_score_accuracy

MID_STAGE_TRUTH_VERSION = "nico.mid_stage_truth.v3"
_MARKER = "_nico_mid_stage_truth_v3"
_ACTIVE = {"queued", "running", "pending", "planned"}
_TERMINAL = {"complete", "completed", "blocked", "failed", "error", "not_started"}
_MID_PRESENTATION_REPLACEMENTS = (
    ("evidence-bound Full Assessment draft", "evidence-bound Mid Assessment draft"),
    ("evidence-bound full assessment draft", "evidence-bound Mid Assessment draft"),
    ("Full Technical Assessment", "Mid Technical Assessment"),
    ("Full Assessment", "Mid Assessment"),
    ("full assessment", "Mid assessment"),
)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _mid_presentation_text(value: Any) -> Any:
    """Correct inherited Full-tier labels only in bounded presentation fields."""

    if not isinstance(value, str):
        return value
    output = value
    for source, replacement in _MID_PRESENTATION_REPLACEMENTS:
        output = output.replace(source, replacement)
    return output


def _normalize_mid_presentation_labels(output: dict[str, Any]) -> None:
    for key in ("executive_summary", "summary", "report_generation_note"):
        if key in output:
            output[key] = _mid_presentation_text(output.get(key))

    assessment = deepcopy(output.get("assessment")) if isinstance(output.get("assessment"), dict) else {}
    if assessment:
        for key in ("executive_summary", "summary", "title", "assessment_name"):
            if key in assessment:
                assessment[key] = _mid_presentation_text(assessment.get(key))
        output["assessment"] = assessment


def _replace_progress(
    progress: list[dict[str, Any]],
    step: str,
    *,
    status: str,
    message: str,
    evidence: dict[str, Any],
) -> None:
    replacement = {
        "step": step,
        "status": status,
        "message": message,
        "evidence": deepcopy(evidence),
    }
    for index, item in enumerate(progress):
        if str(item.get("step") or "") == step:
            progress[index] = replacement
            return
    progress.append(replacement)


def normalize_mid_stage_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    _normalize_mid_presentation_labels(output)
    progress = [deepcopy(item) for item in _list(output.get("progress")) if isinstance(item, dict)]
    report_status = str(output.get("report_generation_status") or "mid_report_generation_pending").lower()
    approval_status = str(output.get("approval_request_status") or "pending").lower()

    for item in progress:
        step = str(item.get("step") or "")
        status = str(item.get("status") or "").lower()
        if step == "scoring" and status in {"complete", "completed"}:
            item["message"] = (
                "Mid Assessment multi-section scorecard was generated from attached same-run repository and scanner evidence."
            )
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            evidence["assessment_type"] = "mid"
            evidence["generic_full_report_generated"] = False
            evidence["score_contract"] = "seven_fixed_technical_weights"
            item["evidence"] = evidence

    report_item = next((item for item in progress if str(item.get("step") or "") == "reports"), None)
    report_item_status = str((report_item or {}).get("status") or "").lower()
    if report_status in {"mid_report_generation_pending", "pending", "planned"} and report_item_status not in _TERMINAL:
        _replace_progress(
            progress,
            "reports",
            status="planned",
            message=(
                "Dedicated Mid draft generation is planned after same-run repository evidence, scanner evidence, and technical scoring are complete."
            ),
            evidence={
                "assessment_type": "mid",
                "report_path": "mid_run",
                "generic_full_report_handler_enabled": False,
                "dedicated_mid_report_enabled": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )

    approval_item = next((item for item in progress if str(item.get("step") or "") == "approval_request"), None)
    approval_item_status = str((approval_item or {}).get("status") or "").lower()
    if approval_status in _ACTIVE and approval_item_status not in _TERMINAL:
        _replace_progress(
            progress,
            "approval_request",
            status="planned",
            message=(
                "Dedicated Mid human-review request is planned after the same-run Mid draft passes the report-quality gate."
            ),
            evidence={
                "assessment_type": "mid",
                "approval_path": "mid_review",
                "generic_full_review_handler_enabled": False,
                "dedicated_mid_review_enabled": True,
                "human_approval_required": True,
                "client_delivery_allowed": False,
            },
        )

    stages = [deepcopy(item) for item in _list(output.get("execution_stages")) if isinstance(item, dict)]
    for stage in stages:
        if str(stage.get("id") or "") == "dedicated_mid_draft_and_review_request" and str(stage.get("status") or "").lower() in {
            "skipped",
            "mid_report_generation_pending",
        }:
            stage["status"] = "planned"
            stage["generic_full_report_generated"] = False
            stage["dedicated_mid_report_enabled"] = True
            stage["dedicated_mid_review_enabled"] = True
    if stages:
        output["execution_stages"] = stages

    output["progress"] = progress
    output["mid_stage_truth_version"] = MID_STAGE_TRUTH_VERSION
    output["mid_presentation_label_truth"] = {
        "generic_full_label_exposed": False,
        "assessment_type": "mid",
        "evidence_or_findings_rewritten": False,
    }
    output["mid_artifact_execution_contract"] = {
        "generic_full_report_handler_enabled": False,
        "generic_full_review_handler_enabled": False,
        "dedicated_mid_report_enabled": True,
        "dedicated_mid_review_enabled": True,
        "same_run_identity_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return attach_mid_score_intelligence(output)


def install_mid_stage_truth_patch() -> dict[str, Any]:
    from nico import mid_assessment_api

    static_score_install = install_mid_static_score_accuracy()
    current: Callable[[dict[str, Any]], dict[str, Any]] = mid_assessment_api._attach_mid_contract
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": MID_STAGE_TRUTH_VERSION,
            "static_score_accuracy": static_score_install,
        }

    @wraps(current)
    def attach_with_mid_stage_truth(result: dict[str, Any]) -> dict[str, Any]:
        return normalize_mid_stage_truth(current(result))

    setattr(attach_with_mid_stage_truth, _MARKER, True)
    setattr(attach_with_mid_stage_truth, "_nico_previous", current)
    mid_assessment_api._attach_mid_contract = attach_with_mid_stage_truth
    return {
        "status": "installed",
        "version": MID_STAGE_TRUTH_VERSION,
        "generic_full_skipped_labels_exposed": False,
        "generic_full_presentation_labels_exposed": False,
        "dedicated_mid_planned_labels_exposed": True,
        "mid_scorecard_wording": True,
        "mid_score_intelligence_attached": True,
        "static_score_accuracy": static_score_install,
        "express_direct_comparison_allowed": False,
        "same_run_identity_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_STAGE_TRUTH_VERSION",
    "install_mid_stage_truth_patch",
    "normalize_mid_stage_truth",
]
