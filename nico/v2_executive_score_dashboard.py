from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from typing import Any, Mapping

from nico.v2_authoritative_premium_report import _html_from_markdown, _pdf_from_markdown

VERSION = "nico.v2.executive-score-dashboard.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def _scores(canonical: Mapping[str, Any]) -> tuple[int | None, int | None]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    technical = next((score for raw in (
        truth.get("technical_score"),
        assessment.get("technical_score"),
        maturity.get("technical_score"),
        maturity.get("presented_score"),
        maturity.get("score"),
    ) if (score := _numeric(raw)) is not None), None)
    adjusted = next((score for raw in (
        truth.get("canonical_evidence_adjusted_score"),
        assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"),
        technical,
    ) if (score := _numeric(raw)) is not None), None)
    return technical, adjusted


def _dashboard(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    technical, adjusted = _scores(canonical)
    technical_label = f"{technical}/100" if technical is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
    adjusted_label = f"{adjusted}/100" if adjusted is not None else ("SIN PUNTUACIÓN" if spanish else "NOT SCORED")
    if spanish:
        return (
            "## Panel ejecutivo de puntuación\n\n"
            f"- Madurez técnica: {technical_label}\n"
            f"- Ajuste por evidencia: {adjusted_label}\n"
            "- Estado del paquete: Completo, pendiente de aprobación humana\n"
            "- Entrega al cliente: Bloqueada hasta aprobación\n"
        )
    return (
        "## Executive Score Dashboard\n\n"
        f"- Technical maturity: {technical_label}\n"
        f"- Evidence-Adjusted: {adjusted_label}\n"
        "- Assessment package: Complete, pending human approval\n"
        "- Client delivery: Blocked until approval\n"
    )


def apply_executive_score_dashboard(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    language = _text(canonical.get("report_language") or canonical.get("locale")).casefold()
    spanish = language.startswith("es")
    markdown = str(result.get("markdown") or "").strip()
    dashboard = _dashboard(canonical, spanish=spanish).strip()

    # Replace any prior dashboard instance and place the integrated dashboard
    # immediately before the executive decision brief. This preserves the old
    # report's executive visual hierarchy without reviving the removed plain
    # Canonical Score Summary page.
    headings = ("## Executive Score Dashboard", "## Panel ejecutivo de puntuación")
    for heading in headings:
        start = markdown.find(heading)
        if start >= 0:
            next_heading = markdown.find("\n## ", start + len(heading))
            markdown = (markdown[:start] + (markdown[next_heading + 1 :] if next_heading >= 0 else "")).strip()

    markers = ("## Executive Decision Brief", "## Resumen ejecutivo")
    marker = next((value for value in markers if value in markdown), "")
    if marker:
        markdown = markdown.replace(marker, dashboard + "\n\n" + marker, 1)
    else:
        lines = markdown.splitlines()
        insert_at = 3 if len(lines) >= 3 else len(lines)
        lines[insert_at:insert_at] = ["", dashboard, ""]
        markdown = "\n".join(lines)
    markdown = markdown.strip() + "\n"

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    title = "Evaluación Técnica Integral NICO" if spanish else f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    rendered_html = _html_from_markdown(markdown, title, spanish=spanish)
    pdf, page_count = _pdf_from_markdown(markdown, canonical, spanish=spanish)
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({
        "executive_score_dashboard": True,
        "executive_score_dashboard_version": VERSION,
        "canonical_score_labels_in_markdown_html_pdf": True,
        "plain_canonical_score_page_removed": True,
        "page_count": page_count,
    })
    result.update({
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
        "premium_report_renderer": contract,
    })
    return result


__all__ = ["VERSION", "apply_executive_score_dashboard"]
