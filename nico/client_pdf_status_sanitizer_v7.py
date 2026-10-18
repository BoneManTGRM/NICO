from __future__ import annotations

import unicodedata
import re
from typing import Any

VERSION = "nico.client-pdf-status-sanitizer.v7.3"
_MARKER = "__nico_client_pdf_status_sanitizer_v7__"
_PRESERVED_REVIEW_MARKERS = (
    "nico | comprehensive client review | automated draft",
    "section 1 of 8 | page 1 of 2",
    "section 2 of 8 | page 1 of 2",
    "section 3 of 8 | page 1 of 2",
    "section 4 of 8 | page 1 of 2",
    "section 5 of 8 | page 1 of 2",
    "section 6 of 8 | page 1 of 2",
    "section 7 of 8 | page 1 of 2",
    "section 8 of 8 | page 1 of 2",
    "human decision pending | delivery blocked",
    "automated draft | human review required",
    "client artifact manifest",
    "human review and exact-artifact approval record",
    "nico | exact-artifact review package | automated draft",
    "review package ready | human approval pending | client delivery blocked",
)


def _normalized(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def _flowing_review_page(text: str) -> bool:
    """Recognize worksheet structure, without exempting text sanitization.

    This is presentation classification, not provenance or approval authority.
    A PDF dictionary bit alone cannot identify a worksheet.
    """
    normalized = _normalized(text)
    lines = {_normalized(line) for line in text.splitlines()}
    english = {'nico | automated draft', 'human decision pending | client delivery blocked'} <= lines
    spanish = {'nico | borrador automatizado', 'decision humana pendiente | entrega bloqueada'} <= lines
    if not (english or spanish):
        return False
    counter = re.search(r'\b(?:review page|pagina de revision) (\d+) (?:of|de) (\d+)\b', normalized)
    if not counter or not 1 <= int(counter[1]) <= int(counter[2]):
        return False
    section_ids = ('functional_qa', 'platform_parity', 'historical_trends_and_change_failure',
                   'requirements_traceability', 'stakeholder_and_business_alignment',
                   'risk_reduction_and_executive_briefing', 'six_month_roadmap', 'staffing_sequencing_and_cost')
    for section_id in section_ids:
        if re.search(r'\bid: ' + section_id + r' \| (?:section|seccion) [1-8] (?:of|de) 8\b', normalized):
            return True
        if re.search(r'\[' + section_id + r'\] — (?:continued|continuacion)\b', normalized):
            return True
    return False


def install_client_pdf_status_sanitizer_v7() -> dict[str, Any]:
    from nico import client_pdf_status_sanitizer_v1 as sanitizer
    from nico.comprehensive_scanner_stage_wording_v1 import (
        install_comprehensive_scanner_stage_wording_v1,
    )
    from nico.v2_dark_branded_cover_readiness_v4 import (
        install_dark_branded_cover_readiness_v4,
    )

    cover_readiness = install_dark_branded_cover_readiness_v4()
    scanner_stage_wording = install_comprehensive_scanner_stage_wording_v1()
    current = sanitizer._drop_internal_page
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "client_review_pages_preserved": True,
            "artifact_manifest_pages_preserved": True,
            "cover_readiness": cover_readiness,
            "scanner_stage_wording": scanner_stage_wording,
        }

    def _drop_internal_page(text: str) -> bool:
        normalized = _normalized(text)
        if _flowing_review_page(text):
            return False
        if any(marker in normalized for marker in _PRESERVED_REVIEW_MARKERS):
            return False
        return current(text)

    setattr(_drop_internal_page, _MARKER, True)
    setattr(_drop_internal_page, "_nico_previous", current)
    sanitizer._drop_internal_page = _drop_internal_page
    return {
        "status": "installed",
        "version": VERSION,
        "client_review_pages_preserved": True,
        "artifact_manifest_pages_preserved": True,
        "raw_internal_pages_still_removed": True,
        "automated_draft_boundary_preserved": True,
        "cover_readiness": cover_readiness,
        "scanner_stage_wording": scanner_stage_wording,
        "execution_and_disposition_separated": True,
        "review_package_ready": True,
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_client_pdf_status_sanitizer_v7"]
