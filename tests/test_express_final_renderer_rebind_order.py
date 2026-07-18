from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "nico" / "__init__.py"


def test_report_recovery_rebinds_after_all_express_renderers() -> None:
    source = INIT.read_text(encoding="utf-8")
    premium = source.rindex("install_express_report_premium_v14()")
    dossier = source.rindex("install_express_dossier_export_v15()")
    recovery = source.rindex("install_express_report_generation_recovery()")
    checkpoint = source.rindex("install_express_final_gate_checkpoint_patch()")
    transport = source.rindex("install_express_backend_completion_transport()")

    assert premium < dossier < recovery < checkpoint < transport


def test_final_recovery_binding_is_not_only_the_early_async_metadata_install() -> None:
    source = INIT.read_text(encoding="utf-8")
    assert source.count("install_express_report_generation_recovery()") >= 1
    assert source.rindex("install_express_report_generation_recovery()") > source.rindex(
        "install_report_intelligence_final_pdf_binding()"
    )
    assert source.rindex("install_express_final_gate_checkpoint_patch()") > source.rindex(
        "install_report_quality_gate_compat()"
    )


def test_completion_transport_remains_last_express_finalization_binding() -> None:
    source = INIT.read_text(encoding="utf-8")
    transport = source.rindex("install_express_backend_completion_transport()")
    assert transport > source.rindex("install_express_report_generation_recovery()")
    assert transport > source.rindex("install_express_final_gate_checkpoint_patch()")
