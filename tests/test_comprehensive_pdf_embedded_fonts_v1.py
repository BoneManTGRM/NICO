from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas


def _font_dictionaries(pdf_bytes: bytes) -> list[dict]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    fonts: list[dict] = []
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        for reference in (resources.get("/Font") or {}).values():
            fonts.append(reference.get_object())
    return fonts


def test_comprehensive_renderer_embeds_portable_fonts_for_existing_aliases() -> None:
    from nico.comprehensive_pdf_embedded_fonts_v1 import (
        install_comprehensive_pdf_embedded_fonts_v1,
    )

    state = install_comprehensive_pdf_embedded_fonts_v1()

    output = io.BytesIO()
    document = canvas.Canvas(output, invariant=1)
    document.setFont("Helvetica-Bold", 19)
    document.drawString(42, 740, "Client Evidence Summary")
    document.setFont("Helvetica", 8.2)
    document.drawString(42, 716, "Revisión técnica — aprobación humana pendiente")
    document.save()

    fonts = _font_dictionaries(output.getvalue())
    assert fonts
    assert all(font.get("/Subtype") == "/TrueType" for font in fonts)
    assert all(
        (font.get("/FontDescriptor") or {}).get_object().get("/FontFile2")
        for font in fonts
    )
    assert PdfReader(io.BytesIO(output.getvalue())).pages[0].extract_text() == (
        "Client Evidence Summary\n"
        "Revisión técnica — aprobación humana pendiente\n"
    )
    assert state["status"] in {"installed", "already_installed"}
    assert state["regular_embedded"] is True
    assert state["bold_embedded"] is True
    assert state["italic_embedded"] is True
    assert state["bold_italic_embedded"] is True
    assert state["client_viewer_font_substitution_required"] is False
    assert pdfmetrics.getFont("Helvetica").__class__.__name__ == "TTFont"
    assert pdfmetrics.getFont("Helvetica-Bold").__class__.__name__ == "TTFont"


def test_final_report_worker_installs_embedded_fonts_before_app_import() -> None:
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(encoding="utf-8")

    installer_import = "from nico.comprehensive_pdf_embedded_fonts_v1 import ("
    installer_call = "install_comprehensive_pdf_embedded_fonts_v1()"
    app_import = "from nico.api.terminal_authority_bootstrap import app"
    assert installer_import in source
    assert source.index(installer_import) < source.index(app_import)
    assert source.index(installer_call) < source.index(app_import)
    assert '"embedded_pdf_fonts_bound": True' in source
