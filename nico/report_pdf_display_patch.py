from __future__ import annotations

from typing import Any, Callable


def apply_pdf_display_patch() -> None:
    """Keep the PDF executive summary complete while preserving bullet limits.

    The professional PDF renderer intentionally truncates many table cells and
    evidence bullets. That is fine for dense lists, but the executive summary is a
    client-facing narrative and should never end with a visible "[truncated]"
    marker. This patch only changes large narrative calls; short table cells and
    bullet limits remain bounded.
    """
    from nico import assessment_quality

    original: Callable[[Any, int], str] | None = getattr(assessment_quality, "_nico_original_clean_text", None)
    if original is None:
        original = assessment_quality._clean_text
        assessment_quality._nico_original_clean_text = original

    def clean_text_without_summary_truncation(value: Any, limit: int = 1200) -> str:
        text = assessment_quality._friendly_note(value)
        # The executive summary is rendered with a high limit. Allow it to flow
        # across pages instead of appending "... [truncated]".
        if limit >= 900:
            return text
        return original(value, limit)

    assessment_quality._clean_text = clean_text_without_summary_truncation
