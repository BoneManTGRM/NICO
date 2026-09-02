from __future__ import annotations

from pathlib import Path
from typing import Any

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

VERSION = "nico.comprehensive_pdf_embedded_fonts.v1"

_FONT_FILES = {
    "Helvetica": "Vera.ttf",
    "Helvetica-Bold": "VeraBd.ttf",
    "Helvetica-Oblique": "VeraIt.ttf",
    "Helvetica-BoldOblique": "VeraBI.ttf",
}


def _embedded_font_registered(name: str) -> bool:
    try:
        return isinstance(pdfmetrics.getFont(name), TTFont)
    except KeyError:
        return False


def install_comprehensive_pdf_embedded_fonts_v1() -> dict[str, Any]:
    """Replace Base-14 aliases with ReportLab's bundled, embedded TrueType fonts.

    NICO's report builders consistently address the Helvetica family by its historical
    ReportLab aliases. Base-14 fonts are not embedded, so viewers are allowed to replace
    them with local fonts and can produce materially different spacing. Registering the
    bundled Bitstream Vera faces under those aliases preserves existing renderer code
    while making every newly rendered glyph portable with the PDF.
    """

    already_installed = all(_embedded_font_registered(name) for name in _FONT_FILES)
    if not already_installed:
        font_directory = Path(reportlab.__file__).resolve().parent / "fonts"
        resolved = {
            name: font_directory / filename for name, filename in _FONT_FILES.items()
        }
        missing = [str(path) for path in resolved.values() if not path.is_file()]
        if missing:
            raise RuntimeError(
                "ReportLab bundled PDF fonts are unavailable: " + ", ".join(missing)
            )
        for name, path in resolved.items():
            # ReportLab does not expose an unregister operation and intentionally will
            # not replace a lazily cached Base-14 font with a dynamic TrueType font.
            # This installer runs during worker bootstrap, before requests are accepted;
            # remove only the exact historical aliases that this module owns.
            pdfmetrics._fonts.pop(name, None)
            pdfmetrics.registerFont(TTFont(name, str(path)))
        pdfmetrics.registerFontFamily(
            "Helvetica",
            normal="Helvetica",
            bold="Helvetica-Bold",
            italic="Helvetica-Oblique",
            boldItalic="Helvetica-BoldOblique",
        )

    embedded = {name: _embedded_font_registered(name) for name in _FONT_FILES}
    if not all(embedded.values()):
        raise RuntimeError("Portable comprehensive PDF font registration is incomplete")

    return {
        "artifact_schema": VERSION,
        "status": "already_installed" if already_installed else "installed",
        "bound": True,
        "regular_embedded": embedded["Helvetica"],
        "bold_embedded": embedded["Helvetica-Bold"],
        "italic_embedded": embedded["Helvetica-Oblique"],
        "bold_italic_embedded": embedded["Helvetica-BoldOblique"],
        "client_viewer_font_substitution_required": False,
        "canonical_truth_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_pdf_embedded_fonts_v1"]
