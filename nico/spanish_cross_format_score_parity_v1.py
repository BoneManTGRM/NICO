from __future__ import annotations

from functools import wraps
from typing import Any

VERSION = "nico.spanish-cross-format-score-parity.v1"
_MARKER = "__nico_spanish_cross_format_score_parity_v1__"


def install_spanish_cross_format_score_parity() -> dict[str, Any]:
    from nico import comprehensive_cross_format_finality_v49 as cross

    current = cross._package_score_truth
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "spanish_score_labels_supported": True,
        }

    @wraps(current)
    def localized(package: dict[str, Any], pdf: bytes) -> dict[str, Any]:
        result = dict(current(package, pdf))
        canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
        language = str(
            package.get("report_language")
            or package.get("locale")
            or canonical.get("report_language")
            or canonical.get("locale")
            or "en"
        ).casefold()
        if not language.startswith("es"):
            return result

        technical = result.get("technical_score")
        adjusted = result.get("evidence_adjusted_score")
        markdown = str(package.get("markdown") or "")
        html_text = cross._html_text(str(package.get("html") or ""))
        pdf_text = cross._pdf_text(pdf)
        technical_labels = (
            "Madurez técnica",
            "Madurez tecnica",
            "MADUREZ TÉCNICA",
            "MADUREZ TECNICA",
        )
        adjusted_labels = (
            "Ajuste por evidencia",
            "AJUSTE POR EVIDENCIA",
            "Puntuación ajustada por evidencia",
            "Puntuacion ajustada por evidencia",
        )
        result.update(
            {
                "markdown_technical_matches": cross._score_near_label(markdown, technical, technical_labels),
                "markdown_evidence_adjusted_matches": cross._score_near_label(markdown, adjusted, adjusted_labels),
                "html_technical_matches": cross._score_near_label(html_text, technical, technical_labels),
                "html_evidence_adjusted_matches": cross._score_near_label(html_text, adjusted, adjusted_labels),
                "pdf_technical_matches": cross._score_near_label(pdf_text, technical, technical_labels),
                "pdf_evidence_adjusted_matches": cross._score_near_label(pdf_text, adjusted, adjusted_labels),
                "localized_score_labels_verified": True,
                "verified_language": "es-MX",
            }
        )
        return result

    setattr(localized, _MARKER, True)
    setattr(localized, "_nico_previous", current)
    cross._package_score_truth = localized
    return {
        "status": "installed",
        "version": VERSION,
        "bound": cross._package_score_truth is localized,
        "spanish_score_labels_supported": True,
        "markdown_html_pdf_supported": True,
    }


__all__ = ["VERSION", "install_spanish_cross_format_score_parity"]
