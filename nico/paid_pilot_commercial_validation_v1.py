"""Fail-closed commercial validation for paid NICO report pilots."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TIERS = ("express", "mid", "full")
MIN_PAID_CASES = {"express": 3, "mid": 3, "full": 2}
MIN_PRICE = {"express": 1000.0, "mid": 3000.0, "full": 7500.0}
MIN_CLIENT_VALUE_SCORE = {"express": 75.0, "mid": 82.0, "full": 88.0}
MIN_ACTION_RATE = {"express": 0.60, "mid": 0.70, "full": 0.75}


def qualify_paid_pilot_commercial_validation(
    pilots: Mapping[str, Sequence[Mapping[str, Any]]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    """Block commercial certification until real paid pilots demonstrate value."""
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for tier in TIERS:
        cases = pilots.get(tier)
        if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
            failures.append(f"{tier}:missing_paid_cases")
            continue
        if len(cases) < MIN_PAID_CASES[tier]:
            failures.append(f"{tier}:insufficient_paid_cases")

        acted = 0
        valid_cases = 0
        for index, case in enumerate(cases):
            if not isinstance(case, Mapping):
                failures.append(f"{tier}:case_{index}:invalid")
                continue
            valid_cases += 1
            for field in (
                "client_id",
                "assessment_id",
                "report_sha256",
                "invoice_id",
                "payment_date",
                "client_reviewer",
                "client_decision",
            ):
                if not str(case.get(field, "")).strip():
                    failures.append(f"{tier}:case_{index}:missing:{field}")

            try:
                if float(case.get("amount_paid", 0)) < MIN_PRICE[tier]:
                    failures.append(f"{tier}:case_{index}:below_minimum_price")
            except (TypeError, ValueError):
                failures.append(f"{tier}:case_{index}:invalid:amount_paid")

            try:
                score = float(case.get("client_value_score", 0))
                if score < MIN_CLIENT_VALUE_SCORE[tier]:
                    failures.append(f"{tier}:case_{index}:low_client_value_score")
            except (TypeError, ValueError):
                failures.append(f"{tier}:case_{index}:invalid:client_value_score")

            if case.get("real_repository") is not True:
                failures.append(f"{tier}:case_{index}:not_real_repository")
            if case.get("evidence_verified") is not True:
                failures.append(f"{tier}:case_{index}:evidence_not_verified")
            if case.get("material_false_positive") is True:
                failures.append(f"{tier}:case_{index}:material_false_positive")
            if case.get("client_acted_on_report") is True:
                acted += 1
            if case.get("refund_requested") is True:
                failures.append(f"{tier}:case_{index}:refund_requested")

        if valid_cases:
            action_rate = acted / valid_cases
            if action_rate < MIN_ACTION_RATE[tier]:
                failures.append(f"{tier}:low_client_action_rate")
        if cases and not any(case.get("renewal_or_follow_on_intent") is True for case in cases if isinstance(case, Mapping)):
            failures.append(f"{tier}:no_renewal_or_follow_on_intent")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
