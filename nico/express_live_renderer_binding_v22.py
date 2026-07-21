from __future__ import annotations

from typing import Any

from nico.express_pdf_renderer_truth_v21 import install_express_pdf_renderer_truth_v21
from nico.express_canonical_truth_finalization_v23 import install_express_canonical_truth_finalization_v23
from nico.express_scanner_disposition_truth_v1 import install_express_scanner_disposition_truth_v1
from nico.express_cross_format_contract_v24 import install_express_cross_format_contract_v24
from nico.express_glyph_score_leakage_patch import install_express_glyph_score_leakage_patch
from nico.express_section_status_truth_v26 import install_express_section_status_truth_v26
from nico.express_evidence_specific_scoring_v33 import install_express_evidence_specific_scoring_v33
from nico.express_source_score_refresh_v34 import install_express_source_score_refresh_v34
from nico.express_terminal_projection_truth_v1 import install_express_terminal_projection_truth_v1
from nico.express_client_report_postprocessor_v27 import install_express_client_report_postprocessor_v27
from nico.express_client_report_postprocessor_v31_compat import install_express_client_report_postprocessor_v31_compat

VERSION = "nico.express_live_renderer_binding.v25"


def install_express_live_renderer_binding_v22() -> dict[str, Any]:
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_premium_v14 as premium

    renderer = install_express_pdf_renderer_truth_v21()
    live_renderer = premium._premium_pdf
    previous = dossier._premium_pdf
    dossier._premium_pdf = live_renderer
    scanner_dispositions = install_express_scanner_disposition_truth_v1()
    canonical_truth = install_express_canonical_truth_finalization_v23()
    cross_format = install_express_cross_format_contract_v24()
    glyph_truth = install_express_glyph_score_leakage_patch()
    section_status_truth = install_express_section_status_truth_v26()
    evidence_specific_scoring = install_express_evidence_specific_scoring_v33()
    source_score_refresh = install_express_source_score_refresh_v34()
    terminal_projection = install_express_terminal_projection_truth_v1()
    postprocessor_compat = install_express_client_report_postprocessor_v31_compat()
    client_report_postprocessor = install_express_client_report_postprocessor_v27()

    return {
        "status": "installed" if previous is not live_renderer else "already_installed",
        "version": VERSION,
        "renderer_install": renderer,
        "scanner_disposition_install": scanner_dispositions,
        "canonical_truth_install": canonical_truth,
        "cross_format_contract_install": cross_format,
        "glyph_score_truth_install": glyph_truth,
        "section_status_truth_install": section_status_truth,
        "evidence_specific_scoring_install": evidence_specific_scoring,
        "source_score_refresh_install": source_score_refresh,
        "terminal_projection_install": terminal_projection,
        "client_report_postprocessor_compat_install": postprocessor_compat,
        "client_report_postprocessor_install": client_report_postprocessor,
        "premium_renderer_bound": bool(getattr(live_renderer, "_nico_express_pdf_renderer_truth_v21", False)),
        "dossier_renderer_bound": bool(getattr(dossier._premium_pdf, "_nico_express_pdf_renderer_truth_v21", False)),
        "scanner_dispositions_bound": scanner_dispositions.get("status") in {"installed", "already_installed"},
        "canonical_truth_bound": canonical_truth.get("status") in {"installed", "already_installed"},
        "cross_format_contract_bound": cross_format.get("status") in {"installed", "already_installed"},
        "glyph_score_truth_bound": glyph_truth.get("status") in {"installed", "already_installed"},
        "section_status_truth_bound": section_status_truth.get("status") in {"installed", "already_installed"},
        "evidence_specific_scoring_bound": evidence_specific_scoring.get("status") in {"installed", "already_installed"},
        "source_score_refresh_bound": source_score_refresh.get("status") in {"installed", "already_installed"},
        "terminal_projection_bound": terminal_projection.get("status") in {"installed", "already_installed"},
        "client_report_postprocessor_bound": client_report_postprocessor.get("status") in {"installed", "already_installed"},
        "client_report_postprocessor_compat_bound": postprocessor_compat.get("status") in {"installed", "already_installed"},
        "static_import_rebound": previous is not live_renderer,
        "human_review_required": True,
    }


__all__ = ["VERSION", "install_express_live_renderer_binding_v22"]
