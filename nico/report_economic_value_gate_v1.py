"""Fail-closed qualification for reports sold as high-value technical oversight."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TIERS = ("express", "mid", "full")
REQUIRED_FINDING_FIELDS = (
    "title",
    "business_impact",
    "technical_evidence",
    "recommended_action",
    "owner",
    "priority",
    "effort_estimate",
    "cost_or_loss_exposure",
    "confidence",
)

MIN_FINDINGS = {"express": 3, "mid": 7, "full": 12}
MIN_HIGH_VALUE_FINDINGS = {"express": 1, "mid": 3, "full": 5}


def qualify_report_economic_value(
    reports: Mapping[str, Mapping[str, Any]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    """Block delivery unless every tier contains decision-useful, economically framed findings."""
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for tier in TIERS:
        report = reports.get(tier)
        if not isinstance(report, Mapping):
            failures.append(f"{tier}:missing_report")
            continue

        findings = report.get("findings")
        if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
            failures.append(f"{tier}:missing_findings")
            continue
        if len(findings) < MIN_FINDINGS[tier]:
            failures.append(f"{tier}:insufficient_findings")

        high_value_count = 0
        for index, finding in enumerate(findings):
            if not isinstance(finding, Mapping):
                failures.append(f"{tier}:finding_{index}:invalid")
                continue
            for field in REQUIRED_FINDING_FIELDS:
                value = finding.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    failures.append(f"{tier}:finding_{index}:missing:{field}")
            exposure = finding.get("cost_or_loss_exposure")
            try:
                if float(exposure) >= 1000:
                    high_value_count += 1
            except (TypeError, ValueError):
                failures.append(f"{tier}:finding_{index}:invalid:cost_or_loss_exposure")

        if high_value_count < MIN_HIGH_VALUE_FINDINGS[tier]:
            failures.append(f"{tier}:insufficient_high_value_findings")

        for field in (
            "executive_decision_summary",
            "top_3_actions",
            "90_day_roadmap",
            "estimated_total_exposure",
            "estimated_remediation_budget",
            "evidence_coverage_percent",
            "reviewer",
            "snapshot_sha",
        ):
            value = report.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                failures.append(f"{tier}:missing:{field}")

        try:
            coverage = float(report.get("evidence_coverage_percent", 0))
            if coverage < 85:
                failures.append(f"{tier}:low_evidence_coverage")
        except (TypeError, ValueError):
            failures.append(f"{tier}:invalid:evidence_coverage_percent")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
