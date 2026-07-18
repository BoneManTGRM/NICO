"""Validate production pilot evidence before commercial certification."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TIERS = ("express", "mid", "full")
MIN_CASES = {"express": 3, "mid": 3, "full": 3}
MIN_PRICE = {"express": 1000.0, "mid": 3000.0, "full": 7500.0}


def qualify_production_pilot_registry(
    registry: Mapping[str, Sequence[Mapping[str, Any]]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    seen_assessments: set[str] = set()
    seen_receipts: set[str] = set()

    for tier in TIERS:
        cases = registry.get(tier)
        if not isinstance(cases, Sequence) or isinstance(cases, (str, bytes)):
            failures.append(f"{tier}:missing_cases")
            continue
        if len(cases) < MIN_CASES[tier]:
            failures.append(f"{tier}:insufficient_cases")

        for index, case in enumerate(cases):
            prefix = f"{tier}:case_{index}"
            if not isinstance(case, Mapping):
                failures.append(f"{prefix}:invalid")
                continue

            for field in (
                "assessment_id",
                "repository_identity",
                "report_sha256",
                "deployment_sha",
                "payment_receipt_id",
                "client_reviewer",
                "completed_at",
            ):
                if not str(case.get(field, "")).strip():
                    failures.append(f"{prefix}:missing:{field}")

            assessment_id = str(case.get("assessment_id", ""))
            receipt_id = str(case.get("payment_receipt_id", ""))
            if assessment_id:
                if assessment_id in seen_assessments:
                    failures.append(f"{prefix}:duplicate_assessment")
                seen_assessments.add(assessment_id)
            if receipt_id:
                if receipt_id in seen_receipts:
                    failures.append(f"{prefix}:duplicate_receipt")
                seen_receipts.add(receipt_id)

            try:
                if float(case.get("amount_paid", 0)) < MIN_PRICE[tier]:
                    failures.append(f"{prefix}:below_minimum_price")
            except (TypeError, ValueError):
                failures.append(f"{prefix}:invalid_amount_paid")

            for field in (
                "production_run",
                "authorized_repository",
                "artifacts_downloaded",
                "manual_review_complete",
                "evidence_verified",
                "client_confirmed_value",
                "client_acted_on_report",
                "no_refund_requested",
            ):
                if case.get(field) is not True:
                    failures.append(f"{prefix}:{field}:failed")

            if int(case.get("material_false_positives", 1)) != 0:
                failures.append(f"{prefix}:material_false_positives")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
