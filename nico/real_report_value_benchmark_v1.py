"""Qualification for real generated report value."""

from __future__ import annotations

from typing import Any, Mapping

TIERS = ("express", "mid", "full")
MIN_EXPERT_SCORE = {"express": 70.0, "mid": 80.0, "full": 88.0}
MIN_USEFULNESS_SCORE = {"express": 75.0, "mid": 85.0, "full": 90.0}
MIN_REPLACEMENT_VALUE = {"express": 1000.0, "mid": 3000.0, "full": 7500.0}


def qualify_real_report_value(
    benchmarks: Mapping[str, Mapping[str, Any]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for tier in TIERS:
        record = benchmarks.get(tier)
        if not isinstance(record, Mapping):
            failures.append(f"{tier}:missing_benchmark")
            continue

        for field in ("assessment_id", "report_sha256", "snapshot_sha", "reviewer"):
            if not str(record.get(field, "")).strip():
                failures.append(f"{tier}:missing:{field}")

        try:
            if float(record.get("expert_equivalence_score", 0)) < MIN_EXPERT_SCORE[tier]:
                failures.append(f"{tier}:low_expert_equivalence")
        except (TypeError, ValueError):
            failures.append(f"{tier}:invalid_expert_equivalence")

        try:
            if float(record.get("decision_usefulness_score", 0)) < MIN_USEFULNESS_SCORE[tier]:
                failures.append(f"{tier}:low_decision_usefulness")
        except (TypeError, ValueError):
            failures.append(f"{tier}:invalid_decision_usefulness")

        try:
            if float(record.get("estimated_replacement_value", 0)) < MIN_REPLACEMENT_VALUE[tier]:
                failures.append(f"{tier}:insufficient_replacement_value")
        except (TypeError, ValueError):
            failures.append(f"{tier}:invalid_replacement_value")

        for field in (
            "real_generated_report",
            "evidence_verified",
            "findings_non_duplicate",
            "client_would_act",
            "independent_review_complete",
        ):
            if record.get(field) is not True:
                failures.append(f"{tier}:{field}:failed")

        if int(record.get("material_false_positives", 1)) != 0:
            failures.append(f"{tier}:material_false_positives")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
