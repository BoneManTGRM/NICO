from __future__ import annotations

from typing import Any, Mapping

from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts

# Install canonical truth and review-gate projection before the sole report
# compiler runs. The PDF guard remains bound for compatibility with existing
# tests and internal exports, while the single-pass compiler validates the
# exact finished client PDF after all pages have been assembled.
install_pipeline_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Build the old premium report once from the new authoritative evidence."""
    return rebuild_single_pass_premium_artifacts(package)


__all__ = [
    "VERSION",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "rebuild_client_artifacts",
]
