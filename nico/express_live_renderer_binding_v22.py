from __future__ import annotations

from typing import Any

from nico.express_pdf_renderer_truth_v21 import install_express_pdf_renderer_truth_v21
from nico.express_canonical_truth_finalization_v23 import install_express_canonical_truth_finalization_v23
from nico.express_cross_format_contract_v24 import install_express_cross_format_contract_v24
from nico.express_glyph_score_leakage_patch import install_express_glyph_score_leakage_patch

VERSION = "nico.express_live_renderer_binding.v22"


def install_express_live_renderer_binding_v22() -> dict[str, Any]:
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_premium_v14 as premium

    renderer = install_express_pdf_renderer_truth_v21()
    live_renderer = premium._premium_pdf
    previous = dossier._premium_pdf
    dossier._premium_pdf = live_renderer
    canonical_truth = install_express_canonical_truth_finalization_v23()
    cross_format = install_express_cross_format_contract_v24()
    glyph_truth = install_express_glyph_score_leakage_patch()

    return {
        "status": "installed" if previous is not live_renderer else "already_installed",
        "version": VERSION,
        "renderer_install": renderer,
        "canonical_truth_install": canonical_truth,
        "cross_format_contract_install": cross_format,
        "glyph_score_truth_install": glyph_truth,
        "premium_renderer_bound": bool(getattr(live_renderer, "_nico_express_pdf_renderer_truth_v21", False)),
        "dossier_renderer_bound": bool(getattr(dossier._premium_pdf, "_nico_express_pdf_renderer_truth_v21", False)),
        "canonical_truth_bound": canonical_truth.get("status") in {"installed", "already_installed"},
        "cross_format_contract_bound": cross_format.get("status") in {"installed", "already_installed"},
        "glyph_score_truth_bound": glyph_truth.get("status") in {"installed", "already_installed"},
        "static_import_rebound": previous is not live_renderer,
        "human_review_required": True,
    }


__all__ = ["VERSION", "install_express_live_renderer_binding_v22"]
