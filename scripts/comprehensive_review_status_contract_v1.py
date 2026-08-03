from __future__ import annotations

from typing import Any, Mapping

VERSION = "nico.comprehensive-review-status-contract.v1"

PROVISIONAL_REVIEW_STATUSES = {
    "PROVISIONAL STRONG — HUMAN REVIEW REQUIRED",
    "FUERTE PROVISIONAL — REVISIÓN HUMANA REQUERIDA",
}
REVIEW_REQUIRED_ASSURANCE_STATUSES = {
    "human_review_required",
    "review_required",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def review_required_count(section: Mapping[str, Any]) -> int:
    direct = _integer(section.get("review_required_candidates"))
    if direct:
        return direct
    score_contract = (
        section.get("score_contract")
        if isinstance(section.get("score_contract"), Mapping)
        else {}
    )
    return _integer(score_contract.get("review_required_count"))


def assurance_only_scoring_verified(section: Mapping[str, Any]) -> bool:
    effect = _text(section.get("score_effect")).casefold().replace("_", "-")
    if effect == "assurance-only until triaged":
        return True
    score_contract = (
        section.get("score_contract")
        if isinstance(section.get("score_contract"), Mapping)
        else {}
    )
    return (
        score_contract.get("unverified_candidate_volume_affects_assurance_only") is True
        and score_contract.get("unverified_candidate_volume_affects_technical_score") is False
    )


def assert_section_status_contract(
    section: Mapping[str, Any],
    *,
    label: str,
    score: int,
    status: str,
    numeric_status: str,
) -> str:
    """Require numeric status unless review-required candidates justify provisional status."""

    normalized_status = _text(status).upper()
    candidates = review_required_count(section)
    if not candidates:
        if normalized_status != numeric_status:
            raise AssertionError(
                f"canonical JSON section {label} presents {score}/100 with status "
                f"{normalized_status or 'missing'}, expected {numeric_status}"
            )
        return normalized_status

    if numeric_status != "STRONG":
        raise AssertionError(
            f"canonical JSON section {label} has {candidates} review-required candidates "
            f"but numeric status {numeric_status} has no authorized provisional contract"
        )
    if normalized_status not in PROVISIONAL_REVIEW_STATUSES:
        raise AssertionError(
            f"canonical JSON section {label} has {candidates} review-required candidates "
            f"but presents {score}/100 with status {normalized_status or 'missing'}; "
            "expected PROVISIONAL STRONG — HUMAN REVIEW REQUIRED"
        )
    if section.get("human_review_required") is not True:
        raise AssertionError(
            f"canonical JSON section {label} uses provisional status without mandatory human review"
        )
    assurance_status = _text(section.get("assurance_status")).casefold()
    if assurance_status not in REVIEW_REQUIRED_ASSURANCE_STATUSES:
        raise AssertionError(
            f"canonical JSON section {label} uses provisional status with unsupported "
            f"assurance status {assurance_status or 'missing'}"
        )
    if not assurance_only_scoring_verified(section):
        raise AssertionError(
            f"canonical JSON section {label} uses provisional status without assurance-only scoring"
        )
    return normalized_status


__all__ = [
    "PROVISIONAL_REVIEW_STATUSES",
    "REVIEW_REQUIRED_ASSURANCE_STATUSES",
    "VERSION",
    "assert_section_status_contract",
    "assurance_only_scoring_verified",
    "review_required_count",
]
