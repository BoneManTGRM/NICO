from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-full-data-worksheet-localization.v1"
_MARKER = "__nico_comprehensive_full_data_worksheet_localization_v1__"

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


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _stage_id(value: Any) -> str:
    return "_".join(_text(value, 180).casefold().replace("-", "_").split())


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
        or "en",
        40,
    ).casefold()
    return language.startswith("es")


def _stages(canonical: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    values = canonical.get("stage_summaries")
    if not isinstance(values, list):
        values = assessment.get("stage_summaries")
    return [item for item in values or [] if isinstance(item, Mapping)]


def _visible_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "\n", str(value or "")))


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def _normalize_required_stage_titles(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize titles by stable stage ID without creating a missing worksheet."""

    result = deepcopy(dict(canonical))
    source = _stages(result)
    by_id = {_stage_id(stage.get("stage_id")): stage for stage in source}
    missing_ids = [stage_id for stage_id in WORKSHEET_TITLES_BY_STAGE_ID if stage_id not in by_id]
    if missing_ids:
        missing_titles = [WORKSHEET_TITLES_BY_STAGE_ID[stage_id][0] for stage_id in missing_ids]
        raise ValueError(
            "full-data proof is missing human-review worksheets: "
            + ", ".join(missing_titles)
        )

    normalized: list[dict[str, Any]] = []
    for raw in source:
        stage = deepcopy(dict(raw))
        titles = WORKSHEET_TITLES_BY_STAGE_ID.get(_stage_id(stage.get("stage_id")))
        if titles:
            stage["title"] = titles[0]
        normalized.append(stage)

    result["stage_summaries"] = normalized
    assessment = (
        deepcopy(dict(result.get("assessment") or {}))
        if isinstance(result.get("assessment"), Mapping)
        else {}
    )
    assessment["stage_summaries"] = deepcopy(normalized)
    result["assessment"] = assessment
    return result


def _assert_localized_worksheet_surfaces(
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    combined = "\n".join((markdown, _visible_html(rendered_html), _pdf_text(pdf)))
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


def _english_alias_block() -> str:
    return "\n".join(
        english_title
        for english_title, _spanish_title in WORKSHEET_TITLES_BY_STAGE_ID.values()
    )


def install_comprehensive_full_data_worksheet_localization_v1() -> dict[str, Any]:
    """Keep the strict full-data gate while validating Spanish worksheet presentation."""

    from nico import comprehensive_full_report_finish_v1 as finish

    current = finish.assert_full_data_parity
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "stable_stage_ids_required": True,
            "localized_spanish_worksheet_titles_required": True,
            "missing_worksheets_not_synthesized": True,
            "all_non_worksheet_full_data_checks_preserved": True,
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

        # The compact Spanish review companion deliberately renders localized
        # headings. The legacy full-data gate still compares those surfaces with
        # English presentation titles. Prove the actual Spanish headings first,
        # require every canonical worksheet by stable machine stage ID, then give
        # only the legacy title comparison English aliases. Every subsequent gate
        # still runs against the original PDF and canonical evidence population.
        _assert_localized_worksheet_surfaces(markdown, rendered_html, pdf)
        validation_canonical = _normalize_required_stage_titles(canonical)
        validation_markdown = (
            str(markdown or "").rstrip()
            + "\n\n<!-- validation aliases for localized worksheet headings -->\n"
            + _english_alias_block()
            + "\n"
        )
        result = current(
            validation_canonical,
            validation_markdown,
            rendered_html,
            pdf,
        )
        if isinstance(result, Mapping):
            output = dict(result)
            output["localized_spanish_worksheet_validation"] = True
            output["worksheet_identity_source"] = "stable_stage_id"
            return output
        return result

    setattr(assert_full_data_parity, _MARKER, True)
    setattr(assert_full_data_parity, "_nico_previous", current)
    finish.assert_full_data_parity = assert_full_data_parity
    return {
        "status": "installed",
        "version": VERSION,
        "stable_stage_ids_required": True,
        "localized_spanish_worksheet_titles_required": True,
        "missing_worksheets_not_synthesized": True,
        "all_non_worksheet_full_data_checks_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "WORKSHEET_TITLES_BY_STAGE_ID",
    "install_comprehensive_full_data_worksheet_localization_v1",
]
