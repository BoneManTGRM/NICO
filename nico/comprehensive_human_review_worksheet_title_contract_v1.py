from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-human-review-worksheet-title-contract.v1"
_MARKER = "__nico_human_review_worksheet_title_contract_v1__"

# These are presentation identities for existing human-review worksheets. The
# contract never creates a missing stage and never changes evidence or scoring.
WORKSHEET_TITLE_BY_STAGE_ID: dict[str, str] = {
    "functional_qa": "Functional QA",
    "platform_parity": "Platform Parity",
    "historical_trends_and_change_failure": "Historical Trends and Change Failure",
    "requirements_traceability": "Requirements Traceability",
    "stakeholder_and_business_alignment": "Stakeholder and Business Alignment",
    "risk_reduction_and_executive_briefing": "Risk Reduction and Executive Briefing",
    "six_month_roadmap": "Six-Month Roadmap",
    "staffing_sequencing_and_cost": "Staffing, Sequencing, and Cost",
}
WORKSHEET_TITLES = tuple(WORKSHEET_TITLE_BY_STAGE_ID.values())


def _stage_id(value: Any) -> str:
    return "_".join(str(value or "").strip().casefold().replace("-", "_").split())


def normalize_human_review_worksheet_titles(
    stages: Any,
) -> list[dict[str, Any]]:
    """Apply canonical titles only to worksheets that already exist."""

    normalized: list[dict[str, Any]] = []
    for raw in stages or []:
        if not isinstance(raw, Mapping):
            continue
        stage = deepcopy(dict(raw))
        canonical_title = WORKSHEET_TITLE_BY_STAGE_ID.get(_stage_id(stage.get("stage_id")))
        if canonical_title:
            stage["title"] = canonical_title
        normalized.append(stage)
    return normalized


def install_human_review_worksheet_title_contract_v1() -> dict[str, Any]:
    """Bind canonical worksheet titles at the premium renderer boundary."""

    from nico import v2_premium_report_renderer as premium

    current = premium._canonical_stages
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "canonical_worksheet_titles": True,
            "missing_stages_not_synthesized": True,
            "scores_unchanged": True,
            "candidate_dispositions_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def canonical_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
        return normalize_human_review_worksheet_titles(current(canonical))

    setattr(canonical_stages, _MARKER, True)
    setattr(canonical_stages, "_nico_previous", current)
    premium._canonical_stages = canonical_stages

    return {
        "status": "installed",
        "version": VERSION,
        "canonical_worksheet_titles": True,
        "risk_reduction_title": WORKSHEET_TITLE_BY_STAGE_ID[
            "risk_reduction_and_executive_briefing"
        ],
        "missing_stages_not_synthesized": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "WORKSHEET_TITLE_BY_STAGE_ID",
    "WORKSHEET_TITLES",
    "install_human_review_worksheet_title_contract_v1",
    "normalize_human_review_worksheet_titles",
]
