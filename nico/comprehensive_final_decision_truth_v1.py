from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_review_report_truth_v1 import (
    _REPORT_STAGE_IDS,
    _synchronize_package,
    build_review_truth,
)

VERSION = "nico.comprehensive_final_decision_truth.v1"
_ALLOWED_DECISIONS = {"approved", "rejected", "request_more_evidence"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def synchronize_final_decision_truth(
    record: Mapping[str, Any],
    *,
    decision: str,
    reviewer: str,
    reviewer_role: str,
    decision_reason: str,
    decided_at: str | None,
) -> dict[str, Any]:
    """Project the explicit human package decision before artifact acceptance.

    The report analysis is not regenerated. The existing single Comprehensive
    package is re-projected from canonical review evidence so the exact artifacts
    hashed by the accepted-edition receipt state the current final-human-decision
    truth. Client delivery remains a separate gate and therefore stays pending for
    an approved decision until the delivery package is successfully certified.
    """

    normalized = _text(decision).casefold()
    if normalized not in _ALLOWED_DECISIONS:
        raise ValueError("invalid_decision")
    if not _text(reviewer):
        raise ValueError("reviewer_required")
    if not _text(reviewer_role):
        raise ValueError("reviewer_role_required")
    if not _text(decision_reason):
        raise ValueError("decision_reason_required")

    updated = deepcopy(dict(record))
    if updated.get("human_review_completed") is True or isinstance(
        updated.get("accepted_edition"), Mapping
    ):
        raise ValueError("final_decision_truth_requires_unaccepted_report")

    truth = build_review_truth(updated)
    truth.update(
        {
            "final_human_approval_status": normalized,
            "client_delivery_authorization_status": (
                "pending_authorization" if normalized == "approved" else "blocked"
            ),
            "final_decision_reviewer": _text(reviewer),
            "final_decision_reviewer_role": _text(reviewer_role),
            "final_decision_reason": _text(decision_reason),
            "final_decided_at": _text(decided_at),
            "final_human_approval_is_separate_from_human_disposition": True,
            "client_delivery_requires_separate_successful_authorization": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )

    stage_results = updated.get("stage_results")
    if isinstance(stage_results, Mapping):
        stages = deepcopy(dict(stage_results))
        for stage_id in _REPORT_STAGE_IDS:
            stage = stages.get(stage_id)
            if not isinstance(stage, Mapping):
                continue
            stage_copy = deepcopy(dict(stage))
            for key in ("report_package", "reports"):
                package = stage_copy.get(key)
                if isinstance(package, Mapping) and (
                    package.get("json")
                    or package.get("markdown")
                    or package.get("pdf_base64")
                ):
                    package_copy = deepcopy(dict(package))
                    _synchronize_package(package_copy, truth)
                    stage_copy[key] = package_copy
            stages[stage_id] = stage_copy
        updated["stage_results"] = stages

    top = updated.get("reports")
    if isinstance(top, Mapping) and (
        top.get("json") or top.get("markdown") or top.get("pdf_base64")
    ):
        top_copy = deepcopy(dict(top))
        _synchronize_package(top_copy, truth)
        updated["reports"] = top_copy

    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = ["VERSION", "synchronize_final_decision_truth"]
