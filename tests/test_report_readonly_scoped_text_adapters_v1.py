from __future__ import annotations
import base64
import io
import pytest
from pypdf import PdfReader
from pypdf import PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import BooleanObject, NameObject
from reportlab.pdfgen import canvas
from nico import client_report_completion_v2 as completion

from pypdf._page import PageObject
from nico import comprehensive_full_report_finish_v1 as finish
from nico import comprehensive_ci_operational_truth_v71 as ci
from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
from nico.report_pdf_text import extract_pdf_page_texts, pdf_text_cache_scope
from tests.test_comprehensive_four_phase_report_v1 import _pdf

@pytest.mark.parametrize("adapter", ("finish", "ci", "cleanup"))
def test_readonly_adapters_reuse_exact_scoped_text_and_preserve_results(adapter, monkeypatch):
    body = _pdf()
    raw_pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(body)).pages]
    raw = "\n".join(raw_pages)
    assert "NICO Comprehensive" in raw and "Table of Contents" in raw
    calls = 0
    original = PageObject.extract_text
    def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)
    with pdf_text_cache_scope():
        extract_pdf_page_texts(body)
        monkeypatch.setattr(PageObject, "extract_text", counted)
        for _ in range(2):
            if adapter == "finish":
                assert finish._pdf_text(body) == raw
            elif adapter == "ci":
                assert ci._pdf_text(base64.b64encode(body).decode()) == ci._surface_text(raw)
            else:
                pages, joined = cleanup._pdf_text(body)
                assert pages == raw_pages and joined == raw
                pages[0] = "caller mutation must not alter cached text"
    assert calls == 0

def test_ci_adapter_keeps_encoding_signature_and_parser_rejection():
    for encoded, message in (("not valid base64!", "decodable PDF"),
                             (base64.b64encode(b"plain text").decode(), "valid final PDF")):
        with pdf_text_cache_scope(), pytest.raises(ValueError, match=message):
            ci._pdf_text(encoded)
    with pdf_text_cache_scope(), pytest.raises(PdfReadError):
        finish._pdf_text(b"%PDF invalid incomplete")

def _completion_fixture(*, literal: bool):
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 720, "AUTOMATED DRAFT")
    document.showPage()
    document.drawString(40, 720, "FINAL REPORT")
    document.showPage()
    document.save()
    reader = PdfReader(io.BytesIO(buffer.getvalue()))
    writer = PdfWriter()
    writer.append(reader)
    if literal:
        writer.pages[1][NameObject("/NICOSuppliedEvidence")] = BooleanObject(True)
    output = io.BytesIO()
    writer.write(output)
    canonical = {"canonical_findings": [], "report_language": "en"}
    register = {"summary": {
        "finding_population_reconciled": True,
        "semantic_duplicate_code_anchors_absent": True,
        "scanner_configuration_errors_promoted_to_code_findings": False,
        "unverified_tls_candidates_promoted_to_p1": False,
        "stable_alias_projection_idempotent": True,
        "decision_finding_count": 0,
    }, "code_findings": []}
    # Required unrelated sections are present; finality expectations below
    # independently distinguish supplied quotations from report-owned prose.
    prose = "AUTOMATED DRAFT\n" + "\n".join(completion._REVIEW_SECTION_TITLES)
    return canonical, register, prose, output.getvalue()

def _without_ci_boundary(monkeypatch):
    from nico import comprehensive_ci_boundary_compat_v74 as boundary
    monkeypatch.setattr(boundary, "ci_cd_boundary_markers", lambda *args, **kwargs: ())

@pytest.mark.parametrize("length", (1, 3))
def test_completion_rejects_short_and_long_cached_page_population(length, monkeypatch):
    canonical, register, prose, body = _completion_fixture(literal=True)
    _without_ci_boundary(monkeypatch)
    monkeypatch.setattr(completion, "extract_pdf_page_texts", lambda _: ("AUTOMATED DRAFT",) * length)
    with pdf_text_cache_scope(), pytest.raises(ValueError, match="page population"):
        _completion_validator()(canonical, register, prose, prose, body)

def test_completion_literal_metadata_controls_exclusion_with_warm_scoped_cache(monkeypatch):
    _without_ci_boundary(monkeypatch)
    for marked in (True, False, True):
        canonical, register, prose, body = _completion_fixture(literal=marked)
        with pdf_text_cache_scope():
            texts = extract_pdf_page_texts(body)
            assert len(texts) == 2 and "FINAL REPORT" in texts[1]
            if marked:
                result = _completion_validator()(canonical, register, prose, prose, body)
                assert result["finding_population_reconciled"] is True
            else:
                with pytest.raises(ValueError, match="finality language"):
                    _completion_validator()(canonical, register, prose, prose, body)

def _completion_validator():
    # Test the responsible validator separately from installed publication wrappers;
    # the full wrapper path has its own locale/process integration.
    import ast
    from pathlib import Path
    tree = ast.parse(Path(completion.__file__).read_text())
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                and item.name == "_validate_final_surfaces")
    namespace = dict(completion.__dict__)
    exec(compile(ast.Module(body=[node], type_ignores=[]), completion.__file__, "exec"), namespace)
    return namespace["_validate_final_surfaces"]
