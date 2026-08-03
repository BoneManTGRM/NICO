from __future__ import annotations

import html as html_lib
from pathlib import Path
from typing import Any, Callable

VERSION = "nico.comprehensive-live-report-contract.v2"

_EN_EVIDENCE_SUMMARIES = (
    "Evidence Package Summary",
    "Client Evidence Summary",
)
_ES_EVIDENCE_SUMMARIES = (
    "Resumen del paquete de evidencia",
    "Resumen de evidencia para revisión",
    "Resumen de evidencia para revision",
)
_REQUIRED_SECTIONS = (
    "NICO Comprehensive Technical Assessment",
    "Functional QA",
    "Platform Parity",
    "Six-Month Roadmap",
    "Staffing, Sequencing, and Cost",
    "Human Review and Acceptance Gate",
)
_CANONICAL_INCOMPLETE_ANALYZER_LABEL = "Incomplete applicable analyzers:"
_RETIRED_EVIDENCE_APPENDIX_HEADINGS = (
    "Evidence Appendix",
    "Apéndice de evidencia",
    "Apendice de evidencia",
)
_STALE_DRAFT_PHRASES = (
    "DRAFT ONLY",
    "DRAFT - HUMAN REVIEW REQUIRED",
    "DRAFT · HUMAN REVIEW REQUIRED",
    "COMPLETE ONLY AS A DRAFT",
)
_FORBIDDEN_FINALITY = (
    "FINAL REPORT",
    "INFORME FINAL",
    "AUTOMATED FINAL",
    "APPROVED FINAL",
    "FINAL APROBADO",
    "CLIENT DELIVERY AUTHORIZED",
    "ENTREGA AL CLIENTE AUTORIZADA",
)


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    normalized = str(value or "").casefold()
    return any(marker.casefold() in normalized for marker in markers)


def _assert_marker(value: str, marker: str, *, surface: str) -> None:
    escaped = html_lib.escape(marker)
    assert marker in value or escaped in value, f"Comprehensive {surface} omitted {marker}"


def _retired_heading_present(value: str) -> bool:
    retired = {marker.casefold() for marker in _RETIRED_EVIDENCE_APPENDIX_HEADINGS}
    for raw in str(value or "").splitlines():
        normalized = " ".join(raw.lstrip("# ").split()).strip().casefold()
        if normalized in retired:
            return True
    return False


def validate_report(
    acceptance: Any,
    service: str,
    payload: dict[str, Any],
    destination: Path,
    *,
    fallback: Callable[[str, dict[str, Any], Path], dict[str, Any]],
) -> dict[str, Any]:
    """Validate the current compact review package without reviving retired FINAL contracts."""

    if service != "comprehensive":
        return dict(fallback(service, payload, destination))

    package = acceptance.report_package(service, payload)
    assessment = acceptance.assessment_payload(service, payload)
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    encoded_pdf = str(package.get("pdf_base64") or "")

    # Existing semantic-unit fixtures intentionally supply only canonical JSON and
    # text aliases while mocking the historical validator. Keep those tests on the
    # delegated seam. A real Comprehensive package identifies itself explicitly
    # and remains fail-closed on any missing artifact below.
    if package.get("service_id") != "comprehensive":
        return dict(fallback(service, payload, destination))

    assert markdown.strip(), "comprehensive Markdown report is missing"
    assert rendered_html.strip().lower().startswith("<!doctype html"), (
        "comprehensive HTML report is invalid"
    )
    assert encoded_pdf, "comprehensive PDF report is missing"
    assert "NONE/100" not in markdown.upper()
    assert "NULL/100" not in markdown.upper()

    pdf = acceptance.pdf_evidence(encoded_pdf, destination)
    pdf_text = str(pdf.get("text") or "")
    assert "NICO MID TECHNICAL" not in markdown.upper()
    assert "NICO MID TECHNICAL" not in pdf_text.upper()

    for marker in _REQUIRED_SECTIONS:
        _assert_marker(markdown, marker, surface="Markdown")
        _assert_marker(rendered_html, marker, surface="HTML")
        _assert_marker(pdf_text, marker, surface="PDF")

    evidence_markers = _EN_EVIDENCE_SUMMARIES + _ES_EVIDENCE_SUMMARIES
    assert _contains_any(markdown, evidence_markers), (
        "Comprehensive Markdown omitted the compact evidence summary"
    )
    assert _contains_any(rendered_html, evidence_markers), (
        "Comprehensive HTML omitted the compact evidence summary"
    )
    assert _contains_any(pdf_text, evidence_markers), (
        "Comprehensive PDF omitted the compact evidence summary"
    )

    surfaces = {
        "Markdown": markdown,
        "HTML": rendered_html,
        "PDF": pdf_text,
    }
    for surface, raw_value in surfaces.items():
        value = raw_value.upper()
        for forbidden in _FORBIDDEN_FINALITY:
            assert forbidden not in value, (
                f"Comprehensive {surface} retained unapproved finality: {forbidden}"
            )
        for stale in _STALE_DRAFT_PHRASES:
            assert stale not in value, (
                f"Comprehensive {surface} retained stale status: {stale}"
            )
        assert _contains_any(value, ("AUTOMATED DRAFT", "BORRADOR AUTOMATIZADO")), (
            f"Comprehensive {surface} omitted automated-draft lifecycle truth"
        )
        assert _contains_any(value, ("PENDING HUMAN APPROVAL", "APROBACIÓN HUMANA PENDIENTE")), (
            f"Comprehensive {surface} omitted pending-human-approval status"
        )
        assert _contains_any(value, ("CLIENT DELIVERY BLOCKED", "ENTREGA AL CLIENTE BLOQUEADA")), (
            f"Comprehensive {surface} omitted blocked-delivery status"
        )
        assert _CANONICAL_INCOMPLETE_ANALYZER_LABEL in raw_value, (
            f"Comprehensive {surface} omitted the canonical incomplete analyzer count"
        )
        assert not _retired_heading_present(raw_value), (
            f"Comprehensive {surface} restored the retired raw Evidence Appendix"
        )

    assert acceptance.first_bool(payload, "human_review_required") is True, (
        "Comprehensive package omitted mandatory human-review truth"
    )
    assert acceptance.first_bool(payload, "client_delivery_allowed") is not True, (
        "Comprehensive package allowed client delivery before approval"
    )
    assert assessment.get("client_delivery_allowed") is not True, (
        "Comprehensive assessment allowed client delivery before approval"
    )
    assert "\x7f" not in pdf_text, "Comprehensive PDF contains a control-character glyph"

    maturity = acceptance.dict_value(assessment.get("maturity_signal"))
    score = maturity.get("presented_score", maturity.get("score"))
    score_label = (
        f"{int(score)}/100"
        if isinstance(score, (int, float)) and not isinstance(score, bool)
        else "NOT SCORED"
    )
    assert score_label in markdown
    assert score_label in rendered_html
    assert score_label in pdf_text
    section_evidence = acceptance.section_parity(
        assessment,
        markdown,
        rendered_html,
        pdf_text,
    )

    truth_values = {
        acceptance.text(value, 128)
        for value in (
            package.get("canonical_truth_sha256"),
            acceptance.dict_value(package.get("json")).get("canonical_truth_sha256"),
            payload.get("canonical_truth_sha256"),
        )
        if acceptance.text(value, 128)
    }
    if len(truth_values) > 1:
        raise AssertionError(f"canonical truth hash drift: {sorted(truth_values)}")

    return {
        "report_id": acceptance.first_text(
            package.get("report_id"),
            payload.get("report_id"),
        ),
        "score": score_label,
        "maturity_level": acceptance.first_text(maturity.get("level")),
        "section_parity": section_evidence,
        "canonical_truth_sha256": next(iter(truth_values), ""),
        "pdf": {key: value for key, value in pdf.items() if key != "text"},
        "semantic_contract": {
            "status": "passed",
            "page_count_informational_only": True,
            "required_sections_verified": True,
            "compact_evidence_summary_verified": True,
            "canonical_incomplete_analyzer_count_verified": True,
            "retired_evidence_appendix_absent": True,
            "automated_draft_language_verified": True,
            "unapproved_finality_absent": True,
            "stale_draft_language_absent": True,
            "control_characters_absent": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "markdown_sha256": acceptance.sha256(markdown.encode("utf-8")),
        "html_sha256": acceptance.sha256(rendered_html.encode("utf-8")),
    }


__all__ = ["VERSION", "validate_report"]
