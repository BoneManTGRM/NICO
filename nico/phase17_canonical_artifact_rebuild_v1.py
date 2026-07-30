from __future__ import annotations

from typing import Any, Mapping

from nico.scanner_evidence_contract_v2 import install_scanner_evidence_contract_v2
from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_localized_report_quality_repairs import repair_localized_rendered_report
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_report_quality_repairs import _is_spanish, repair_canonical_truth
from nico.v2_report_quality_runtime_compat import repair_rendered_report
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts

# Bind scanner truth before report compilation so every report consumes one
# fail-closed exact-run evidence contract. Report projection and review gates
# remain downstream of that authoritative scanner boundary.
_SCANNER_EVIDENCE_CONTRACT = install_scanner_evidence_contract_v2()
install_pipeline_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Build one premium report from repaired authoritative evidence."""
    prepared = repair_canonical_truth(package)
    rendered = rebuild_single_pass_premium_artifacts(prepared)
    canonical = rendered.get("json") if isinstance(rendered.get("json"), Mapping) else {}
    if _is_spanish(canonical):
        return repair_localized_rendered_report(rendered)
    return repair_rendered_report(rendered)


__all__ = [
    "VERSION",
    "_SCANNER_EVIDENCE_CONTRACT",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "rebuild_client_artifacts",
]
