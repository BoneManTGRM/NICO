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
