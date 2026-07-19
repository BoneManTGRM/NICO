from pathlib import Path


def test_batch_c_source_prohibits_ranked_dossier_boilerplate() -> None:
    source = Path("nico/express_decision_quality_v17.py").read_text(encoding="utf-8")
    assert "Business impact requires reviewer confirmation." not in source
    assert "Define the smallest reversible repair from the exact evidence." not in source


def test_batch_c_source_requires_page_and_geometry_contracts() -> None:
    source = Path("nico/express_decision_quality_v17.py").read_text(encoding="utf-8")
    assert '"pdf_page_break_before"' in source
    assert '"proportional_geometry"' in source
    assert '"SUPPLEMENTAL · MAPPED TO SCORED CONTROLS"' in source
    assert '"ci_categories_exactly_once": True' in source
