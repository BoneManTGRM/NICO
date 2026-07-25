from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_score_truth.v1"
_SCORE_LINE = re.compile(r"^(?:technical_score|source_score|presented_score):\s*(\d{1,3})(?:\.0+)?$", re.IGNORECASE)


def _maturity_level(score: int | None) -> str:
    if score is None:
        return "Pending"
    if score >= 82:
        return "Senior"
    if score >= 58:
        return "Mid"
    return "Junior"


def reconcile_scoring_result(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    assessment = output.get("assessment")
    if output.get("status") != "complete" or not isinstance(assessment, dict):
        return output

    from nico.comprehensive_express_quality_v7 import reconcile_comprehensive_assessment

    assessment = reconcile_comprehensive_assessment(assessment)
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_value = int(score) if isinstance(score, (int, float)) else None
    level = _maturity_level(score_value)
    maturity["level"] = level
    assessment["maturity_signal"] = maturity
    output["assessment"] = assessment

    evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
    evidence.update(
        {
            "maturity_level": level,
            "technical_score": score_value,
            "technical_band": maturity.get("score_band_label") or "NOT SCORED",
            "scored_sections": sum(
                1
                for row in assessment.get("scoring_weights") or []
                if isinstance(row, dict) and row.get("included")
            ),
        }
    )
    output["evidence"] = evidence
    output["canonical_score_truth"] = {
        "version": VERSION,
        "reconciled_before_downstream_stages": True,
        "technical_score": score_value,
        "maturity_level": level,
    }
    return output


def wrap_scoring_provider(delegate: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    @wraps(delegate)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        return reconcile_scoring_result(delegate(context))

    return wrapped


def _reported_stage_scores(stages: list[dict[str, Any]]) -> set[int]:
    values: set[int] = set()
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        for line in stage.get("evidence") or []:
            match = _SCORE_LINE.match(str(line or "").strip())
            if match:
                values.add(int(match.group(1)))
    return values


def enforce_report_score_truth(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    assessment = output.get("assessment") if isinstance(output.get("assessment"), dict) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    canonical_score = int(score) if isinstance(score, (int, float)) else None
    stage_scores = _reported_stage_scores(output.get("stage_summaries") or [])

    mismatch = bool(stage_scores and (canonical_score is None or stage_scores != {canonical_score}))
    contract = output.get("report_quality_contract") if isinstance(output.get("report_quality_contract"), dict) else {}
    contract["canonical_score_consistent_across_stages"] = not mismatch
    contract["canonical_score"] = canonical_score
    contract["stage_reported_scores"] = sorted(stage_scores)
    output["report_quality_contract"] = contract

    package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
    package_contract = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}
    package_contract.update(
        {
            "canonical_score_consistent_across_stages": not mismatch,
            "canonical_score": canonical_score,
            "stage_reported_scores": sorted(stage_scores),
        }
    )
    package["report_quality_contract"] = package_contract
    output["report_package"] = package

    if mismatch:
        output["status"] = "blocked"
        output["reason"] = "canonical_score_truth_mismatch"
        package["client_delivery_allowed"] = False
        output["client_delivery_allowed"] = False
    return output


def wrap_report_builder(delegate: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return enforce_report_score_truth(delegate(*args, **kwargs))

    return wrapped


__all__ = [
    "VERSION",
    "enforce_report_score_truth",
    "reconcile_scoring_result",
    "wrap_report_builder",
    "wrap_scoring_provider",
]
