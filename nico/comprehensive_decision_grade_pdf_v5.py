from __future__ import annotations

from typing import Any

from nico.comprehensive_premium_pdf_v6 import _build_pdf as _premium_build_pdf
from nico.comprehensive_premium_pdf_v6 import _pdf_with_final_count as _premium_pdf_with_final_count

VERSION = "nico.comprehensive_decision_grade_pdf.v6"


def _build_pdf(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
    final_page_count: int | None = None,
) -> bytes:
    """Build only evidence-bearing report pages.

    Earlier releases padded every report to a fixed minimum page count by
    repeating stage evidence. Phase 6 removes that artificial page contract:
    report length now follows unique decision-relevant content only.
    """

    return _premium_build_pdf(
        identity,
        assessment,
        stages,
        roadmap,
        staffing,
        limitations,
        generated_at,
        final_page_count,
    )


def _pdf_with_final_count(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> tuple[bytes, int]:
    """Return the natural report and its deterministic final page count."""

    return _premium_pdf_with_final_count(
        identity,
        assessment,
        stages,
        roadmap,
        staffing,
        limitations,
        generated_at,
    )


__all__ = ["VERSION", "_build_pdf", "_pdf_with_final_count"]
