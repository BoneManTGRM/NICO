"""Small isolated cases for the observed production pagination failures."""
import base64
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader
from reportlab.platypus import SimpleDocTemplate

from nico.comprehensive_report_package import _pdf, _source_pdf_tables, _source_presentation_stages, _source_tables


@pytest.mark.parametrize("reverse", [False, True])
def test_identical_coverage_is_presented_once_without_changing_retained_stages(reverse):
    coverage = {"inventory_complete": True, "observed_source_files": 10, "analyzed_source_files": 2}
    stages = [
        {"stage_id": "architecture", "source_observation": {"observation_sha256": "a" * 64}, "profile_coverage": coverage,
         "structured_tables": [{"title": "Components", "columns": ["Source"], "rows": [["app.py"]]}]},
        {"stage_id": "repository", "profile_coverage": deepcopy(coverage)},
        {"stage_id": "different_scope", "profile_coverage": {**coverage, "analyzed_source_files": 3}},
    ]
    if reverse:
        stages.reverse()
    original = deepcopy(stages)
    tables = [table for stage in _source_presentation_stages(stages) for table in _source_tables(stage)]
    assert sum(t["title"] == "Bounded profile coverage" for t in tables) == 2
    assert any(t["title"] == "Components" for t in tables)
    assert stages == original


@pytest.mark.parametrize("spanish", [False, True])
def test_observation_hash_stays_with_its_source_table(spanish):
    stage = {"source_observation": {"observation_sha256": "a" * 64},
             "structured_tables": [{"title": "Components", "columns": ["Source"],
                                    "rows": [[f"source_{i}.py"] for i in range(24)]}]}
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=(612, 544)).build(_source_pdf_tables(stage, spanish=spanish, width=468))
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(output.getvalue())).pages]
    hash_page = next(text for text in pages if "a" * 64 in text.replace("\n", ""))
    assert "source_" in hash_page


@pytest.mark.parametrize("spanish", [False, True])
def test_table_coverage_note_stays_with_the_last_data_row(spanish):
    stage = {"structured_tables": [{"title": "Components", "columns": ["Source"],
                                    "rows": [[f"source_{i}.py"] for i in range(24)]}]}
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=(612, 544)).build(_source_pdf_tables(stage, spanish=spanish, width=468))
    note = "Se muestran" if spanish else "Showing"
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(output.getvalue())).pages]
    assert all("source_23.py" in text for text in pages if note in text)


def test_long_stage_evidence_continuations_identify_their_section():
    stage = {"stage_id": "six_month_roadmap", "title": "Six-Month Roadmap", "status": "framework_only",
             "summary": "Stakeholder validation remains pending.", "findings": [], "unavailable": [],
             "evidence": [f"WORK-{i}: proposed work; " + "bounded source observation " * 20 for i in range(18)]}
    encoded, error, _ = _pdf({"repository": "example/project", "commit_sha": "a" * 40, "run_id": "fixture"},
                             {}, [stage], "2026-09-15T00:00:00Z")
    assert error is None
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(base64.b64decode(encoded))).pages]
    work_pages = [text for text in pages if "WORK-" in text]
    assert len(work_pages) > 1
    assert all("Six-Month Roadmap" in text for text in work_pages)
    assert all(f"WORK-{i}:" in "\n".join(pages) for i in range(18))


@pytest.mark.parametrize("spanish", [False, True])
def test_compatibility_contents_retains_every_entry_and_final_page_reference(monkeypatch, spanish):
    from reportlab.pdfgen import canvas
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico import comprehensive_spanish_presentation_parity_v1 as localization

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(612, 792), invariant=1)
    for title in ["Cover", *[f"SECTION-{i:02}" for i in range(33)]]:
        pdf.drawString(48, 744, title)
        pdf.showPage()
    pdf.save()
    monkeypatch.setattr(navigation, "_outline_title", lambda text: text.splitlines()[0])
    monkeypatch.setattr(localization, "_spanish_outline_title", lambda nav, text: text.splitlines()[0])
    monkeypatch.setattr(localization, "_localized_title", lambda title: title)
    rendered = (localization._renumber_spanish(navigation, output.getvalue()) if spanish
                else navigation._renumber_and_outline(output.getvalue()))
    reader = PdfReader(io.BytesIO(rendered))
    assert len(reader.pages) == 36  # cover, two contents pages, 33 sections
    contents = "\n".join(page.extract_text() for page in reader.pages[1:3])
    for i in range(33):
        assert f"SECTION-{i:02}\n{i + 4}" in contents
        destination = next(item for item in reader.outline if item.title == f"SECTION-{i:02}")
        assert reader.get_destination_page_number(destination) == i + 3
    # Leave the first contents page's four-phase table region clear.
    positions = []
    reader.pages[1].extract_text(visitor_text=lambda text, cm, tm, font, size:
                                 positions.append(tm[5]) if text.startswith("SECTION-") else None)
    assert min(positions) >= 190


@pytest.mark.parametrize("spanish", [False, True])
def test_phase_bookmarks_do_not_target_contents_continuations(spanish):
    from reportlab.pdfgen import canvas
    from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=(612, 792), invariant=1)
    contents = "Índice" if spanish else "Table of Contents"
    gate = "Puerta de revisión humana y aceptación" if spanish else "Human Review and Acceptance Gate"
    for heading, text in [("Cover", ""), (contents, ""), (contents, gate), ("Body", ""), (gate, "")]:
        pdf.drawString(48, 744, heading)
        pdf.drawString(48, 700, text)
        pdf.showPage()
    pdf.save()
    reader = PdfReader(io.BytesIO(apply_four_phase_pdf(output.getvalue(), {}, spanish=spanish)))
    name = "Revisión humana por excepción" if spanish else "Human Review by Exception"
    phases = next(items for items in reader.outline if isinstance(items, list))
    target = next(item for item in phases if item.title == name)
    assert reader.get_destination_page_number(target) == 4
