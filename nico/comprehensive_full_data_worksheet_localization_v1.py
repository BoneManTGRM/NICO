from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-full-data-worksheet-localization.v2.1"
_MARKER = "__nico_comprehensive_full_data_worksheet_localization_v1__"

SPANISH_CANDIDATE_REGISTER = "Registro de candidatos que requieren revisión"
SPANISH_REVIEW_GATE = "Puerta de revisión humana y aceptación"
SPANISH_EXACT_SOURCE_INDEX = "Índice completo de fuentes exactas"

WORKSHEET_TITLES_BY_STAGE_ID: dict[str, tuple[str, str]] = {
    "functional_qa": ("Functional QA", "QA funcional"),
    "platform_parity": ("Platform Parity", "Paridad de plataformas"),
    "historical_trends_and_change_failure": (
        "Historical Trends and Change Failure",
        "Tendencias históricas y fallos de cambio",
    ),
    "requirements_traceability": (
        "Requirements Traceability",
        "Trazabilidad de requisitos",
    ),
    "stakeholder_and_business_alignment": (
        "Stakeholder and Business Alignment",
        "Alineación comercial y de partes interesadas",
    ),
    "risk_reduction_and_executive_briefing": (
        "Risk Reduction and Executive Briefing",
        "Reducción de riesgo y resumen ejecutivo",
    ),
    "six_month_roadmap": ("Six-Month Roadmap", "Hoja de ruta de seis meses"),
    "staffing_sequencing_and_cost": (
        "Staffing, Sequencing, and Cost",
        "Personal, secuencia y costo",
    ),
}

# These aliases are the same stable semantic IDs accepted by the current review
# companion. Supporting them prevents a valid retained worksheet from being lost
# merely because an older canonical stage uses its established short ID.
WORKSHEET_STAGE_ALIASES: dict[str, tuple[str, ...]] = {
    "functional_qa": ("functional_qa",),
    "platform_parity": ("platform_parity",),
    "historical_trends_and_change_failure": (
        "historical_trends_and_change_failure",
        "historical_trends",
    ),
    "requirements_traceability": ("requirements_traceability",),
    "stakeholder_and_business_alignment": (
        "stakeholder_and_business_alignment",
        "stakeholder_alignment",
    ),
    "risk_reduction_and_executive_briefing": (
        "risk_reduction_and_executive_briefing",
    ),
    "six_month_roadmap": ("six_month_roadmap",),
    "staffing_sequencing_and_cost": (
        "staffing_sequencing_and_cost",
        "resourcing",
    ),
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _stage_id(value: Any) -> str:
    return "_".join(_text(value, 180).casefold().replace("-", "_").split())


def _worksheet_key(value: Any) -> str | None:
    normalized = _stage_id(value)
    for canonical_id, aliases in WORKSHEET_STAGE_ALIASES.items():
        if normalized in aliases:
            return canonical_id
    return None


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    # Persisted run identity is the terminal language authority. Check it first so
    # a stale root projection cannot turn an es-MX run back into English.
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    for key in ("report_language", "requested_report_language", "requested_locale", "locale"):
        value = _text(identity.get(key), 40).casefold()
        if value:
            return value.startswith("es")
    try:
        from nico.comprehensive_report_language_truth_v77 import resolve_report_language

        return resolve_report_language(canonical) == "es-MX"
    except (ImportError, AttributeError):
        assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
        value = _text(
            canonical.get("report_language")
            or canonical.get("locale")
            or assessment.get("report_language")
            or assessment.get("locale"),
            40,
        ).casefold()
        return value.startswith("es")


def _stages(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    values = canonical.get("stage_summaries")
    if not isinstance(values, list):
        values = assessment.get("stage_summaries")
    return [item for item in values or [] if isinstance(item, Mapping)]


def _visible_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "\n", str(value or "")))


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def _normalize_required_stage_titles(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize only existing required stages by stable semantic ID; never synthesize one."""

    result = deepcopy(dict(canonical))
    source = _stages(result)
    present = {
        key
        for stage in source
        if (key := _worksheet_key(stage.get("stage_id"))) is not None
    }
    missing_ids = [stage_id for stage_id in WORKSHEET_TITLES_BY_STAGE_ID if stage_id not in present]
    if missing_ids:
        missing_titles = [WORKSHEET_TITLES_BY_STAGE_ID[stage_id][0] for stage_id in missing_ids]
        raise ValueError(
            "full-data proof is missing human-review worksheets: " + ", ".join(missing_titles)
        )

    normalized: list[dict[str, Any]] = []
    for raw in source:
        stage = deepcopy(dict(raw))
        key = _worksheet_key(stage.get("stage_id"))
        if key:
            stage["title"] = WORKSHEET_TITLES_BY_STAGE_ID[key][0]
        normalized.append(stage)

    result["stage_summaries"] = normalized
    assessment = deepcopy(dict(result.get("assessment") or {})) if isinstance(result.get("assessment"), Mapping) else {}
    assessment["stage_summaries"] = deepcopy(normalized)
    result["assessment"] = assessment
    return result


def _assert_localized_worksheet_surfaces(markdown: str, rendered_html: str, extracted: str) -> None:
    combined = "\n".join((markdown, _visible_html(rendered_html), extracted))
    missing = [
        spanish_title
        for _english_title, spanish_title in WORKSHEET_TITLES_BY_STAGE_ID.values()
        if spanish_title not in combined
    ]
    if missing:
        raise ValueError(
            "full-data Spanish proof is missing localized human-review worksheets: "
            + ", ".join(missing)
        )


def _assert_spanish_exact_source_index(
    findings: list[Mapping[str, Any]], extracted: str
) -> None:
    from nico.comprehensive_exact_source_index_validation_v1 import compact_pdf_identifier

    if SPANISH_EXACT_SOURCE_INDEX not in extracted:
        raise ValueError(
            f"full-data PDF is missing required section: {SPANISH_EXACT_SOURCE_INDEX}"
        )
    index_text = extracted.split(SPANISH_EXACT_SOURCE_INDEX, 1)[1]
    compact_index = compact_pdf_identifier(index_text)
    identifiers: list[str] = []
    seen: set[str] = set()
    for item in findings:
        identifier = _text(item.get("finding_id") or item.get("id"), 300)
        if not identifier:
            raise ValueError("canonical exact-source finding is missing a stable finding identifier")
        compact = compact_pdf_identifier(identifier)
        if compact in seen:
            raise ValueError(f"canonical exact-source finding identifier is duplicated: {identifier}")
        seen.add(compact)
        identifiers.append(identifier)
    omitted = [identifier for identifier in identifiers if compact_pdf_identifier(identifier) not in compact_index]
    if omitted:
        raise ValueError(
            f"full-data PDF index omitted {len(omitted)} canonical exact-source finding(s)"
        )


def _assert_spanish_full_data_parity(
    finish: Any,
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> dict[str, Any]:
    """Run the strict full-data proof against the actual Spanish presentation."""

    validation_canonical = _normalize_required_stage_titles(canonical)
    if finish.classify_report_proof(validation_canonical) != "full_comprehensive":
        raise ValueError("sparse fixture cannot satisfy full-data Comprehensive parity validation")

    extracted = _pdf_text(pdf)
    combined = "\n".join((markdown or "", _visible_html(rendered_html), extracted))
    sections = finish._sections(canonical)
    if not sections:
        raise ValueError("full-data proof is missing the canonical scorecard")

    _assert_localized_worksheet_surfaces(markdown, rendered_html, extracted)

    scanners = finish._scanners(canonical)
    assessment = finish._assessment(canonical)
    requested = assessment.get("requested_scanner_records") or canonical.get("requested_scanner_records")
    if requested and not scanners:
        raise ValueError("full-data proof is missing applicable scanner execution evidence")

    candidates = finish._candidate_total(canonical)
    if candidates and not finish._candidate_register(canonical):
        raise ValueError("full-data proof has candidates but no canonical candidate register")
    if candidates and SPANISH_CANDIDATE_REGISTER not in combined:
        raise ValueError("full-data proof is missing the localized candidate register section")

    findings = finish._findings(canonical)
    _assert_spanish_exact_source_index(findings, extracted)

    # The detached manifest/approval supplement is intentionally technical and
    # remains English today; the two client-report sections are localized.
    for title in (
        "Client Artifact Manifest",
        "Human Review and Exact-Artifact Approval Record",
        SPANISH_REVIEW_GATE,
        SPANISH_EXACT_SOURCE_INDEX,
    ):
        if title not in extracted:
            raise ValueError(f"full-data PDF is missing required section: {title}")

    timestamp = finish.canonical_generation_timestamp(canonical)
    if not timestamp:
        raise ValueError("full-data manifest is missing a canonical generation timestamp")
    if (
        "Generated\nNot available" in extracted
        or "Generated: Not available" in extracted
        or "Generado\nNo disponible" in extracted
        or "Generado: No disponible" in extracted
    ):
        raise ValueError("full-data manifest silently degraded the generation timestamp")

    return {
        "proof_kind": "full_comprehensive",
        "scored_control_count": len(sections),
        "scanner_execution_count": len(scanners),
        "candidate_count": candidates,
        "exact_source_finding_count": len(findings),
        "worksheet_count": len(WORKSHEET_TITLES_BY_STAGE_ID),
        "generation_timestamp": timestamp,
        "localized_spanish_full_data_validation": True,
        "worksheet_identity_source": "stable_stage_id_or_established_alias",
        "persisted_report_language_authority": True,
    }


def install_comprehensive_full_data_worksheet_localization_v1() -> dict[str, Any]:
    """Make the legacy full-data proof bilingual without weakening any truth gate."""

    from nico import comprehensive_full_report_finish_v1 as finish

    current = finish.assert_full_data_parity
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "stable_stage_ids_required": True,
            "established_stage_aliases_supported": True,
            "localized_spanish_full_data_sections_required": True,
            "missing_worksheets_not_synthesized": True,
            "exact_source_identifiers_required": True,
            "persisted_report_language_authority": True,
            "english_path_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def assert_full_data_parity(
        canonical: Mapping[str, Any],
        markdown: str,
        rendered_html: str,
        pdf: bytes,
    ) -> dict[str, Any]:
        if not _is_spanish(canonical):
            return current(canonical, markdown, rendered_html, pdf)
        return _assert_spanish_full_data_parity(
            finish, canonical, markdown, rendered_html, pdf
        )

    setattr(assert_full_data_parity, _MARKER, True)
    setattr(assert_full_data_parity, "_nico_previous", current)
    finish.assert_full_data_parity = assert_full_data_parity
    return {
        "status": "installed",
        "version": VERSION,
        "stable_stage_ids_required": True,
        "established_stage_aliases_supported": True,
        "localized_spanish_full_data_sections_required": True,
        "missing_worksheets_not_synthesized": True,
        "exact_source_identifiers_required": True,
        "persisted_report_language_authority": True,
        "english_path_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "SPANISH_CANDIDATE_REGISTER",
    "SPANISH_REVIEW_GATE",
    "SPANISH_EXACT_SOURCE_INDEX",
    "WORKSHEET_STAGE_ALIASES",
    "WORKSHEET_TITLES_BY_STAGE_ID",
    "install_comprehensive_full_data_worksheet_localization_v1",
]
