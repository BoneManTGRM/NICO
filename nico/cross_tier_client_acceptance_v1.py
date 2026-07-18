"""Fail-closed client acceptance gate for Express, Mid, and Full."""

from __future__ import annotations

from typing import Any, Mapping

TIERS = ("express", "mid", "full")
REQUIRED_FIELDS = (
    "assessment_completed",
    "report_opened",
    "pdf_downloaded",
    "html_downloaded",
    "markdown_downloaded",
    "mobile_verified",
    "english_verified",
    "spanish_verified",
    "score_matches_report",
    "findings_traceable",
    "client_signoff",
)


def qualify_client_acceptance(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    prior_release_allowed: bool = True,
) -> dict[str, Any]:
    """Return a release decision that blocks on incomplete client acceptance."""

    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for tier in TIERS:
        record = evidence.get(tier)
        if not isinstance(record, Mapping):
            failures.append(f"{tier}:missing_evidence")
            continue

        for field in REQUIRED_FIELDS:
            if field not in record:
                failures.append(f"{tier}:missing:{field}")
            elif record[field] is not True:
                failures.append(f"{tier}:{field}:failed")

        if not str(record.get("assessment_id", "")).strip():
            failures.append(f"{tier}:missing_assessment_id")
        if not str(record.get("snapshot_sha", "")).strip():
            failures.append(f"{tier}:missing_snapshot_sha")
        if not str(record.get("reviewer", "")).strip():
            failures.append(f"{tier}:missing_reviewer")
        if int(record.get("critical_defects", 1)) != 0:
            failures.append(f"{tier}:critical_defects_open")
        if int(record.get("high_defects", 1)) != 0:
            failures.append(f"{tier}:high_defects_open")

    unique = sorted(set(failures))
    return {
        "status": "accepted" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
