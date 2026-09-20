"""Synthetic reference and legacy-byte compatibility regressions for R5/R6."""
import io
import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from nico.comprehensive_operator_presentation_v1 import _render_source


def source_pdf(extra_pages=0, spanish=False):
    out=io.BytesIO(); c=canvas.Canvas(out)
    c.drawString(40, 740, "Aprobación humana: Pendiente de una acción explícita del revisor." if spanish else
                 "Human approval: Pending explicit reviewer action.")
    c.showPage()
    for n in range(extra_pages):
        c.drawString(40, 740, f"Synthetic evidence {n}"); c.showPage()
    c.drawString(40, 740, "Registro de aprobación del operador" if spanish else "Operator Report Approval Record")
    c.showPage(); c.save()
    return out.getvalue()


@pytest.mark.parametrize("spanish", [False, True])
@pytest.mark.parametrize("extra_pages", [0, 3])
def test_reference_resolves_from_assembled_report_and_legacy_stays_frozen(spanish, extra_pages):
    source=source_pdf(extra_pages, spanish)
    legacy, _ = _render_source(source)
    fixed, _ = _render_source(source, resolve_approval_references=True)
    text=PdfReader(io.BytesIO(fixed)).pages[0].extract_text()
    assert (f"pág. {extra_pages + 2} del informe" if spanish else f"report p. {extra_pages + 2}") in text
    assert "see certificate" not in text and "ver certificado" not in text
    assert _render_source(source)[0] == legacy
    assert ("ver certificado" if spanish else "see certificate") in PdfReader(io.BytesIO(legacy)).pages[0].extract_text()
    assert _render_source(source, resolve_approval_references=True)[0] == fixed


def test_missing_approval_reference_is_rejected():
    out=io.BytesIO(); c=canvas.Canvas(out); c.drawString(40,740,"Synthetic report without a record"); c.save()
    with pytest.raises(ValueError, match="reference_target_missing"):
        _render_source(out.getvalue(), resolve_approval_references=True)
