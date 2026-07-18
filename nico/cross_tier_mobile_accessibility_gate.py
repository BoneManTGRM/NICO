from __future__ import annotations

from typing import Any

TIERS = ("express", "mid", "full")
REQUIRED_VIEWPORTS = (320, 375, 390, 414)
REQUIRED_CHECKS = (
    "no_horizontal_overflow",
    "no_clipped_text",
    "no_overlapping_controls",
    "primary_actions_visible",
    "keyboard_navigation",
    "visible_focus",
    "semantic_headings",
    "form_labels",
    "screen_reader_summary",
    "contrast_pass",
    "reduced_motion",
    "download_flow_pass",
)


def evaluate_cross_tier_mobile_accessibility(payload: dict[str, Any]) -> dict[str, Any]:
    """Fail closed unless every tier passes required mobile and accessibility evidence."""
    issues: list[str] = []
    results = payload.get("tiers") or {}

    for tier in TIERS:
        record = results.get(tier)
        if not isinstance(record, dict):
            issues.append(f"missing_tier:{tier}")
            continue

        widths = tuple(sorted({int(value) for value in (record.get("viewports") or []) if int(value) > 0}))
        for required in REQUIRED_VIEWPORTS:
            if required not in widths:
                issues.append(f"missing_viewport:{tier}:{required}")

        checks = record.get("checks") or {}
        for name in REQUIRED_CHECKS:
            if checks.get(name) is not True:
                issues.append(f"failed_check:{tier}:{name}")

        if record.get("tier") != tier:
            issues.append(f"tier_identity_mismatch:{tier}")
        if record.get("locale_parity") is not True:
            issues.append(f"locale_parity_failed:{tier}")
        if record.get("download_content_disposition") is not True:
            issues.append(f"unsafe_download_disposition:{tier}")
        if record.get("download_content_length") is not True:
            issues.append(f"missing_download_length:{tier}")
        if record.get("touch_target_min_px", 0) < 44:
            issues.append(f"touch_target_too_small:{tier}")
        if record.get("client_delivery_blocked") is True:
            issues.append(f"prior_delivery_block:{tier}")

    return {
        "approved": not issues,
        "client_delivery_allowed": not issues,
        "issues": sorted(set(issues)),
        "tiers_checked": list(TIERS),
        "viewports_required": list(REQUIRED_VIEWPORTS),
        "checks_required": list(REQUIRED_CHECKS),
    }


__all__ = ["evaluate_cross_tier_mobile_accessibility"]
