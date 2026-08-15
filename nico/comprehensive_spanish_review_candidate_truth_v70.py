from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive-review-candidate-truth.v72"
_MARKER = "_nico_comprehensive_review_candidate_truth_v72"
_ES_SECTION_HEADINGS = {
    "## Resumen del paquete de evidencia",
    "## Registro de candidatos que requieren revisión",
}
_EN_SECTION_HEADINGS = {
    "## Evidence Package Summary",
    "## Review-Required Candidate Register",
}
_ES_REVIEW_GATE_HEADINGS = {
    "## Puerta de revisión humana y aceptación",
    "## Puerta de revisión y aceptación humana",
    "## Puerta de revisión y entrega",
    "## Estado de entrega",
}
_EN_REVIEW_GATE_HEADINGS = {
    "## Human Review and Acceptance Gate",
    "## Delivery Status",
}
_ES_SCORE_EFFECT = (
    "Efecto en puntuación: solo aseguramiento mientras la disposición humana "
    "siga pendiente; el triage técnico de NICO está completo."
)
_EN_SCORE_EFFECT = (
    "Score effect: assurance-only while authorized human disposition remains "
    "pending; NICO automated technical triage is complete."
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or identity.get("report_language")
        or assessment.get("report_language")
    ).casefold()
    return language.startswith("es")


def _candidate_summary(canonical: Mapping[str, Any]) -> tuple[int, int]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    summary = canonical.get("review_candidate_summary")
    if not isinstance(summary, Mapping):
        summary = assessment.get("review_candidate_summary")
    if not isinstance(summary, Mapping):
        summary = {}
    return (
        _integer(summary.get("review_required_total")),
        _integer(summary.get("verified_material_total")),
    )


def spanish_review_candidate_truth_markdown(canonical: Mapping[str, Any]) -> str:
    review_total, material_total = _candidate_summary(canonical)
    return "\n".join(
        [
            "## Registro de candidatos que requieren revisión",
            "",
            (
                "La finalización técnica, el triage automatizado y la disposición humana "
                "se mantienen como estados distintos. La evidencia completa permanece "
                "en los artefactos JSON y CSV de la ejecución exacta."
            ),
            "",
            f"- Candidatos que requieren revisión: {review_total}",
            f"- Hallazgos materiales confirmados: {material_total}",
            f"- {_ES_SCORE_EFFECT}",
        ]
    ).strip() + "\n"


def english_review_candidate_truth_markdown(canonical: Mapping[str, Any]) -> str:
    review_total, material_total = _candidate_summary(canonical)
    return "\n".join(
        [
            "## Review-Required Candidate Register",
            "",
            (
                "Technical completion, automated triage, and authorized human disposition "
                "remain separate states. Complete evidence remains in the exact-run JSON "
                "and CSV artifacts."
            ),
            "",
            f"- Review-required candidates: {review_total}",
            f"- Confirmed material findings: {material_total}",
            f"- {_EN_SCORE_EFFECT}",
        ]
    ).strip() + "\n"


def _replace_or_insert_h2_section(
    markdown: str,
    replacement: str,
    *,
    section_headings: set[str],
    insert_before_headings: set[str],
) -> str:
    lines = str(markdown or "").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() in section_headings),
        None,
    )
    if start is not None:
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        replacement_lines = replacement.rstrip().splitlines()
        lines[start:end] = [*replacement_lines, ""]
        return "\n".join(lines).strip() + "\n"

    insert_at = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() in insert_before_headings
        ),
        len(lines),
    )
    addition = [*replacement.rstrip().splitlines(), ""]
    lines[insert_at:insert_at] = addition
    return "\n".join(lines).strip() + "\n"


def repair_spanish_review_candidate_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
) -> str:
    """Synchronize Spanish client text with authoritative candidate disposition truth."""

    if not _is_spanish(canonical):
        return str(markdown or "")
    review_total, _ = _candidate_summary(canonical)
    if review_total <= 0:
        return str(markdown or "")
    return _replace_or_insert_h2_section(
        str(markdown or ""),
        spanish_review_candidate_truth_markdown(canonical),
        section_headings=_ES_SECTION_HEADINGS,
        insert_before_headings=_ES_REVIEW_GATE_HEADINGS,
    )


def repair_english_review_candidate_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
) -> str:
    """Synchronize English client text with authoritative candidate disposition truth."""

    if _is_spanish(canonical):
        return str(markdown or "")
    review_total, _ = _candidate_summary(canonical)
    if review_total <= 0:
        return str(markdown or "")
    return _replace_or_insert_h2_section(
        str(markdown or ""),
        english_review_candidate_truth_markdown(canonical),
        section_headings=_EN_SECTION_HEADINGS,
        insert_before_headings=_EN_REVIEW_GATE_HEADINGS,
    )


def repair_review_candidate_markdown(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    review_total, _ = _candidate_summary(canonical)
    if review_total <= 0:
        return str(markdown or "")
    if spanish or _is_spanish(canonical):
        return _replace_or_insert_h2_section(
            str(markdown or ""),
            spanish_review_candidate_truth_markdown(canonical),
            section_headings=_ES_SECTION_HEADINGS,
            insert_before_headings=_ES_REVIEW_GATE_HEADINGS,
        )
    return _replace_or_insert_h2_section(
        str(markdown or ""),
        english_review_candidate_truth_markdown(canonical),
        section_headings=_EN_SECTION_HEADINGS,
        insert_before_headings=_EN_REVIEW_GATE_HEADINGS,
    )


def install_spanish_review_candidate_truth_v70() -> dict[str, Any]:
    """Bind bilingual candidate-truth repair to the real V2 Markdown producer."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_ready_projection_v1 as projection

    current: Callable[..., str] = completion.compact_client_markdown
    if getattr(current, _MARKER, False):
        projection.compact_client_markdown = current
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "spanish_review_candidate_truth_synchronized": True,
            "english_review_candidate_truth_synchronized": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def compact_client_markdown(
        existing: str,
        canonical: Mapping[str, Any],
        register: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> str:
        rendered = current(
            existing,
            deepcopy(dict(canonical)),
            deepcopy(dict(register)),
            spanish=spanish,
        )
        return repair_review_candidate_markdown(
            rendered,
            canonical,
            spanish=spanish,
        )

    setattr(compact_client_markdown, _MARKER, True)
    setattr(compact_client_markdown, "_nico_previous", current)
    completion.compact_client_markdown = compact_client_markdown
    projection.compact_client_markdown = compact_client_markdown
    return {
        "status": "installed",
        "version": VERSION,
        "bound": completion.compact_client_markdown is compact_client_markdown,
        "spanish_review_candidate_heading": "Registro de candidatos que requieren revisión",
        "english_review_candidate_heading": "Review-Required Candidate Register",
        "canonical_candidate_counts_rendered": True,
        "current_score_effect_truth_rendered": True,
        "stale_review_wording_replaced_before_html_render": True,
        "english_and_spanish_reports_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "english_review_candidate_truth_markdown",
    "install_spanish_review_candidate_truth_v70",
    "repair_english_review_candidate_markdown",
    "repair_review_candidate_markdown",
    "repair_spanish_review_candidate_markdown",
    "spanish_review_candidate_truth_markdown",
]
