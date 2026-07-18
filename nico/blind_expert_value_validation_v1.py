"""Fail-closed validation for blind expert review of real NICO reports."""

from __future__ import annotations

from typing import Any, Mapping

TIERS = ("express", "mid", "full")
MIN_CASES = {"express": 3, "mid": 3, "full": 3}
MIN_MEDIAN_SCORE = {"express": 75.0, "mid": 82.0, "full": 88.0}
MIN_WILLINGNESS_TO_PAY = {"express": 1000.0, "mid": 3000.0, "full": 7500.0}


def qualify_blind_expert_validation(
    evidence: Mapping[str, Mapping[str, Any]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for tier in TIERS:
        record = evidence.get(tier)
        if not isinstance(record, Mapping):
            failures.append(f"{tier}:missing_validation")
            continue

        cases = record.get("cases")
        if not isinstance(cases, list) or len(cases) < MIN_CASES[tier]:
            failures.append(f"{tier}:insufficient_real_cases")
            continue

        for index, case in enumerate(cases):
            if case.get("real_repository") is not True:
                failures.append(f"{tier}:case_{index}:not_real_repository")
            if case.get("reviewer_blinded") is not True:
                failures.append(f"{tier}:case_{index}:reviewer_not_blinded")
            if case.get("evidence_verified") is not True:
                failures.append(f"{tier}:case_{index}:evidence_not_verified")
            if int(case.get("material_false_positives", 1)) != 0:
                failures.append(f"{tier}:case_{index}:material_false_positives")
            for field in ("report_sha256", "assessment_id", "reviewer", "client_decision"):
                if not str(case.get(field, "")).strip():
                    failures.append(f"{tier}:case_{index}:missing:{field}")

        try:
            if float(record.get("median_expert_score", 0)) < MIN_MEDIAN_SCORE[tier]:
                failures.append(f"{tier}:low_median_expert_score")
        except (TypeError, ValueError):
            failures.append(f"{tier}:invalid_median_expert_score")

        try:
            if float(record.get("median_willingness_to_pay", 0)) < MIN_WILLINGNESS_TO_PAY[tier]:
                failures.append(f"{tier}:low_willingness_to_pay")
        except (TypeError, ValueError):
            failures.append(f"{tier}:invalid_willingness_to_pay")

        if record.get("client_action_confirmed") is not True:
            failures.append(f"{tier}:client_action_not_confirmed")
        if record.get("comparison_to_human_consultant_complete") is not True:
            failures.append(f"{tier}:human_comparison_incomplete")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
