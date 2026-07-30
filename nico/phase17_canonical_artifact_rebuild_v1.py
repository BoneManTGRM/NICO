from __future__ import annotations

from typing import Any, Mapping

from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_localized_report_quality_repairs import repair_localized_rendered_report
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_report_quality_repairs import repair_canonical_truth
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts
from nico.v3_report_truth_remediation import finalize_report_v3, repair_report_truth_v3

# Install canonical truth and review-gate projection before the sole report
# compiler runs. The PDF guard remains bound for compatibility with existing
# tests and internal exports. V3 remediation then normalizes scanner truth,
# semantic finding identity, score aliases, roadmap references, and final
# artifact integrity without inventing evidence or changing a score by fiat.
install_pipeline_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Build one premium report from repaired authoritative evidence."""
    prepared = repair_report_truth_v3(repair_canonical_truth(package))
    rendered = rebuild_single_pass_premium_artifacts(prepared)
    repaired = repair_localized_rendered_report(rendered)
    return finalize_report_v3(repaired)


__all__ = [
    "VERSION",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "rebuild_client_artifacts",
]
