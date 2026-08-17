from __future__ import annotations

import html
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.comprehensive-review-candidate-publication.v75"
_PRODUCER_MARKER = "_nico_review_candidate_producer_v75"
_MERGE_MARKER = "_nico_review_candidate_merge_v75"
_FINAL_MARKER = "_nico_review_candidate_final_v75"

_EN_HEADING = "## Review-Required Candidate Register"
_ES_HEADING = "## Registro de candidatos que requieren revisión"
_EN_HEADING_TEXT = "Review-Required Candidate Register"
_ES_HEADING_TEXT = "Registro de candidatos que requieren revisión"
_EN_SCORE_EFFECT = (
    "Score effect: assurance-only while authorized human disposition remains "
    "pending; NICO automated technical triage is complete."
)
_ES_SCORE_EFFECT = (
    "Efecto en puntuación: solo aseguramiento mientras la disposición humana "
    "siga pendiente; el triaje técnico de NICO está completo."
)

_EVIDENCE_SUMMARY_HEADINGS = {
    "## Evidence Package Summary",
    "## Resumen del paquete de evidencia",
}
_CANDIDATE_HEADINGS = {
    _EN_HEADING,
    _ES_HEADING,
}
_INSERT_BEFORE_HEADINGS = {
    "## Human Review and Acceptance Gate",
    "## Delivery Status",
    "## Puerta de revisión humana y aceptación",
    "## Puerta de revisión y aceptación humana",
    "## Puerta de revisión y entrega",
    "## Estado de entrega",
}
_STALE_LINE_PREFIXES = (
    "- review-required candidates:",
    "- confirmed material findings:",
    "- score effect:",
    "- candidatos pendientes de revisión:",
    "- candidatos que requieren revisión:",
    "- hallazgos materiales confirmados:",
    "- efecto en puntuación:",
    "- efecto en la puntuación:",
)
_STALE_SCORE_EFFECT_MARKERS = (
    "score effect: assurance-only until triaged",
    "efecto en la puntuación: solo aseguramiento hasta su clasificación",
    "efecto en puntuación: solo aseguramiento hasta completar la revisión",
    "efecto en la puntuación: solo aseguramiento hasta completar la revisión",
)


def _text(value: Any) -> str:
    return " ".join(str("" if value is None else value).split()).strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value if value is not None else 0))
    except (TypeError, ValueError):
        return 0


def _chain_has_marker(current: Callable[..., Any], marker: str) -> bool:
    seen: set[int] = set()
    candidate: Any = current
    while callable(candidate) and id(candidate) not in seen:
        seen.add(id(candidate))
        if getattr(candidate, marker, False):
            return True
        candidate = getattr(candidate, "_nico_previous", None)
    return False


def _is_spanish(canonical: Mapping[str, Any], spanish: bool = False) -> bool:
    if spanish:
        return True
    identity = _mapping(canonical.get("identity"))
    assessment = _mapping(canonical.get("assessment"))
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or identity.get("report_language")
        or assessment.get("report_language")
    ).casefold()
    return language.startswith("es")


def _candidate_summary(canonical: Mapping[str, Any]) -> tuple[int, int]:
    assessment = _mapping(canonical.get("assessment"))
    summary = canonical.get("review_candidate_summary")
    if not isinstance(summary, Mapping):
        summary = assessment.get("review_candidate_summary")
    summary = _mapping(summary)

    review = summary.get("review_required_total")
    material = summary.get("verified_material_total")
    if review is None or material is None:
        register = canonical.get("canonical_scanner_finding_register")
        if not isinstance(register, Mapping):
            register = assessment.get("canonical_scanner_finding_register")
        totals = _mapping(_mapping(register).get("totals"))
        if review is None:
            review = totals.get("review_required")
        if material is None:
            material = totals.get("material")
    return _integer(review), _integer(material)


def review_candidate_truth_markdown(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    spanish = _is_spanish(canonical, spanish)
    review_total, material_total = _candidate_summary(canonical)
    if spanish:
        return "\n".join(
            [
                _ES_HEADING,
                "",
                (
                    "La finalización técnica, el triaje automatizado y la disposición humana "
                    "se mantienen como estados distintos. La evidencia completa permanece "
                    "en los artefactos JSON y CSV de la ejecución exacta."
                ),
                "",
                f"- Candidatos que requieren revisión: {review_total}",
                f"- Hallazgos materiales confirmados: {material_total}",
                f"- {_ES_SCORE_EFFECT}",
            ]
        ).strip() + "\n"
    return "\n".join(
        [
            _EN_HEADING,
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


def _remove_h2_section(markdown: str, heading: str) -> str:
    lines = str(markdown or "").splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == heading),
        None,
    )
    if start is None:
        return str(markdown or "")
    end = next(
        (
            index
            for index in range(start + 1, len(lines))
            if lines[index].startswith("## ")
        ),
        len(lines),
    )
    del lines[start:end]
    return "\n".join(lines).strip() + "\n"


def _clean_evidence_summary(markdown: str) -> str:
    lines = str(markdown or "").splitlines()
    for heading in _EVIDENCE_SUMMARY_HEADINGS:
        start = next(
            (index for index, line in enumerate(lines) if line.strip() == heading),
            None,
        )
        if start is None:
            continue
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if lines[index].startswith("## ")
            ),
            len(lines),
        )
        retained = [lines[start]]
        for line in lines[start + 1 : end]:
            normalized = line.strip().casefold()
            if any(normalized.startswith(prefix) for prefix in _STALE_LINE_PREFIXES):
                continue
            retained.append(line)
        lines[start:end] = retained
        break
    return "\n".join(lines).strip() + "\n"


def _normalize_stale_copy(markdown: str) -> str:
    output = str(markdown or "")
    replacements = (
        ("Candidatos pendientes de revisión", "Candidatos que requieren revisión"),
        (
            "Efecto en puntuación: solo aseguramiento hasta completar la revisión.",
            _ES_SCORE_EFFECT,
        ),
        (
            "Efecto en la puntuación: solo aseguramiento hasta completar la revisión.",
            _ES_SCORE_EFFECT,
        ),
        (
            "Efecto en la puntuación: solo aseguramiento hasta su clasificación.",
            _ES_SCORE_EFFECT,
        ),
        ("Score effect: assurance-only until triaged.", _EN_SCORE_EFFECT),
    )
    for old, new in replacements:
        output = output.replace(old, new)
    return output


def repair_review_candidate_publication(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    """Publish authoritative bilingual candidate truth after every Markdown compiler."""

    spanish = _is_spanish(canonical, spanish)
    output = _clean_evidence_summary(_normalize_stale_copy(str(markdown or "")))
    for heading in _CANDIDATE_HEADINGS:
        while heading in output:
            output = _remove_h2_section(output, heading)

    review_total, _material_total = _candidate_summary(canonical)
    if review_total <= 0:
        return output

    replacement = review_candidate_truth_markdown(canonical, spanish=spanish)
    lines = output.splitlines()
    insert_at = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() in _INSERT_BEFORE_HEADINGS
        ),
        len(lines),
    )
    lines[insert_at:insert_at] = [*replacement.rstrip().splitlines(), ""]
    return "\n".join(lines).strip() + "\n"


def _surface_text(value: Any, *, html_source: bool = False) -> str:
    text = str(value or "")
    if html_source:
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.split())


def validate_review_candidate_surfaces(result: Mapping[str, Any]) -> dict[str, Any]:
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    review_total, material_total = _candidate_summary(canonical)
    spanish = _is_spanish(canonical)
    if review_total <= 0:
        return {
            "version": VERSION,
            "report_language": "es-MX" if spanish else "en",
            "review_candidate_truth_required": False,
            "review_candidate_truth_in_markdown": True,
            "review_candidate_truth_in_html": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    required = (
        (
            _ES_HEADING_TEXT,
            f"Candidatos que requieren revisión: {review_total}",
            f"Hallazgos materiales confirmados: {material_total}",
            _ES_SCORE_EFFECT,
        )
        if spanish
        else (
            _EN_HEADING_TEXT,
            f"Review-required candidates: {review_total}",
            f"Confirmed material findings: {material_total}",
            _EN_SCORE_EFFECT,
        )
    )
    surfaces = {
        "markdown": _surface_text(result.get("markdown")),
        "html": _surface_text(result.get("html"), html_source=True),
    }
    for surface_name, surface in surfaces.items():
        missing = [marker for marker in required if _surface_text(marker) not in surface]
        if missing:
            raise ValueError(
                f"client report omitted review-candidate truth in {surface_name}: {missing[0]}"
            )
        stale = [marker for marker in _STALE_SCORE_EFFECT_MARKERS if marker in surface.casefold()]
        if stale:
            raise ValueError(
                f"client report retained stale review-candidate truth in {surface_name}: {stale[0]}"
            )
    return {
        "version": VERSION,
        "report_language": "es-MX" if spanish else "en",
        "review_candidate_truth_required": True,
        "review_required_total": review_total,
        "verified_material_total": material_total,
        "review_candidate_truth_in_markdown": True,
        "review_candidate_truth_in_html": True,
        "stale_review_candidate_copy_absent": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _install_producer_bridge() -> bool:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_ready_projection_v1 as projection
    from nico import comprehensive_spanish_review_candidate_truth_v70 as legacy

    # The prior repair treated the evidence-summary heading as the candidate
    # section and could replace the summary wholesale. Retain the summary and
    # maintain one dedicated candidate section instead.
    legacy._ES_SECTION_HEADINGS = {_ES_HEADING}
    legacy._EN_SECTION_HEADINGS = {_EN_HEADING}
    legacy.repair_review_candidate_markdown = repair_review_candidate_publication
    legacy.install_spanish_review_candidate_truth_v70()

    current: Callable[..., str] = completion.compact_client_markdown
    if _chain_has_marker(current, _PRODUCER_MARKER):
        projection.compact_client_markdown = current
        return True

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
        return repair_review_candidate_publication(
            rendered,
            canonical,
            spanish=spanish,
        )

    setattr(compact_client_markdown, _PRODUCER_MARKER, True)
    setattr(compact_client_markdown, "_nico_previous", current)
    completion.compact_client_markdown = compact_client_markdown
    projection.compact_client_markdown = compact_client_markdown
    return True


def _install_post_companion_bridge() -> bool:
    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as companion

    current: Callable[..., str] = completion.merge_review_companion_markdown
    if _chain_has_marker(current, _MERGE_MARKER):
        companion.merge_review_companion_markdown = current
        return True

    @wraps(current)
    def merge_review_companion_markdown(
        markdown: str,
        canonical: Mapping[str, Any],
        *,
        spanish: bool,
    ) -> str:
        rendered = current(markdown, canonical, spanish=spanish)
        return repair_review_candidate_publication(
            rendered,
            canonical,
            spanish=spanish,
        )

    setattr(merge_review_companion_markdown, _MERGE_MARKER, True)
    setattr(merge_review_companion_markdown, "_nico_previous", current)
    completion.merge_review_companion_markdown = merge_review_companion_markdown
    companion.merge_review_companion_markdown = merge_review_companion_markdown
    return True


def _install_final_validation_bridge() -> bool:
    from nico import client_report_completion_v2 as completion
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17

    current = completion.finalize_client_report_package
    if _chain_has_marker(current, _FINAL_MARKER):
        phase17.finalize_client_report_package = current
        return True

    @wraps(current)
    def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
        result = current(package)
        validation = validate_review_candidate_surfaces(result)
        completion_contract = deepcopy(dict(result.get("client_report_completion") or {}))
        completion_contract.update(validation)
        result["client_report_completion"] = completion_contract
        return result

    setattr(finalize_client_report_package, _FINAL_MARKER, True)
    setattr(finalize_client_report_package, "_nico_previous", current)
    completion.finalize_client_report_package = finalize_client_report_package
    phase17.finalize_client_report_package = finalize_client_report_package
    return True


def install_comprehensive_review_candidate_publication_v75() -> dict[str, Any]:
    producer_bound = _install_producer_bridge()
    post_companion_bound = _install_post_companion_bridge()
    final_validation_bound = _install_final_validation_bridge()
    return {
        "status": "installed",
        "version": VERSION,
        "producer_bound_after_late_installers": producer_bound,
        "post_companion_repair_bound": post_companion_bound,
        "final_surface_validation_bound": final_validation_bound,
        "evidence_summary_preserved": True,
        "dedicated_review_candidate_section": True,
        "english_and_spanish_supported": True,
        "stale_review_candidate_copy_removed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_review_candidate_publication_v75",
    "repair_review_candidate_publication",
    "review_candidate_truth_markdown",
    "validate_review_candidate_surfaces",
]
