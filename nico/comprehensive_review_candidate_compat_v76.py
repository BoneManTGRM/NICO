from __future__ import annotations

from typing import Any, Mapping

from nico import comprehensive_review_candidate_publication_v75 as publication
from nico import comprehensive_spanish_review_candidate_truth_v70 as legacy

VERSION = "nico.comprehensive-review-candidate-compat.v76"


def _has_exact_h2(markdown: str, heading: str) -> bool:
    return any(line.strip() == heading for line in str(markdown or "").splitlines())


def repair_review_candidate_publication(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    """Publish one exact bilingual candidate section without substring loops."""

    spanish = publication._is_spanish(canonical, spanish)
    output = publication._clean_evidence_summary(
        publication._normalize_stale_copy(str(markdown or ""))
    )
    for heading in publication._CANDIDATE_HEADINGS:
        while _has_exact_h2(output, heading):
            repaired = publication._remove_h2_section(output, heading)
            if repaired == output:  # defensive guard against malformed Markdown
                break
            output = repaired

    review_total, _material_total = publication._candidate_summary(canonical)
    if review_total <= 0:
        return output

    replacement = publication.review_candidate_truth_markdown(
        canonical,
        spanish=spanish,
    )
    lines = output.splitlines()
    insert_at = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() in publication._INSERT_BEFORE_HEADINGS
        ),
        len(lines),
    )
    lines[insert_at:insert_at] = [*replacement.rstrip().splitlines(), ""]
    return "\n".join(lines).strip() + "\n"


def repair_spanish_review_candidate_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
) -> str:
    """Preserve the historical Spanish API while using final publication truth."""

    if not publication._is_spanish(canonical, False):
        return str(markdown or "")
    return repair_review_candidate_publication(
        markdown,
        canonical,
        spanish=True,
    )


def repair_english_review_candidate_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
) -> str:
    """Preserve the historical English API while using final publication truth."""

    if publication._is_spanish(canonical, False):
        return str(markdown or "")
    return repair_review_candidate_publication(
        markdown,
        canonical,
        spanish=False,
    )


def spanish_review_candidate_truth_markdown(
    canonical: Mapping[str, Any],
) -> str:
    return publication.review_candidate_truth_markdown(canonical, spanish=True)


def english_review_candidate_truth_markdown(
    canonical: Mapping[str, Any],
) -> str:
    return publication.review_candidate_truth_markdown(canonical, spanish=False)


def install_comprehensive_review_candidate_compat_v76() -> dict[str, Any]:
    """Rebind current and historical APIs after every late report installer."""

    publication.repair_review_candidate_publication = (
        repair_review_candidate_publication
    )

    # Keep the general evidence summary separate from the dedicated candidate
    # register and preserve every public compatibility entry point.
    legacy._ES_SECTION_HEADINGS = {publication._ES_HEADING}
    legacy._EN_SECTION_HEADINGS = {publication._EN_HEADING}
    legacy.spanish_review_candidate_truth_markdown = (
        spanish_review_candidate_truth_markdown
    )
    legacy.english_review_candidate_truth_markdown = (
        english_review_candidate_truth_markdown
    )
    legacy.repair_spanish_review_candidate_markdown = (
        repair_spanish_review_candidate_markdown
    )
    legacy.repair_english_review_candidate_markdown = (
        repair_english_review_candidate_markdown
    )
    legacy.repair_review_candidate_markdown = (
        repair_review_candidate_publication
    )

    legacy_result = legacy.install_spanish_review_candidate_truth_v70()
    publication_result = (
        publication.install_comprehensive_review_candidate_publication_v75()
    )
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_installer": legacy_result,
        "publication_installer": publication_result,
        "legacy_spanish_alias_bound": (
            legacy.repair_spanish_review_candidate_markdown
            is repair_spanish_review_candidate_markdown
        ),
        "legacy_english_alias_bound": (
            legacy.repair_english_review_candidate_markdown
            is repair_english_review_candidate_markdown
        ),
        "exact_h2_matching_required": True,
        "evidence_summary_preserved": True,
        "dedicated_review_candidate_section": True,
        "english_and_spanish_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "english_review_candidate_truth_markdown",
    "install_comprehensive_review_candidate_compat_v76",
    "repair_english_review_candidate_markdown",
    "repair_review_candidate_publication",
    "repair_spanish_review_candidate_markdown",
    "spanish_review_candidate_truth_markdown",
]
