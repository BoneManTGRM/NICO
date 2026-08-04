from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-score-presence-truth.v1"
_MARKER = "__nico_comprehensive_score_presence_truth_v1__"
_NOT_SCORED = {
    "not scored",
    "not_scored",
    "unscored",
    "sin puntuacion",
    "sin puntuación",
}


def _text(value: Any, limit: int = 300) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _numeric(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        return max(0, min(100, int(round(value))))
    return None


def _explicitly_not_scored(assessment: Mapping[str, Any]) -> bool:
    maturity = (
        assessment.get("maturity_signal")
        if isinstance(assessment.get("maturity_signal"), Mapping)
        else {}
    )
    values = (
        maturity.get("level"),
        maturity.get("score_status"),
        assessment.get("score_status"),
        assessment.get("technical_score_status"),
    )
    for value in values:
        normalized = _text(value).casefold().replace("-", " ")
        if normalized in _NOT_SCORED or "not scored" in normalized or "sin puntuacion" in normalized:
            return True
    return False


def install_comprehensive_score_presence_truth_v1() -> dict[str, Any]:
    from nico import comprehensive_client_truth_canonical_v2 as truth

    current = truth._validate_decision_facts
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _validate_decision_facts(
        canonical: Mapping[str, Any],
        assessment: Mapping[str, Any],
        surfaces: Mapping[str, str],
    ) -> None:
        identity = (
            canonical.get("identity")
            if isinstance(canonical.get("identity"), Mapping)
            else {}
        )
        repository = _text(identity.get("repository"))
        commit = _text(identity.get("commit_sha"))
        if not repository or not commit:
            raise ValueError("canonical Comprehensive identity is incomplete")

        stages = [
            stage
            for stage in canonical.get("stage_summaries") or []
            if isinstance(stage, Mapping)
        ]
        limited = truth._limited_count(assessment, stages)
        language = _text(
            canonical.get("report_language")
            or canonical.get("locale")
            or identity.get("report_language")
            or "en",
            20,
        ).casefold()
        maturity = (
            assessment.get("maturity_signal")
            if isinstance(assessment.get("maturity_signal"), Mapping)
            else {}
        )
        if _explicitly_not_scored(assessment):
            technical = None
            adjusted = None
        else:
            technical = _numeric(
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("presented_score"),
                maturity.get("score"),
            )
            adjusted = _numeric(
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
            )

        for name, value in surfaces.items():
            if repository not in value or commit not in value:
                raise ValueError(
                    f"{name} omitted canonical repository or exact commit identity"
                )
            if technical is not None and f"{technical}/100" not in value:
                raise ValueError(
                    f"{name} omitted the canonical technical score {technical}/100"
                )
            if adjusted is not None and f"{adjusted}/100" not in value:
                raise ValueError(
                    f"{name} omitted the canonical evidence-adjusted score {adjusted}/100"
                )
            if language.startswith("es"):
                if str(limited) not in value:
                    raise ValueError(
                        f"{name} omitted the canonical limited-review count {limited}"
                    )
            elif f"{limited} client-review section(s)" not in value:
                raise ValueError(
                    f"{name} does not render the canonical limited-review count {limited}"
                )

    setattr(_validate_decision_facts, _MARKER, True)
    setattr(_validate_decision_facts, "_nico_previous", current)
    truth._validate_decision_facts = _validate_decision_facts
    return {
        "status": "installed",
        "version": VERSION,
        "not_scored_state_does_not_require_zero_score": True,
        "numeric_scores_required_when_canonically_scored": True,
        "unknown_scores_not_converted_to_zero": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_score_presence_truth_v1",
]
