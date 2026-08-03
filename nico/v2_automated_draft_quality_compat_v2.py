from __future__ import annotations

import re
from typing import Any, Mapping

from nico import v2_automated_draft_quality_compat_v1 as base

VERSION = "nico.v2.automated-draft-quality-compat.v2"
_NORMALIZATION_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "complete only as a draft",
        "complete as an automated draft pending human approval",
    ),
    (" · DRAFT", " · AUTOMATED DRAFT"),
    (" - DRAFT", " - AUTOMATED DRAFT"),
    (" — DRAFT", " — AUTOMATED DRAFT"),
)


def _contains_legacy_status_draft(value: str) -> bool:
    """Reject obsolete status language without rejecting explanatory draft prose.

    `AUTOMATED DRAFT` is the authoritative unapproved lifecycle state. Earlier
    validators rejected every occurrence of the token `DRAFT`, which also blocked
    valid report copy such as `evidence-bound draft`. Only the superseded status
    forms remain publication blockers here.
    """

    normalized = base._semantic(value)
    normalized = normalized.replace("automated draft", "")
    normalized = normalized.replace("borrador automatizado", "")
    return bool(
        re.search(
            r"(?:^|\n|\r)\s*draft\s*(?:$|\n|\r)"
            r"|\bdraft\s*[·—-]\s*human review required\b"
            r"|\bdraft only\b"
            r"|\bcomplete only as a draft\b"
            r"|\bnico comprehensive\s*[·—-].*\s[·—-]\s*draft(?:\s+page\s+\d+)?\b"
            r"|\bborrador solamente\b",
            normalized,
            re.IGNORECASE,
        )
    )


def _extend_replacements(
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    output = list(values)
    for replacement in _NORMALIZATION_REPLACEMENTS:
        if replacement not in output:
            output.append(replacement)
    return tuple(output)


def _bind_narrow_legacy_draft_detection() -> None:
    base._contains_legacy_bare_draft = _contains_legacy_status_draft
    base._PDF_REPLACEMENTS = _extend_replacements(base._PDF_REPLACEMENTS)
    base._TEXT_REPLACEMENTS = _extend_replacements(base._TEXT_REPLACEMENTS)


def install_automated_draft_quality_compat() -> dict[str, Any]:
    _bind_narrow_legacy_draft_detection()
    result = dict(base.install_automated_draft_quality_compat())
    result.update(
        {
            "version": VERSION,
            "legacy_status_draft_detection_narrowed": True,
            "extended_legacy_status_phrases_normalized": True,
            "explanatory_draft_prose_allowed": True,
            "automated_draft_is_valid_unapproved_state": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return result


def repair_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    result = base.repair_rendered_report(package)
    contract = dict(result.get("premium_report_renderer") or {})
    contract["automated_draft_quality_compat_version"] = VERSION
    contract["legacy_status_draft_detection_narrowed"] = True
    contract["extended_legacy_status_phrases_normalized"] = True
    result["premium_report_renderer"] = contract
    return result


def repair_localized_rendered_report(package: Mapping[str, Any]) -> dict[str, Any]:
    install_automated_draft_quality_compat()
    result = base.repair_localized_rendered_report(package)
    contract = dict(result.get("premium_report_renderer") or {})
    contract["automated_draft_quality_compat_version"] = VERSION
    contract["legacy_status_draft_detection_narrowed"] = True
    contract["extended_legacy_status_phrases_normalized"] = True
    result["premium_report_renderer"] = contract
    return result


__all__ = [
    "VERSION",
    "install_automated_draft_quality_compat",
    "repair_localized_rendered_report",
    "repair_rendered_report",
]
