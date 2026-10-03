from __future__ import annotations

import base64
import io

import pytest
from pypdf._page import PageObject
from reportlab.pdfgen.canvas import Canvas

from nico import report_pdf_text as cache
from nico import comprehensive_client_truth_canonical_v2 as canonical
from nico import comprehensive_truth_diagnostics_v1 as diagnostics
from nico import comprehensive_terminal_report_language_authority_v83 as language
from nico import comprehensive_rendered_ci_boundary_truth_v78 as ci
from nico import comprehensive_compact_design_marker_v1 as compact
from nico import comprehensive_report_coverage_synchronization_v63 as coverage


def _pdf(label: str) -> bytes:
    output = io.BytesIO()
    canvas = Canvas(output, invariant=True)
    canvas.drawString(40, 700, label)
    canvas.showPage()
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def _readers(pdf: bytes) -> tuple[object, ...]:
    package = {"pdf_base64": base64.b64encode(pdf).decode("ascii")}
    return (
        canonical._pdf_text(package),
        diagnostics._pdf_text(package),
        language._pdf_text(package),
        ci._extract_pdf_text(package),
        compact._combined_client_text(package),
        coverage._pdf_coverage_alias_present(pdf),
    )


@pytest.mark.parametrize("label", ["run-one pending human approval", "ejecución-uno pendiente de revisión"])
def test_installed_validation_readers_reuse_exact_bytes_only_within_attempt(monkeypatch, label):
    pdf = _pdf(label)
    expected = _readers(pdf)
    changed = _pdf(label + " changed")
    changed_expected = _readers(changed)
    calls = []
    original = PageObject.extract_text

    def extract(page, *args, **kwargs):
        calls.append(page)
        return original(page, *args, **kwargs)

    monkeypatch.setattr(PageObject, "extract_text", extract)
    with cache.pdf_text_cache_scope():
        assert _readers(pdf) == expected
        assert _readers(bytes(bytearray(pdf))) == expected
        assert len(calls) == 2, "same two-page PDF was reparsed by independent validators"
        assert _readers(changed) == changed_expected
        assert len(calls) == 4, "changed PDF bytes must be independently parsed"
    with cache.pdf_text_cache_scope():
        assert _readers(pdf) == expected
    assert len(calls) == 6, "fresh request must not inherit the prior attempt cache"


def test_cached_valid_pdf_does_not_authorize_or_mask_invalid_artifact():
    valid = _pdf("run-one pending human approval")
    with cache.pdf_text_cache_scope():
        _readers(valid)
        invalid = {"pdf_base64": base64.b64encode(b"%PDF-not-a-valid-document").decode("ascii")}
        with pytest.raises(ValueError, match="no valid PDF"):
            canonical._pdf_text(invalid)
        with pytest.raises(ValueError, match="CI/CD language validation"):
            language._pdf_text(invalid)
        assert len(cache._ATTEMPT_CACHE.get().entries) == 1
