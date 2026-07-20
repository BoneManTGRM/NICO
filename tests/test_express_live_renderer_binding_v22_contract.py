from pathlib import Path


def test_package_bootstrap_rebinds_dossier_static_renderer_reference() -> None:
    source = Path("nico/__init__.py").read_text(encoding="utf-8")
    assert "install_express_pdf_renderer_truth_v21()" in source
    assert "install_express_live_renderer_binding_v22()" in source
    assert source.index("install_express_pdf_renderer_truth_v21()") < source.index("install_express_live_renderer_binding_v22()")


def test_live_binding_module_repoints_dossier_renderer() -> None:
    source = Path("nico/express_live_renderer_binding_v22.py").read_text(encoding="utf-8")
    assert "dossier._premium_pdf = live_renderer" in source
    assert '"dossier_renderer_bound"' in source
