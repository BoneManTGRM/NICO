from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-report-semantic-content-gate.v68"
_MARKER = "_nico_comprehensive_semantic_content_gate_v68"
_FINDING_REGISTER_MARKERS = (
    "finding and remediation register",
    "registro de hallazgos y remediación",
    "registro de hallazgos y remediacion",
    "detailed canonical findings",
    "hallazgos canónicos detallados",
    "hallazgos canonicos detallados",
)
_CURRENT_REVIEW_SCORE_EFFECT_MARKERS = (
    "score effect: assurance-only while authorized human disposition remains pending; nico automated technical triage is complete",
    "score effect: assurance-only while human disposition remains pending; nico technical triage is complete",
    "efecto en puntuación: solo aseguramiento mientras la disposición humana siga pendiente; el triage técnico de nico está completo",
    "efecto en la puntuación: solo aseguramiento mientras la disposición humana siga pendiente; el triage técnico de nico está completo",
)
_SUPERSEDED_REVIEW_SCORE_EFFECT_MARKERS = (
    "score effect: assurance-only until triaged",
    "efecto en la puntuación: solo aseguramiento hasta su clasificación",
)
_EN_REVIEW_MARKERS = (
    "review-required candidates: {review_total}",
    "confirmed material findings: {material_total}",
    "review-required candidate register",
)
_ES_REVIEW_MARKERS = (
    "candidatos que requieren revisión: {review_total}",
    "hallazgos materiales confirmados: {material_total}",
    "registro de candidatos que requieren revisión",
)
_CI_OPERATIONAL_MARKERS = (
    "ci/cd operational readiness and historical health",
    "preparación operativa y salud histórica de ci/cd",
    "preparacion operativa y salud historica de ci/cd",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _review_score_effect_marker(lowered: str) -> str:
    return next(
        (marker for marker in _CURRENT_REVIEW_SCORE_EFFECT_MARKERS if marker in lowered),
        "",
    )


def _report_language(package: Mapping[str, Any], canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    value = _text(
        package.get("report_language")
        or canonical.get("report_language")
        or identity.get("report_language")
        or assessment.get("report_language")
    ).casefold()
    return "es-MX" if value.startswith("es") else "en"


def validate_retained_decision_content(package: Mapping[str, Any]) -> dict[str, Any]:
    """Fail publication when retained decision content disappears from client formats."""

    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    hotspots = [item for item in canonical.get("architecture_hotspots") or [] if isinstance(item, Mapping)]
    review_summary = (
        canonical.get("review_candidate_summary")
        if isinstance(canonical.get("review_candidate_summary"), Mapping)
        else assessment.get("review_candidate_summary")
        if isinstance(assessment.get("review_candidate_summary"), Mapping)
        else {}
    )
    ci_context = (
        canonical.get("ci_operational_context")
        if isinstance(canonical.get("ci_operational_context"), Mapping)
        else assessment.get("ci_operational_context")
        if isinstance(assessment.get("ci_operational_context"), Mapping)
        else {}
    )
    language = _report_language(package, canonical)
    combined = "\n".join((str(package.get("markdown") or ""), str(package.get("html") or "")))
    lowered = combined.casefold()

    finding_count = len(findings)
    finding_register_marker = ""
    if finding_count:
        false_zero_markers = (
            "no unresolved priority finding retained",
            "contains 0 unique decision-grade findings",
            "exact-source findings: 0",
            "canonical findings: 0",
            "no canonical actionable finding was retained",
        )
        retained_false_zero = [marker for marker in false_zero_markers if marker in lowered]
        if retained_false_zero:
            raise ValueError(
                "client report suppressed retained canonical findings: "
                + ", ".join(retained_false_zero)
            )
        missing_ids = [
            identifier
            for item in findings
            if (identifier := _text(item.get("finding_id") or item.get("id")))
            and identifier.casefold() not in lowered
        ]
        if missing_ids:
            raise ValueError(
                "client report omitted retained canonical finding identifiers: "
                + ", ".join(missing_ids[:10])
            )
        finding_register_marker = next(
            (marker for marker in _FINDING_REGISTER_MARKERS if marker in lowered),
            "",
        )
        if not finding_register_marker:
            raise ValueError(
                "client report omitted the authoritative finding and remediation register"
            )

    if hotspots and not findings:
        raise ValueError(
            "client report declared zero canonical findings despite actionable exact-SHA complexity hotspots"
        )

    review_total = _integer(review_summary.get("review_required_total"))
    material_total = _integer(review_summary.get("verified_material_total"))
    score_effect_marker = ""
    superseded_score_effect_marker = ""
    if review_total:
        templates = _ES_REVIEW_MARKERS if language == "es-MX" else _EN_REVIEW_MARKERS
        required_markers = tuple(
            marker.format(review_total=review_total, material_total=material_total)
            for marker in templates
        )
        missing = [marker for marker in required_markers if marker.casefold() not in lowered]
        if missing:
            raise ValueError(
                "client report omitted review-candidate truth: " + ", ".join(missing)
            )

        superseded_score_effect_marker = next(
            (marker for marker in _SUPERSEDED_REVIEW_SCORE_EFFECT_MARKERS if marker in lowered),
            "",
        )
        if superseded_score_effect_marker:
            raise ValueError(
                "client report retained superseded review-candidate score-effect language: "
                + superseded_score_effect_marker
            )

        score_effect_marker = _review_score_effect_marker(lowered)
        if not score_effect_marker:
            raise ValueError(
                "client report omitted review-candidate truth: score effect must state that "
                "assurance remains limited while human disposition is pending and NICO technical "
                "triage is complete"
            )

    ci_operational_marker = ""
    if ci_context:
        ci_operational_marker = next(
            (marker for marker in _CI_OPERATIONAL_MARKERS if marker in lowered),
            "",
        )
        if not ci_operational_marker:
            raise ValueError(
                "client report omitted CI/CD operational health that must remain separate from configuration maturity"
            )

    return {
        "version": VERSION,
        "report_language": language,
        "canonical_finding_count_rendered": finding_count,
        "architecture_hotspot_count_checked": len(hotspots),
        "review_required_candidate_count_rendered": review_total,
        "confirmed_material_candidate_count_rendered": material_total,
        "review_candidate_score_effect_marker": score_effect_marker,
        "review_candidate_score_effect_truth_present": not review_total or bool(score_effect_marker),
        "superseded_review_candidate_score_effect_absent": not bool(superseded_score_effect_marker),
        "ci_operational_context_rendered": not bool(ci_context) or bool(ci_operational_marker),
        "ci_operational_context_marker": ci_operational_marker,
        "finding_register_marker": finding_register_marker,
        "authoritative_finding_register_present": not finding_count or bool(finding_register_marker),
        "false_zero_finding_claim_absent": True,
        "retained_finding_identifiers_present": True,
        "review_candidate_truth_present": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_report_semantic_content_gate_v66() -> dict[str, Any]:
    from nico import comprehensive_client_report_render_v60 as client_render

    current = client_render.validate_existing_report_accuracy
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def validate(package: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(current(package))
        content = validate_retained_decision_content(package)
        result["semantic_content_gate"] = content
        result.update(
            {
                "canonical_decision_content_verified": True,
                "authoritative_finding_register_verified": True,
                "review_candidate_truth_verified": True,
                "ci_operational_context_verified": True,
            }
        )
        return result

    setattr(validate, _MARKER, True)
    setattr(validate, "_nico_previous", current)
    client_render.validate_existing_report_accuracy = validate
    return {
        "status": "installed",
        "version": VERSION,
        "bound": client_render.validate_existing_report_accuracy is validate,
        "false_zero_finding_publication_blocked": True,
        "authoritative_finding_register_omission_blocked": True,
        "review_candidate_omission_blocked": True,
        "spanish_review_candidate_truth_supported": True,
        "superseded_review_candidate_score_effect_blocked": True,
        "current_phase1_review_candidate_score_effect_required": True,
        "ci_operational_context_omission_blocked": True,
        "spanish_ci_operational_truth_supported": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_report_semantic_content_gate_v66",
    "validate_retained_decision_content",
]
