from __future__ import annotations

import html
import re
from functools import wraps
from typing import Any, Callable

from nico.express_section_status_truth_v26 import reconcile_section_status_truth

VERSION = "nico.express_score_assurance_export.v1.1"
_PATCH_MARKER = "_nico_express_score_assurance_export_v1"
_MARKDOWN_START = "<!-- NICO_SCORE_ASSURANCE_START -->"
_MARKDOWN_END = "<!-- NICO_SCORE_ASSURANCE_END -->"
_HTML_START = "<!-- NICO_SCORE_ASSURANCE_HTML_START -->"
_HTML_END = "<!-- NICO_SCORE_ASSURANCE_HTML_END -->"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _records(result: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score_value = section.get("score_value")
        score_label = "NOT SCORED" if score_value is None else f"{int(score_value)}/100"
        output.append(
            {
                "section_id": _text(section.get("id")),
                "label": _text(section.get("label") or section.get("title") or section.get("id")),
                "technical_score": score_value,
                "technical_score_label": score_label,
                "technical_band": _text(section.get("score_band") or "not_scored"),
                "technical_band_label": _text(section.get("score_band_label") or "NOT SCORED"),
                "score_tone": _text(section.get("score_tone") or "gray"),
                "assurance_status": _text(section.get("assurance_status") or "unverified"),
                "assurance_label": _text(section.get("assurance_label") or "UNVERIFIED"),
                "assurance_tone": _text(section.get("assurance_tone") or "gray"),
                "canonical_status": _text(section.get("status") or "unknown").upper(),
                "directly_scored": section.get("directly_scored") is not False and score_value is not None,
            }
        )
    return output


def _replace_bounded(document: str, start: str, end: str, replacement: str) -> str:
    pattern = re.compile(re.escape(start) + r"[\s\S]*?" + re.escape(end), re.I)
    if pattern.search(document):
        return pattern.sub(replacement, document, count=1)
    separator = "\n\n" if document.strip() else ""
    return document.rstrip() + separator + replacement + "\n"


def _replace_html_bounded(document: str, replacement: str) -> str:
    pattern = re.compile(re.escape(_HTML_START) + r"[\s\S]*?" + re.escape(_HTML_END), re.I)
    if pattern.search(document):
        return pattern.sub(replacement, document, count=1)
    closing_body = re.search(r"</body\s*>", document, re.I)
    if closing_body:
        return document[: closing_body.start()] + replacement + document[closing_body.start() :]
    return document.rstrip() + replacement


def _markdown(records: list[dict[str, Any]]) -> str:
    rows = [
        _MARKDOWN_START,
        "## Technical Score and Assurance",
        "Technical health and evidence assurance are independent dimensions. A strong score can remain review-limited until open evidence is resolved. Client delivery remains a separate human-approval decision.",
        "",
        "| Control | Technical score | Technical band | Assurance | Canonical status | Treatment |",
        "|---|---:|---|---|---|---|",
    ]
    for item in records:
        treatment = "Scored" if item["directly_scored"] else "Supplemental / review control"
        rows.append(
            "| {label} | {score} | {band} | {assurance} | {status} | {treatment} |".format(
                label=item["label"].replace("|", "\\|"),
                score=item["technical_score_label"],
                band=item["technical_band_label"],
                assurance=item["assurance_label"],
                status=item["canonical_status"],
                treatment=treatment,
            )
        )
    rows.extend(
        [
            "",
            "**Delivery status:** Human review required; client delivery is blocked until an authorized reviewer approves the exact report and evidence snapshot.",
            _MARKDOWN_END,
        ]
    )
    return "\n".join(rows)


def _html(records: list[dict[str, Any]]) -> str:
    rows = []
    for item in records:
        treatment = "Scored" if item["directly_scored"] else "Supplemental / review control"
        rows.append(
            "<tr>"
            f"<td>{html.escape(item['label'])}</td>"
            f"<td>{html.escape(item['technical_score_label'])}</td>"
            f"<td>{html.escape(item['technical_band_label'])}</td>"
            f"<td>{html.escape(item['assurance_label'])}</td>"
            f"<td>{html.escape(item['canonical_status'])}</td>"
            f"<td>{html.escape(treatment)}</td>"
            "</tr>"
        )
    return (
        f"{_HTML_START}"
        '<section id="nico-score-assurance" data-nico-score-assurance="separate">'
        "<h2>Technical Score and Assurance</h2>"
        "<p>Technical health and evidence assurance are independent dimensions. A strong score can remain review-limited until open evidence is resolved. Client delivery remains a separate human-approval decision.</p>"
        '<table><thead><tr><th>Control</th><th>Technical score</th><th>Technical band</th><th>Assurance</th><th>Canonical status</th><th>Treatment</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<p><strong>Delivery status:</strong> Human review required; client delivery is blocked until an authorized reviewer approves the exact report and evidence snapshot.</p>"
        "</section>"
        f"{_HTML_END}"
    )


def _apply_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    existing_reports = result.get("reports")
    result.clear()
    result.update(normalized)
    if isinstance(existing_reports, dict) and isinstance(result.get("reports"), dict):
        replacement_reports = result["reports"]
        existing_reports.clear()
        existing_reports.update(replacement_reports)
        result["reports"] = existing_reports


def publish_score_assurance_exports(result: dict[str, Any]) -> dict[str, Any]:
    normalized = reconcile_section_status_truth(result)
    _apply_in_place(result, normalized)
    records = _records(result)
    reports = result.get("reports")
    if isinstance(reports, dict):
        markdown = reports.get("markdown")
        if isinstance(markdown, str):
            reports["markdown"] = _replace_bounded(markdown, _MARKDOWN_START, _MARKDOWN_END, _markdown(records))
        html_document = reports.get("html")
        if isinstance(html_document, str):
            reports["html"] = _replace_html_bounded(html_document, _html(records))
    result["score_assurance_export"] = {
        "status": "complete",
        "version": VERSION,
        "records": records,
        "record_count": len(records),
        "score_and_assurance_are_independent": True,
        "markdown_published": isinstance(reports, dict) and isinstance(reports.get("markdown"), str),
        "html_published": isinstance(reports, dict) and isinstance(reports.get("html"), str),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


def install_express_score_assurance_export_v1() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        publish_score_assurance_exports(result)
        pdf, error = current(result)
        publish_score_assurance_exports(result)
        return pdf, error

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "markdown_html_json_separation": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_score_assurance_export_v1",
    "publish_score_assurance_exports",
]
