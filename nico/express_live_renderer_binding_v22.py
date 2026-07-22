from __future__ import annotations

from typing import Any

from nico.express_pdf_renderer_truth_v21 import install_express_pdf_renderer_truth_v21
from nico.express_pdf_score_assurance_v1 import install_express_pdf_score_assurance_v1
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
from nico.express_final_export_truth_v35 import install_express_final_export_truth_v35
from nico.express_score_assurance_export_v1 import install_express_score_assurance_export_v1
from nico.express_pdf_section_index_binding_v1 import install_express_pdf_section_index_binding_v1
from nico.express_truth_calibration_v36 import install_express_truth_calibration_v36
from nico.express_assurance_display_v37 import install_express_assurance_display_v37
from nico.express_truth_calibration_v38_compat import install_express_truth_calibration_v38_compat
from nico.express_pdf_score_assurance_layout_v39 import install_express_pdf_score_assurance_layout_v39
from nico.express_truth_calibration_v40_patch import install_express_truth_calibration_v40_patch
from nico.express_report_final_polish_v41 import install_express_report_final_polish_v41

VERSION = "nico.express_live_renderer_binding.v41"


def install_express_live_renderer_binding_v22() -> dict[str, Any]:
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_premium_v14 as premium

    renderer = install_express_pdf_renderer_truth_v21()
    score_assurance_renderer = install_express_pdf_score_assurance_v1()
    live_renderer = premium._premium_pdf
    if score_assurance_renderer.get("status") in {"installed", "already_installed"}:
        setattr(live_renderer, "_nico_express_pdf_renderer_truth_v21", True)
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
    final_export_truth = install_express_final_export_truth_v35()
    score_assurance_export = install_express_score_assurance_export_v1()
    pdf_section_index = install_express_pdf_section_index_binding_v1()
    truth_calibration = install_express_truth_calibration_v36()
    assurance_display = install_express_assurance_display_v37()
    truth_calibration_compat = install_express_truth_calibration_v38_compat()
    pdf_score_assurance_layout = install_express_pdf_score_assurance_layout_v39()
    truth_calibration_patch = install_express_truth_calibration_v40_patch()
    final_report_polish = install_express_report_final_polish_v41()

    renderer_bound = bool(getattr(live_renderer, "_nico_express_pdf_renderer_truth_v21", False))
    score_assurance_bound = bool(getattr(live_renderer, "_nico_express_pdf_score_assurance_v1", False))

    return {
        "status": "installed" if previous is not live_renderer else "already_installed",
        "version": VERSION,
        "renderer_install": renderer,
        "score_assurance_renderer_install": score_assurance_renderer,
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
        "final_export_truth_install": final_export_truth,
        "score_assurance_export_install": score_assurance_export,
        "pdf_section_index_install": pdf_section_index,
        "truth_calibration_install": truth_calibration,
        "assurance_display_install": assurance_display,
        "truth_calibration_compat_install": truth_calibration_compat,
        "pdf_score_assurance_layout_install": pdf_score_assurance_layout,
        "truth_calibration_patch_install": truth_calibration_patch,
        "final_report_polish_install": final_report_polish,
        "premium_renderer_bound": renderer_bound,
        "score_assurance_renderer_bound": score_assurance_bound,
        "dossier_renderer_bound": renderer_bound and dossier._premium_pdf is live_renderer,
        "dossier_score_assurance_renderer_bound": score_assurance_bound and dossier._premium_pdf is live_renderer,
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
        "final_export_truth_bound": final_export_truth.get("status") in {"installed", "already_installed"},
        "score_assurance_export_bound": score_assurance_export.get("status") in {"installed", "already_installed"},
        "pdf_section_index_bound": pdf_section_index.get("status") in {"installed", "already_installed"},
        "truth_calibration_bound": truth_calibration.get("status") in {"installed", "already_installed"},
        "assurance_display_bound": assurance_display.get("status") in {"installed", "already_installed"},
        "truth_calibration_compat_bound": truth_calibration_compat.get("status") in {"installed", "already_installed"},
        "pdf_score_assurance_layout_bound": pdf_score_assurance_layout.get("status") in {"installed", "already_installed"},
        "truth_calibration_patch_bound": truth_calibration_patch.get("status") in {"installed", "already_installed"},
        "final_report_polish_bound": final_report_polish.get("status") in {"installed", "already_installed"},
        "score_band_separated_from_assurance": True,
        "static_import_rebound": previous is not live_renderer,
        "human_review_required": True,
    }


__all__ = ["VERSION", "install_express_live_renderer_binding_v22"]
