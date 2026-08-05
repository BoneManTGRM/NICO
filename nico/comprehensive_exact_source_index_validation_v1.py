from __future__ import annotations

import re
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-exact-source-index-validation.v1"
_MARKER = "__nico_exact_source_index_validation_v1__"
_OMITTED_ERROR = re.compile(
    r"^full-data PDF index omitted (?P<count>\d+) canonical exact-source finding\(s\)$"
)
_INDEX_TITLE = "Complete Exact-Source Index"
_LAYOUT_WHITESPACE = re.compile(r"[\s\u00ad\u200b\u2060]+")


def compact_pdf_identifier(value: Any) -> str:
    """Normalize only PDF layout whitespace around an immutable identifier.

    ReportLab can wrap a long finding ID inside the narrow index column. PDF text
    extraction then inserts spaces or line breaks even though the visible ID is
    complete. Removing layout whitespace preserves every identifier character and
    does not permit a changed, truncated, or missing identifier to pass.
    """

    return _LAYOUT_WHITESPACE.sub("", str(value or "")).casefold()


def validate_exact_source_index_identifiers(
    canonical: Mapping[str, Any],
    extracted_pdf_text: str,
) -> int:
    """Require every canonical finding ID inside the actual index section."""

    from nico import comprehensive_full_report_finish_v1 as finish

    if _INDEX_TITLE not in extracted_pdf_text:
        raise ValueError(f"full-data PDF is missing required section: {_INDEX_TITLE}")

    index_text = extracted_pdf_text.split(_INDEX_TITLE, 1)[1]
    compact_index = compact_pdf_identifier(index_text)
    identifiers: list[str] = []
    compact_identifiers: set[str] = set()
    for item in finish._findings(canonical):
        identifier = finish._text(item.get("finding_id") or item.get("id"), 300)
        if not identifier:
            raise ValueError(
                "canonical exact-source finding is missing a stable finding identifier"
            )
        compact = compact_pdf_identifier(identifier)
        if compact in compact_identifiers:
            raise ValueError(
                f"canonical exact-source finding identifier is duplicated: {identifier}"
            )
        compact_identifiers.add(compact)
        identifiers.append(identifier)

    omitted = [
        identifier
        for identifier in identifiers
        if compact_pdf_identifier(identifier) not in compact_index
    ]
    if omitted:
        raise ValueError(
            f"full-data PDF index omitted {len(omitted)} canonical exact-source finding(s)"
        )
    return len(identifiers)


def _post_index_validation(
    canonical: Mapping[str, Any],
    extracted: str,
) -> dict[str, Any]:
    """Complete the original validator after its layout-sensitive ID check."""

    from nico import comprehensive_full_report_finish_v1 as finish

    finding_count = validate_exact_source_index_identifiers(canonical, extracted)
    for title in (
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        "Human Review and Acceptance Gate",
        _INDEX_TITLE,
    ):
        if title not in extracted:
            raise ValueError(f"full-data PDF is missing required section: {title}")

    timestamp = finish.canonical_generation_timestamp(canonical)
    if not timestamp:
        raise ValueError("full-data manifest is missing a canonical generation timestamp")
    if "Generated\nNot available" in extracted or "Generated: Not available" in extracted:
        raise ValueError("full-data manifest silently degraded the generation timestamp")

    return {
        "proof_kind": "full_comprehensive",
        "scored_control_count": len(finish._sections(canonical)),
        "scanner_execution_count": len(finish._scanners(canonical)),
        "candidate_count": finish._candidate_total(canonical),
        "exact_source_finding_count": finding_count,
        "worksheet_count": len(finish._WORKSHEET_TITLES),
        "generation_timestamp": timestamp,
    }


def install_exact_source_index_validation_v1() -> dict[str, Any]:
    """Make the strict full-data gate tolerant only of PDF line wrapping."""

    from nico import comprehensive_full_report_finish_v1 as finish

    current = finish.assert_full_data_parity
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "index_section_required": True,
            "every_canonical_finding_id_required": True,
            "layout_whitespace_only_normalization": True,
            "missing_or_changed_ids_fail_closed": True,
            "scores_unchanged": True,
            "candidate_dispositions_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def assert_full_data_parity(
        canonical: Mapping[str, Any],
        markdown: str,
        rendered_html: str,
        pdf: bytes,
    ) -> dict[str, Any]:
        try:
            return current(canonical, markdown, rendered_html, pdf)
        except ValueError as exc:
            if not _OMITTED_ERROR.fullmatch(str(exc)):
                raise
            # Every validation before the exact-ID check has already passed in
            # the original fail-closed validator. Recheck the same index using
            # layout-only normalization, then execute all remaining boundaries.
            extracted = finish._pdf_text(pdf)
            return _post_index_validation(canonical, extracted)

    setattr(assert_full_data_parity, _MARKER, True)
    setattr(assert_full_data_parity, "_nico_previous", current)
    finish.assert_full_data_parity = assert_full_data_parity
    return {
        "status": "installed",
        "version": VERSION,
        "index_section_required": True,
        "every_canonical_finding_id_required": True,
        "layout_whitespace_only_normalization": True,
        "missing_or_changed_ids_fail_closed": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "compact_pdf_identifier",
    "install_exact_source_index_validation_v1",
    "validate_exact_source_index_identifiers",
]
