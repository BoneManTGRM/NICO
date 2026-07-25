from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_score_truth.v3"
_SCORE_LINE = re.compile(
    r"^(?P<field>technical_score|source_score|presented_score|evidence_adjusted_score|canonical_evidence_adjusted_score):\s*(?P<score>\d{1,3})(?:\.0+)?$",
    re.IGNORECASE,
)


def _maturity_level(score: int | None) -> str:
    if score is None:
        return "Pending"
    if score >= 82:
        return "Senior"
    if score >= 58:
        return "Mid"
    return "Junior"


def _number(value: Any) -> int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0, min(100, int(round(value))))
    return None


def _technical_score(assessment: dict[str, Any]) -> int | None:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    for candidate in (
        assessment.get("technical_score"),
        maturity.get("technical_score"),
        maturity.get("score"),
        maturity.get("source_score"),
    ):
        value = _number(candidate)
        if value is not None:
            return value
    return None


def _evidence_adjusted_score(assessment: dict[str, Any]) -> int | None:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    for candidate in (
        assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"),
        maturity.get("presented_score"),
    ):
        value = _number(candidate)
        if value is not None:
            return value
    return _technical_score(assessment)


def _already_reconciled(assessment: dict[str, Any]) -> bool:
    marker = assessment.get("comprehensive_express_quality")
    quality = assessment.get("canonical_evidence_score_contract")
    return (
        isinstance(marker, dict)
        and marker.get("status") == "complete"
        and isinstance(assessment.get("scoring_weights"), list)
        and _technical_score(assessment) is not None
        and _evidence_adjusted_score(assessment) is not None
        and (not isinstance(quality, dict) or quality.get("immutable_for_downstream_report_formats") is True)
    )


def _stamp_canonical_scores(assessment: dict[str, Any]) -> tuple[dict[str, Any], int | None, int | None]:
    output = deepcopy(assessment)
    technical = _technical_score(output)
    adjusted = _evidence_adjusted_score(output)
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    maturity["score"] = technical
    maturity["source_score"] = technical
    maturity["technical_score"] = technical
    maturity["presented_score"] = adjusted
    maturity["evidence_adjusted_score"] = adjusted
    maturity["canonical_evidence_adjusted_score"] = adjusted
    output["maturity_signal"] = maturity
    output["technical_score"] = technical
    output["evidence_adjusted_score"] = adjusted
    output["canonical_evidence_adjusted_score"] = adjusted
    return output, technical, adjusted


def reconcile_scoring_result(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    assessment = output.get("assessment")
    if output.get("status") != "complete" or not isinstance(assessment, dict):
        return output

    from nico.comprehensive_express_quality_v7 import reconcile_comprehensive_assessment

    assessment = deepcopy(assessment) if _already_reconciled(assessment) else reconcile_comprehensive_assessment(assessment)
    assessment, score_value, adjusted_value = _stamp_canonical_scores(assessment)
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    level = _maturity_level(score_value)
    maturity["level"] = level
    assessment["maturity_signal"] = maturity
    output["assessment"] = assessment

    evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
    evidence.update(
        {
            "maturity_level": level,
            "technical_score": score_value,
            "evidence_adjusted_score": adjusted_value,
            "canonical_evidence_adjusted_score": adjusted_value,
            "technical_band": maturity.get("score_band_label") or "NOT SCORED",
            "scored_sections": sum(
                1
                for row in assessment.get("scoring_weights") or []
                if isinstance(row, dict) and row.get("included")
            ),
        }
    )
    output["evidence"] = evidence
    output["canonical_evidence_adjusted_score"] = adjusted_value
    output["canonical_score_truth"] = {
        "version": VERSION,
        "reconciled_before_downstream_stages": True,
        "reconciliation_reused_when_complete": _already_reconciled(assessment),
        "technical_score": score_value,
        "evidence_adjusted_score": adjusted_value,
        "canonical_evidence_adjusted_score": adjusted_value,
        "maturity_level": level,
        "technical_and_assurance_scores_not_conflated": True,
        "canonical_evidence_score_immutable_downstream": True,
    }
    return output


def wrap_scoring_provider(delegate: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    @wraps(delegate)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        return reconcile_scoring_result(delegate(context))

    return wrapped


def _reported_stage_scores(stages: list[dict[str, Any]]) -> dict[str, set[int]]:
    values: dict[str, set[int]] = {"technical": set(), "adjusted": set()}
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        evidence = stage.get("evidence") or []
        if isinstance(evidence, dict):
            evidence = [f"{key}: {value}" for key, value in evidence.items()]
        for line in evidence if isinstance(evidence, list) else []:
            match = _SCORE_LINE.match(str(line or "").strip())
            if not match:
                continue
            field = match.group("field").casefold()
            score = int(match.group("score"))
            if field in {"technical_score", "source_score"}:
                values["technical"].add(score)
            else:
                values["adjusted"].add(score)
    return values


def _existing_json_scores(package: dict[str, Any]) -> tuple[set[int], set[int]]:
    payload = package.get("json") if isinstance(package.get("json"), dict) else {}
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else payload
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    technical = {
        value
        for raw in (assessment.get("technical_score"), maturity.get("technical_score"), maturity.get("score"))
        if (value := _number(raw)) is not None
    }
    adjusted = {
        value
        for raw in (
            assessment.get("canonical_evidence_adjusted_score"),
            assessment.get("evidence_adjusted_score"),
            maturity.get("canonical_evidence_adjusted_score"),
            maturity.get("evidence_adjusted_score"),
            maturity.get("presented_score"),
        )
        if (value := _number(raw)) is not None
    }
    return technical, adjusted


def enforce_report_score_truth(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    assessment = output.get("assessment") if isinstance(output.get("assessment"), dict) else {}
    assessment, canonical_score, adjusted_score = _stamp_canonical_scores(assessment)
    output["assessment"] = assessment
    output["canonical_evidence_adjusted_score"] = adjusted_score

    stage_scores = _reported_stage_scores(output.get("stage_summaries") or [])
    package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
    json_technical, json_adjusted = _existing_json_scores(package)

    technical_mismatch = bool(
        (stage_scores["technical"] and (canonical_score is None or stage_scores["technical"] != {canonical_score}))
        or (json_technical and (canonical_score is None or json_technical != {canonical_score}))
    )
    adjusted_mismatch = bool(
        (stage_scores["adjusted"] and (adjusted_score is None or stage_scores["adjusted"] != {adjusted_score}))
        or (json_adjusted and (adjusted_score is None or json_adjusted != {adjusted_score}))
    )

    contract = output.get("report_quality_contract") if isinstance(output.get("report_quality_contract"), dict) else {}
    contract.update(
        {
            "canonical_score_consistent_across_stages": not technical_mismatch,
            "canonical_evidence_adjusted_score_consistent_across_stages": not adjusted_mismatch,
            "canonical_score": canonical_score,
            "evidence_adjusted_score": adjusted_score,
            "canonical_evidence_adjusted_score": adjusted_score,
            "stage_reported_scores": sorted(stage_scores["technical"]),
            "stage_reported_evidence_adjusted_scores": sorted(stage_scores["adjusted"]),
            "json_reported_scores": sorted(json_technical),
            "json_reported_evidence_adjusted_scores": sorted(json_adjusted),
            "technical_and_assurance_scores_not_conflated": True,
            "all_report_formats_must_use_canonical_evidence_adjusted_score": True,
        }
    )
    output["report_quality_contract"] = contract

    package_contract = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}
    package_contract.update(contract)
    package["report_quality_contract"] = package_contract
    package["technical_score"] = canonical_score
    package["evidence_adjusted_score"] = adjusted_score
    package["canonical_evidence_adjusted_score"] = adjusted_score
    json_payload = package.get("json") if isinstance(package.get("json"), dict) else {}
    json_payload["technical_score"] = canonical_score
    json_payload["evidence_adjusted_score"] = adjusted_score
    json_payload["canonical_evidence_adjusted_score"] = adjusted_score
    package["json"] = json_payload
    output["report_package"] = package

    if technical_mismatch or adjusted_mismatch:
        output["status"] = "blocked"
        if technical_mismatch and adjusted_mismatch:
            output["reason"] = "canonical_score_truth_mismatch"
        elif adjusted_mismatch:
            output["reason"] = "canonical_evidence_adjusted_score_mismatch"
        else:
            output["reason"] = "canonical_technical_score_mismatch"
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
