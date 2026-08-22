from __future__ import annotations

import re
from functools import wraps
from typing import Any

VERSION = "nico.spanish-cross-format-score-parity.v1"
_MARKER = "__nico_spanish_cross_format_score_parity_v1__"
_SCORE_SUMMARY_MARKER = "__nico_spanish_score_summary_contract_v1__"


def _install_phase2_review_work() -> dict[str, Any]:
    from nico.comprehensive_review_work_runtime_v1 import (
        install_comprehensive_review_work_runtime_v1,
    )

    return install_comprehensive_review_work_runtime_v1()


def _install_spanish_presentation_score_summary_contract() -> dict[str, Any]:
    """Bind the current canonical score-truth sentence to a strict Spanish contract.

    The final Comprehensive presentation may append an operational-metrics sentence
    to the original score summary. The canonical Spanish renderer intentionally fails
    closed for unknown English prose, so this wrapper recognizes only that exact
    extended contract, preserves every dynamic score/count, and delegates every other
    value to the existing validator.
    """

    from nico import comprehensive_spanish_canonical_report_v87 as presentation

    current = presentation._structured_presentation_es
    if getattr(current, _SCORE_SUMMARY_MARKER, False):
        return {
            "status": "already_installed",
            "bound": True,
            "contract": "extended_operational_metrics_score_summary",
        }

    extended_score_summary = re.compile(
        r"Technical maturity remains based on exact-commit technical controls\. "
        r"Evidence-Adjusted readiness is (?P<adjusted>\d+(?:\.\d+)?)/100 versus "
        r"technical maturity (?P<technical>\d+(?:\.\d+)?)/100\. NICO retains "
        r"(?P<review>\d+) review-required candidates and (?P<material>\d+) "
        r"confirmed material findings as explicit review context\. Candidate volume, "
        r"clustering and reviewer workload do not change numeric security or "
        r"readiness scores\. Candidate volume and reviewer workload are operational "
        r"review metrics and have no numeric technical-maturity or Evidence-Adjusted "
        r"score effect\."
    )

    @wraps(current)
    def localized_score_summary(value: str) -> str | None:
        stripped = str(value or "").strip()
        match = extended_score_summary.fullmatch(stripped)
        if match is None:
            return current(value)
        return (
            "La madurez técnica sigue basándose en controles técnicos del commit exacto. "
            f"La preparación ajustada por evidencia es {match.group('adjusted')}/100 "
            f"frente a una madurez técnica de {match.group('technical')}/100. NICO "
            f"conserva {match.group('review')} candidatos que requieren revisión y "
            f"{match.group('material')} hallazgos materiales confirmados como contexto "
            "explícito de revisión. El volumen de candidatos, la agrupación y la carga "
            "de trabajo de revisión no modifican las puntuaciones numéricas de seguridad "
            "ni de preparación. El volumen de candidatos y la carga de trabajo de "
            "revisión son métricas operativas de revisión y no tienen efecto numérico "
            "sobre la madurez técnica ni sobre la puntuación ajustada por evidencia."
        )

    setattr(localized_score_summary, _SCORE_SUMMARY_MARKER, True)
    setattr(localized_score_summary, "_nico_previous", current)
    presentation._structured_presentation_es = localized_score_summary
    return {
        "status": "installed",
        "bound": presentation._structured_presentation_es is localized_score_summary,
        "contract": "extended_operational_metrics_score_summary",
        "scores_preserved": True,
        "candidate_counts_preserved": True,
        "unknown_english_still_fails_closed": True,
    }


def install_spanish_cross_format_score_parity() -> dict[str, Any]:
    from nico import comprehensive_cross_format_finality_v49 as cross

    spanish_presentation_score_summary = (
        _install_spanish_presentation_score_summary_contract()
    )
    phase2_review_work = _install_phase2_review_work()
    current = cross._package_score_truth
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "spanish_score_labels_supported": True,
            "spanish_presentation_score_summary": spanish_presentation_score_summary,
            "phase2_review_work": phase2_review_work,
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
        "spanish_presentation_score_summary": spanish_presentation_score_summary,
        "phase2_review_work": phase2_review_work,
    }


__all__ = [
    "VERSION",
    "_install_spanish_presentation_score_summary_contract",
    "install_spanish_cross_format_score_parity",
]
