from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

VERSION = "cross_tier_artifact_inspection_v1"
TIERS = ("express", "mid", "full")
FORMATS = ("pdf", "html", "markdown")
_REQUIRED_PAGE_CHECKS = (
    "no_blank_pages",
    "no_near_blank_pages",
    "no_clipped_content",
    "no_duplicate_prose",
    "no_broken_tables",
    "no_raw_markup",
    "visual_consistency",
)


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def inspect_cross_tier_artifacts(
    artifacts: Mapping[str, Any],
    *,
    expected_snapshot_sha: str,
    expected_locales: Sequence[str] = ("en", "es"),
) -> dict[str, Any]:
    """Validate representative rendered artifacts and equivalent truth across tiers/formats."""
    records = _mapping(artifacts)
    issues: list[str] = []
    tier_results: dict[str, Any] = {}

    for tier in TIERS:
        tier_record = _mapping(records.get(tier))
        tier_issues: list[str] = []
        if not tier_record:
            tier_issues.append("missing_tier_record")

        locales = _mapping(tier_record.get("locales"))
        for locale in expected_locales:
            locale_record = _mapping(locales.get(locale))
            if not locale_record:
                tier_issues.append(f"missing_locale:{locale}")
                continue
            if str(locale_record.get("snapshot_sha") or "") != str(expected_snapshot_sha or ""):
                tier_issues.append(f"snapshot_sha_mismatch:{locale}")

            formats = _mapping(locale_record.get("formats"))
            truth_fingerprint = str(locale_record.get("truth_fingerprint") or "")
            if not truth_fingerprint:
                tier_issues.append(f"missing_truth_fingerprint:{locale}")

            observed_fingerprints: set[str] = set()
            for report_format in FORMATS:
                artifact = _mapping(formats.get(report_format))
                if not artifact:
                    tier_issues.append(f"missing_format:{locale}:{report_format}")
                    continue
                if not artifact.get("artifact_id"):
                    tier_issues.append(f"missing_artifact_id:{locale}:{report_format}")
                fingerprint = str(artifact.get("truth_fingerprint") or "")
                if fingerprint:
                    observed_fingerprints.add(fingerprint)
                else:
                    tier_issues.append(f"missing_format_truth_fingerprint:{locale}:{report_format}")

                if report_format == "pdf":
                    page_count = int(artifact.get("page_count") or 0)
                    inspected_pages = int(artifact.get("inspected_pages") or 0)
                    if page_count < 1 or inspected_pages != page_count:
                        tier_issues.append(f"pdf_page_inspection_incomplete:{locale}")
                    checks = _mapping(artifact.get("page_checks"))
                    for check in _REQUIRED_PAGE_CHECKS:
                        if checks.get(check) is not True:
                            tier_issues.append(f"pdf_check_failed:{locale}:{check}")

            if truth_fingerprint and (observed_fingerprints != {truth_fingerprint}):
                tier_issues.append(f"cross_format_truth_mismatch:{locale}")

        tier_results[tier] = {
            "status": "passed" if not tier_issues else "blocked",
            "issues": tier_issues,
            "client_delivery_allowed": not tier_issues,
        }
        issues.extend(f"{tier}:{issue}" for issue in tier_issues)

    allowed = not issues
    return {
        "version": VERSION,
        "status": "passed" if allowed else "blocked",
        "expected_snapshot_sha": str(expected_snapshot_sha or ""),
        "expected_locales": list(expected_locales),
        "tiers": tier_results,
        "issues": issues,
        "client_delivery_allowed": allowed,
    }


__all__ = ["FORMATS", "TIERS", "VERSION", "inspect_cross_tier_artifacts"]
