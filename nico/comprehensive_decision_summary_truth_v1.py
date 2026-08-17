from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-decision-summary-truth.v1"
_MARKER = "__nico_comprehensive_decision_summary_truth_v1__"
_LIMITED_STATUSES = {
    "blocked",
    "failed",
    "unavailable",
    "timed_out",
    "review_required",
    "limited",
    "framework_only",
    "not_assessed",
}


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _limited_count(assessment: Mapping[str, Any], stages: list[Mapping[str, Any]]) -> int:
    retained = assessment.get("limited_review_section_count")
    if isinstance(retained, int) and not isinstance(retained, bool) and retained >= 0:
        return retained
    return sum(
        _text(stage.get("status"), 80).casefold() in _LIMITED_STATUSES
        or bool(stage.get("unavailable"))
        for stage in stages
    )


def install_comprehensive_decision_summary_truth_v1() -> dict[str, Any]:
    from nico import comprehensive_report_package as package

    current = package._decision_summary
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _decision_summary(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
    ) -> str:
        language = _text(
            assessment.get("report_language")
            or assessment.get("locale")
            or identity.get("report_language")
            or identity.get("locale"),
            40,
        ).casefold()
        spanish = language.startswith("es")
        maturity = (
            assessment.get("maturity_signal")
            if isinstance(assessment.get("maturity_signal"), Mapping)
            else {}
        )
        level = _text(maturity.get("level") or ("Pendiente" if spanish else "Pending"), 80)
        score = maturity.get("presented_score", maturity.get("score"))
        score_text = (
            f"{int(score)}/100"
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else ("sin puntuación" if spanish else "not scored")
        )
        limited = _limited_count(assessment, stages)
        terminal = [
            _text(stage.get("title"), 140)
            for stage in stages
            if _text(stage.get("status"), 80).casefold()
            in {"blocked", "failed", "unavailable", "timed_out"}
        ]
        if terminal:
            terminal_count = len(terminal)
            terminal_subject = (
                "etapa automatizada"
                if terminal_count == 1
                else "etapas automatizadas"
            )
            terminal_verb = "tiene" if terminal_count == 1 else "tienen"
            execution = (
                f"{terminal_count} {terminal_subject} {terminal_verb} una limitación terminal de ejecución: {', '.join(terminal[:4])}."
                if spanish
                else f"{len(terminal)} automated stage(s) have a terminal execution limitation: {', '.join(terminal[:4])}."
            )
        else:
            execution = (
                "Ninguna etapa automatizada representada en este paquete conserva un fallo terminal de ejecución."
                if spanish
                else "No automated stage represented in this package has a retained terminal execution failure."
            )
        if spanish:
            limited_sections = (
                "sección de revisión del cliente"
                if limited == 1
                else "secciones de revisión del cliente"
            )
            limited_verb = "declara" if limited == 1 else "declaran"
            return (
                "NICO generó un borrador automatizado de Evaluación Técnica Integral para "
                f"{_text(identity.get('repository'))} en el commit inmutable {_text(identity.get('commit_sha'))}. "
                f"La señal de madurez basada en evidencia es {level} ({score_text}). "
                f"{limited} {limited_sections} {limited_verb} evidencia no disponible, limitada, "
                f"de marco o dependiente de las partes interesadas. {execution} El paquete está sujeto a revisión: "
                "la evidencia y las recomendaciones automatizadas no constituyen aprobación humana ni autorización "
                "de entrega al cliente."
            )
        return (
            f"NICO generated an automated Comprehensive Technical Assessment draft for {_text(identity.get('repository'))} "
            f"at immutable commit {_text(identity.get('commit_sha'))}. The evidence-bound maturity signal is "
            f"{level} ({score_text}). {limited} client-review section(s) disclose unavailable, limited, framework-only, "
            f"or stakeholder-dependent evidence. {execution} The package is review-gated: automated evidence and "
            "recommendations are not human approval or client-delivery authorization."
        )

    setattr(_decision_summary, _MARKER, True)
    setattr(_decision_summary, "_nico_previous", current)
    package._decision_summary = _decision_summary
    return {
        "status": "installed",
        "version": VERSION,
        "limited_count_uses_canonical_assessment": True,
        "execution_completion_separate_from_evidence_limitations": True,
        "automated_draft_language_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_decision_summary_truth_v1"]
