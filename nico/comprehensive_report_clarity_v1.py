from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-report-clarity.v1"
_MARKER = "_nico_comprehensive_report_clarity_v1"

_ASSURANCE_DISCLOSURE_RE = re.compile(
    r"(?:\s*Confirmed material findings:\s*\d+\.\s*"
    r"Review-required candidates:\s*\d+\.\s*"
    r"Score effect:\s*assurance-only until triaged\.)+",
    re.IGNORECASE,
)
_COMPLEXITY_UNKNOWN_RE = re.compile(
    r"complexity\s+risk\s*:\s*unknown\.?",
    re.IGNORECASE,
)
_COMPLEXITY_OBSERVED_RE = re.compile(
    r"complexity\s+risk\s*:\s*observed\s*;",
    re.IGNORECASE,
)
_CANDIDATE_SECTION_ALIASES = {
    "dependency": ("dependency", "library"),
    "secret": ("secret",),
    "static": ("static",),
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return language.startswith("es")


def _section_identity(section: Mapping[str, Any]) -> str:
    return _text(
        section.get("section_id")
        or section.get("id")
        or section.get("name")
        or section.get("label")
    ).casefold()


def _candidate_category(section: Mapping[str, Any]) -> str | None:
    identity = _section_identity(section)
    for category, aliases in _CANDIDATE_SECTION_ALIASES.items():
        if any(alias in identity for alias in aliases):
            return category
    return None


def _provisional_label(*, spanish: bool) -> str:
    return (
        "Fuerte provisional — Revisión humana requerida"
        if spanish
        else "Provisional Strong — Human Review Required"
    )


def _strip_disclosure(value: Any) -> str:
    cleaned = _ASSURANCE_DISCLOSURE_RE.sub(" ", _text(value))
    return " ".join(cleaned.split()).strip()


def _dedupe(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        value = _text(raw)
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _normalize_candidate_section(
    section: Mapping[str, Any],
    *,
    spanish: bool,
) -> dict[str, Any]:
    item = deepcopy(dict(section))
    review_required = _integer(item.get("review_required_candidates"))
    if not review_required:
        score_contract = (
            item.get("score_contract")
            if isinstance(item.get("score_contract"), Mapping)
            else {}
        )
        review_required = _integer(score_contract.get("review_required_count"))
    if not review_required:
        return item

    material = _integer(item.get("confirmed_material_findings"))
    if not material:
        score_contract = (
            item.get("score_contract")
            if isinstance(item.get("score_contract"), Mapping)
            else {}
        )
        material = _integer(score_contract.get("material_count"))

    label = _provisional_label(spanish=spanish)
    item.update(
        {
            "presented_status": label,
            "status_label": label,
            "human_review_required": True,
            "confirmed_material_findings": material,
            "review_required_candidates": review_required,
            "score_effect": "assurance-only until triaged",
        }
    )
    item["summary"] = _strip_disclosure(item.get("summary"))

    evidence: list[str] = []
    for line in _dedupe(item.get("evidence")):
        lowered = line.casefold()
        if lowered.startswith(
            (
                "verified material:",
                "confirmed material findings:",
                "review required:",
                "review-required candidates:",
                "score effect:",
                "technical-score impact is limited to verified material findings",
            )
        ):
            continue
        evidence.append(line)
    evidence.extend(
        (
            (
                f"Hallazgos materiales confirmados: {material}."
                if spanish
                else f"Confirmed material findings: {material}."
            ),
            (
                f"Candidatos que requieren revisión: {review_required}."
                if spanish
                else f"Review-required candidates: {review_required}."
            ),
            (
                "Efecto en la puntuación: solo aseguramiento hasta su clasificación."
                if spanish
                else "Score effect: assurance-only until triaged."
            ),
        )
    )
    item["evidence"] = _dedupe(evidence)

    item["unavailable"] = [
        line
        for line in _dedupe(item.get("unavailable"))
        if not (
            "unverified candidate" in line.casefold()
            and "remain review-required" in line.casefold()
        )
    ]
    return item


def _hotspot_identity(item: Mapping[str, Any]) -> str:
    return _text(
        item.get("finding_id")
        or item.get("id")
        or item.get("location")
        or item.get("exact_source")
        or (
            f"{_text(item.get('path'))}:{_text(item.get('line') or item.get('start_line'))}"
        )
    ).casefold()


def _hotspot_count(canonical: Mapping[str, Any]) -> int:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    for value in (
        canonical.get("architecture_hotspots"),
        assessment.get("architecture_hotspots"),
    ):
        if isinstance(value, list) and value:
            identities = {
                identity
                for raw in value
                if isinstance(raw, Mapping)
                and (identity := _hotspot_identity(raw))
            }
            return len(identities) if identities else len(
                [raw for raw in value if isinstance(raw, Mapping)]
            )

    register = (
        canonical.get("client_finding_remediation_register")
        if isinstance(canonical.get("client_finding_remediation_register"), Mapping)
        else {}
    )
    candidates = [
        raw
        for raw in register.get("code_findings") or []
        if isinstance(raw, Mapping)
        and _text(raw.get("finding_family")).casefold() == "complexity_hotspot"
    ]
    identities = {
        identity
        for raw in candidates
        if (identity := _hotspot_identity(raw))
    }
    return len(identities) if identities else len(candidates)


def _architecture_section_present(canonical: Mapping[str, Any]) -> bool:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    sections = (
        assessment.get("sections")
        if isinstance(assessment.get("sections"), list)
        else []
    )
    return any(
        isinstance(item, Mapping) and "architect" in _section_identity(item)
        for item in sections
    )


def _normalize_architecture_section(
    section: Mapping[str, Any],
    *,
    hotspot_count: int,
    spanish: bool,
) -> dict[str, Any]:
    item = deepcopy(dict(section))
    if hotspot_count <= 0:
        return item

    evidence = [
        line
        for line in _dedupe(item.get("evidence"))
        if not _COMPLEXITY_UNKNOWN_RE.search(line)
        and not _COMPLEXITY_OBSERVED_RE.search(line)
        and "riesgo de complejidad:" not in line.casefold()
    ]
    evidence.append(
        (
            "Riesgo de complejidad: observado; "
            f"{hotspot_count} hallazgos de complejidad con fuente exacta "
            "siguen pendientes de revisión humana."
            if spanish
            else "Complexity risk: observed; "
            f"{hotspot_count} exact-source complexity findings remain pending human review."
        )
    )
    item["evidence"] = _dedupe(evidence)
    item["exact_source_complexity_finding_count"] = hotspot_count
    item["complexity_risk_status"] = "observed_pending_human_review"
    return item


def normalize_comprehensive_report_clarity(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Deduplicate candidate disclosures and reconcile retained complexity truth."""

    result = deepcopy(dict(canonical))
    assessment = deepcopy(dict(result.get("assessment") or {}))
    sections = (
        assessment.get("sections")
        if isinstance(assessment.get("sections"), list)
        else []
    )
    spanish = _is_spanish(result)
    hotspot_count = _hotspot_count(result)
    normalized_sections: list[Any] = []

    for raw in sections:
        if not isinstance(raw, Mapping):
            normalized_sections.append(deepcopy(raw))
            continue
        item = deepcopy(dict(raw))
        if _candidate_category(item):
            item = _normalize_candidate_section(item, spanish=spanish)
        if "architect" in _section_identity(item):
            item = _normalize_architecture_section(
                item,
                hotspot_count=hotspot_count,
                spanish=spanish,
            )
        normalized_sections.append(item)

    assessment["sections"] = normalized_sections
    if hotspot_count:
        assessment["exact_source_complexity_finding_count"] = hotspot_count
    result["assessment"] = assessment

    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "comprehensive_report_clarity_version": VERSION,
            "candidate_section_summaries_deduplicated": True,
            "review_candidate_presented_status_requires_human_review": True,
            "exact_source_complexity_truth_reconciled": bool(
                hotspot_count and _architecture_section_present(result)
            ),
            "numeric_scores_unchanged_by_report_clarity": True,
            "scanner_dispositions_unchanged_by_report_clarity": True,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def _score_snapshot(canonical: Mapping[str, Any]) -> tuple[Any, ...]:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    maturity = (
        assessment.get("maturity_signal")
        if isinstance(assessment.get("maturity_signal"), Mapping)
        else {}
    )
    sections = (
        assessment.get("sections")
        if isinstance(assessment.get("sections"), list)
        else []
    )
    return (
        assessment.get("technical_score"),
        assessment.get("canonical_evidence_adjusted_score"),
        maturity.get("technical_score"),
        maturity.get("presented_score"),
        tuple(
            (
                _section_identity(item),
                item.get("score"),
                item.get("presented_score"),
                item.get("source_score"),
            )
            for item in sections
            if isinstance(item, Mapping)
        ),
    )


def _combined_text(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> str:
    from pypdf import PdfReader

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    canonical_text = _text(canonical, 250000)
    return "\n".join((canonical_text, markdown, html.unescape(rendered_html), extracted))


def assert_comprehensive_report_clarity(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    sections = (
        assessment.get("sections")
        if isinstance(assessment.get("sections"), list)
        else []
    )
    spanish = _is_spanish(canonical)
    expected_label = _provisional_label(spanish=spanish).casefold()

    for raw in sections:
        if not isinstance(raw, Mapping) or not _candidate_category(raw):
            continue
        review_required = _integer(raw.get("review_required_candidates"))
        if not review_required:
            continue
        if _text(raw.get("presented_status")).casefold() != expected_label:
            raise ValueError(
                "review-required candidate section omitted the provisional "
                "human-review presented status"
            )
        if _ASSURANCE_DISCLOSURE_RE.search(_text(raw.get("summary"))):
            raise ValueError(
                "review-required candidate section retained repeated assurance disclosure"
            )

        evidence = _dedupe(raw.get("evidence"))
        if spanish:
            material_marker = "hallazgos materiales confirmados:"
            candidate_marker = "candidatos que requieren revisión:"
            score_marker = "efecto en la puntuación:"
        else:
            material_marker = "confirmed material findings:"
            candidate_marker = "review-required candidates:"
            score_marker = "score effect:"
        markers = (material_marker, candidate_marker, score_marker)
        for marker in markers:
            count = sum(line.casefold().startswith(marker) for line in evidence)
            if count != 1:
                raise ValueError(
                    f"candidate section must retain exactly one `{marker}` evidence line"
                )

    hotspot_count = _hotspot_count(canonical)
    combined = " ".join(_combined_text(
        canonical,
        markdown,
        rendered_html,
        pdf,
    ).split())
    if hotspot_count and _architecture_section_present(canonical):
        if _COMPLEXITY_UNKNOWN_RE.search(combined):
            raise ValueError(
                "architecture section reported unknown complexity despite retained hotspots"
            )
        marker = (
            "Riesgo de complejidad: observado;"
            if spanish
            else "Complexity risk: observed;"
        )
        if marker.casefold() not in combined.casefold() or str(hotspot_count) not in combined:
            raise ValueError(
                "architecture section omitted the retained exact-source complexity count"
            )


def install_comprehensive_report_clarity() -> dict[str, Any]:
    """Bind report clarity normalization into the authoritative completion path."""

    from nico import client_report_completion_v2 as completion

    current_sync = completion.synchronize_canonical_finding_surfaces
    if not getattr(current_sync, _MARKER, False):

        @wraps(current_sync)
        def synchronize(
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
        ) -> dict[str, Any]:
            before = _score_snapshot(canonical)
            result = normalize_comprehensive_report_clarity(
                current_sync(canonical, register)
            )
            if before != _score_snapshot(result):
                raise ValueError("report clarity normalization changed numeric scores")
            return result

        setattr(synchronize, _MARKER, True)
        setattr(synchronize, "_nico_previous", current_sync)
        completion.synchronize_canonical_finding_surfaces = synchronize

    current_reconcile = completion.reconcile_authoritative_scanner_truth
    if not getattr(current_reconcile, _MARKER, False):

        @wraps(current_reconcile)
        def reconcile(canonical: Mapping[str, Any]) -> dict[str, Any]:
            reconciled = current_reconcile(canonical)
            before = _score_snapshot(reconciled)
            result = normalize_comprehensive_report_clarity(reconciled)
            if before != _score_snapshot(result):
                raise ValueError("report clarity normalization changed numeric scores")
            return result

        setattr(reconcile, _MARKER, True)
        setattr(reconcile, "_nico_previous", current_reconcile)
        completion.reconcile_authoritative_scanner_truth = reconcile

    current_validate = completion._validate_final_surfaces
    if not getattr(current_validate, _MARKER, False):

        @wraps(current_validate)
        def validate(
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> dict[str, Any]:
            assert_comprehensive_report_clarity(
                canonical,
                markdown,
                rendered_html,
                pdf,
            )
            result = dict(
                current_validate(
                    canonical,
                    register,
                    markdown,
                    rendered_html,
                    pdf,
                )
            )
            result.update(
                {
                    "candidate_section_summaries_deduplicated": True,
                    "review_candidate_status_requires_human_review": True,
                    "exact_source_complexity_truth_reconciled": bool(
                        _hotspot_count(canonical)
                        and _architecture_section_present(canonical)
                    ),
                    "numeric_scores_unchanged_by_report_clarity": True,
                }
            )
            return result

        setattr(validate, _MARKER, True)
        setattr(validate, "_nico_previous", current_validate)
        completion._validate_final_surfaces = validate

    return {
        "status": "installed",
        "version": VERSION,
        "canonical_sync_bound": getattr(
            completion.synchronize_canonical_finding_surfaces,
            _MARKER,
            False,
        ),
        "scanner_reconciliation_bound": getattr(
            completion.reconcile_authoritative_scanner_truth,
            _MARKER,
            False,
        ),
        "final_surface_gate_bound": getattr(
            completion._validate_final_surfaces,
            _MARKER,
            False,
        ),
        "scores_unchanged": True,
        "scanner_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_comprehensive_report_clarity",
    "install_comprehensive_report_clarity",
    "normalize_comprehensive_report_clarity",
]
