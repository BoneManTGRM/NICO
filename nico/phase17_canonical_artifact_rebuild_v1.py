from __future__ import annotations

from typing import Any, Mapping

from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_dark_branded_cover import apply_dark_branded_cover
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts

# Install canonical truth and review-gate projection before the sole report
# compiler runs. The PDF guard remains bound for compatibility with existing
# tests and internal exports, while the final exact client PDF is validated
# after the mature premium layout and branded cover are assembled.
install_pipeline_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render canonical truth through the mature report and restore its branded cover.

    The single-pass compiler builds the complete report body from current scanner,
    score, finding, identity, and lifecycle truth. The cover compositor then replaces
    the temporary canonical-score sheet with the established dark NICO cover without
    regenerating or mutating any report-body page.
    """
    rendered = rebuild_single_pass_premium_artifacts(package)
    return apply_dark_branded_cover(rendered)


__all__ = [
    "VERSION",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "rebuild_client_artifacts",
]
