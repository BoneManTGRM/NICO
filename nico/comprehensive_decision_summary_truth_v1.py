from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-decision-summary-truth.v1"
_MARKER = "__nico_comprehensive_decision_summary_truth_v1__"
_LIMITED_STATUSES = {
    "blocked",
    "failed",
    "unavailable",
    "timed_out",
    "review_required",
    "limited",
    "framework_only",
    "not_assessed",
}


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _limited_count(assessment: Mapping[str, Any], stages: list[Mapping[str, Any]]) -> int:
    retained = assessment.get("limited_review_section_count")
    if isinstance(retained, int) and not isinstance(retained, bool) and retained >= 0:
        return retained
    return sum(
        _text(stage.get("status"), 80).casefold() in _LIMITED_STATUSES
        or bool(stage.get("unavailable"))
        for stage in stages
    )


def install_comprehensive_decision_summary_truth_v1() -> dict[str, Any]:
    from nico import comprehensive_report_package as package

    current = package._decision_summary
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _decision_summary(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
    ) -> str:
        maturity = (
            assessment.get("maturity_signal")
            if isinstance(assessment.get("maturity_signal"), Mapping)
            else {}
        )
        level = _text(maturity.get("level") or "Pending", 80)
        score = maturity.get("presented_score", maturity.get("score"))
        score_text = f"{int(score)}/100" if isinstance(score, (int, float)) and not isinstance(score, bool) else "not scored"
        limited = _limited_count(assessment, stages)
        terminal = [
            _text(stage.get("title"), 140)
            for stage in stages
            if _text(stage.get("status"), 80).casefold()
            in {"blocked", "failed", "unavailable", "timed_out"}
        ]
        execution = (
            f"{len(terminal)} automated stage(s) have a terminal execution limitation: {', '.join(terminal[:4])}."
            if terminal
            else "No automated stage represented in this package has a retained terminal execution failure."
        )
        return (
            f"NICO generated an automated Comprehensive Technical Assessment draft for {_text(identity.get('repository'))} "
            f"at immutable commit {_text(identity.get('commit_sha'))}. The evidence-bound maturity signal is "
            f"{level} ({score_text}). {limited} client-review section(s) disclose unavailable, limited, framework-only, "
            f"or stakeholder-dependent evidence. {execution} The package is review-gated: automated evidence and "
            "recommendations are not human approval or client-delivery authorization."
        )

    setattr(_decision_summary, _MARKER, True)
    setattr(_decision_summary, "_nico_previous", current)
    package._decision_summary = _decision_summary
    return {
        "status": "installed",
        "version": VERSION,
        "limited_count_uses_canonical_assessment": True,
        "execution_completion_separate_from_evidence_limitations": True,
        "automated_draft_language_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_decision_summary_truth_v1"]
