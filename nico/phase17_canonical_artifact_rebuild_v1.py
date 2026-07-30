from __future__ import annotations

from typing import Any, Mapping

from nico.production_report_truth_gate_v1 import reconcile_production_report_truth
from nico.scanner_command_repair_v1 import install_scanner_command_repair
from nico.scanner_evidence_contract_v2 import install_scanner_evidence_contract_v2
from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_localized_report_quality_repairs import repair_localized_rendered_report
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_report_quality_repairs import _is_spanish, repair_canonical_truth
from nico.v2_report_quality_runtime_compat import repair_rendered_report
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts

# Repair concrete scanner commands before wrapping execution evidence. This keeps
# Bandit configuration deterministic and preserves one fail-closed scanner chain.
_SCANNER_COMMAND_REPAIR = install_scanner_command_repair()
_SCANNER_EVIDENCE_CONTRACT = install_scanner_evidence_contract_v2()
install_pipeline_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Build one premium report from reconciled authoritative production evidence."""
    reconciled = reconcile_production_report_truth(package)
    prepared = repair_canonical_truth(reconciled)
    prepared = reconcile_production_report_truth(prepared)
    rendered = rebuild_single_pass_premium_artifacts(prepared)
    canonical = rendered.get("json") if isinstance(rendered.get("json"), Mapping) else {}
    repaired = (
        repair_localized_rendered_report(rendered)
        if _is_spanish(canonical)
        else repair_rendered_report(rendered)
    )
    return reconcile_production_report_truth(repaired)


__all__ = [
    "VERSION",
    "_SCANNER_COMMAND_REPAIR",
    "_SCANNER_EVIDENCE_CONTRACT",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "rebuild_client_artifacts",
]
