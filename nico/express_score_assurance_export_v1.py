from __future__ import annotations

import html
import re
from functools import wraps
from typing import Any, Callable

from nico.express_section_status_truth_v26 import reconcile_section_status_truth

VERSION = "nico.express_score_assurance_export.v2"
_PATCH_MARKER = "_nico_express_score_assurance_export_v1"
_MARKDOWN_START = "<!-- NICO_SCORE_ASSURANCE_START -->"
_MARKDOWN_END = "<!-- NICO_SCORE_ASSURANCE_END -->"
_HTML_START = "<!-- NICO_SCORE_ASSURANCE_HTML_START -->"
_HTML_END = "<!-- NICO_SCORE_ASSURANCE_HTML_END -->"
_CLIENT_ACCEPTANCE_IDS = {"client_acceptance", "client_human_acceptance"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]


def _normalize_not_scored_controls(result: dict[str, Any]) -> None:
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        if section_id not in _CLIENT_ACCEPTANCE_IDS or section.get("directly_scored") is not False:
            continue
        section["score"] = None
        section["presented_score"] = None
        section["presented"] = None
        section["score_value"] = None
        section["score_band"] = "not_scored"
        section["score_band_label"] = "NOT SCORED"
        section["score_tone"] = "gray"
        section["technical_score_display"] = "NOT SCORED"
        section["score_label"] = "NOT SCORED"


def _records(result: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score_value = section.get("score_value")
        score_label = "NOT SCORED" if score_value is None else f"{int(score_value)}/100"
        assurance_status = _text(section.get("assurance_status") or "unverified")
        assurance_label = _text(section.get("assurance_label") or "UNVERIFIED")
        canonical_status = _text(section.get("status") or "unknown").upper()
        directly_scored = section.get("directly_scored") is not False and score_value is not None
        technically_green = bool(directly_scored and int(score_value) >= 80)
        verified_assurance = assurance_status.casefold() == "verified" and canonical_status == "GREEN"
        output.append(
            {
                "section_id": _text(section.get("id")),
                "label": _text(section.get("label") or section.get("title") or section.get("id")),
                "technical_score": score_value,
                "technical_score_label": score_label,
                "technical_band": _text(section.get("score_band") or "not_scored"),
                "technical_band_label": _text(section.get("score_band_label") or "NOT SCORED"),
                "score_tone": _text(section.get("score_tone") or "gray"),
                "assurance_status": assurance_status,
                "assurance_label": assurance_label,
                "assurance_tone": _text(section.get("assurance_tone") or "gray"),
                "canonical_status": canonical_status,
                "directly_scored": directly_scored,
                "findings": _items(section.get("findings")),
                "unavailable": _items(section.get("unavailable")),
                "score_rationale": _text(section.get("score_rationale") or section.get("status_reason")),
                "verified_green": technically_green and verified_assurance,
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


def _markdown_heading(item: dict[str, Any]) -> str:
    return (
        f"### {item['label']} — {item['technical_band_label']} "
        f"({item['technical_score_label']})\n"
        f"**Evidence assurance:** {item['assurance_label']} · "
        f"**Risk disposition:** {item['canonical_status']}"
    )


def _rewrite_markdown_section_headings(document: str, records: list[dict[str, Any]]) -> str:
    """Replace legacy status-colored score headings with independent truth fields.

    Earlier reports emitted headings such as ``YELLOW (89/100)``. That incorrectly
    colored a strong technical score with an evidence-assurance state. The canonical
    status is preserved explicitly on the next line and is never weakened.
    """

    output = document
    for item in records:
        if not item["label"]:
            continue
        label = re.escape(item["label"])
        pattern = re.compile(
            rf"(?m)^###\s+{label}\s+(?:—|-)\s+[^\n(]+\s*"
            rf"\((?:\d{{1,3}}\s*/\s*100|NOT\s+SCORED)\)\s*"
            rf"(?:\n\*\*Evidence assurance:\*\*[^\n]*)?"
        )
        output = pattern.sub(_markdown_heading(item), output, count=1)
    return output


def _rewrite_html_section_headings(document: str, records: list[dict[str, Any]]) -> str:
    output = document
    for item in records:
        label = item["label"]
        if not label:
            continue
        escaped_label = html.escape(label)
        pattern = re.compile(
            rf"<h3(?P<attrs>[^>]*)>\s*{re.escape(escaped_label)}\s*"
            rf"(?:—|&mdash;|&#8212;|-)\s*[^<(]+\s*"
            rf"\((?:\d{{1,3}}\s*/\s*100|NOT\s+SCORED)\)\s*</h3>"
            rf"(?:\s*<p[^>]*data-nico-section-assurance=[\"'][^\"']*[\"'][^>]*>[\s\S]*?</p>)?",
            re.I,
        )
        replacement = (
            f"<h3>{escaped_label} — {html.escape(item['technical_band_label'])} "
            f"({html.escape(item['technical_score_label'])})</h3>"
            f'<p data-nico-section-assurance="{html.escape(item["section_id"])}">'
            f"<strong>Evidence assurance:</strong> {html.escape(item['assurance_label'])} · "
            f"<strong>Risk disposition:</strong> {html.escape(item['canonical_status'])}</p>"
        )
        output = pattern.sub(replacement, output, count=1)
    return output


def _green_requirements(item: dict[str, Any]) -> list[str]:
    if not item["directly_scored"]:
        return ["This control is intentionally not scored; complete its review or approval workflow instead of manufacturing a technical score."]
    if item["verified_green"]:
        return ["Already verified green. Preserve the exact-run evidence and rerun after material changes."]

    requirements: list[str] = []
    score = item.get("technical_score")
    if isinstance(score, (int, float)) and score < 80:
        requirements.append(
            "Raise the evidence-backed technical score to at least 80 through verified remediation; the green threshold must not be lowered."
        )
    if item["assurance_status"].casefold() != "verified" or item["canonical_status"] != "GREEN":
        if item["unavailable"]:
            requirements.append("Complete or formally disposition unavailable evidence: " + "; ".join(item["unavailable"][:2]))
        if item["findings"]:
            requirements.append("Triage, repair, or explicitly accept retained findings: " + "; ".join(item["findings"][:2]))
        if not item["unavailable"] and not item["findings"]:
            requirements.append("Resolve every review-limited, failed, timed-out, unavailable, or untriaged evidence state and retain the clean rerun artifact.")
    if item["score_rationale"]:
        requirements.append("Close the retained score constraint: " + item["score_rationale"])
    return requirements or ["Rerun the exact immutable snapshot and retain verified evidence before changing the presentation state."]


def _markdown(records: list[dict[str, Any]]) -> str:
    rows = [
        _MARKDOWN_START,
        "## Technical Score and Assurance",
        "Technical health and evidence assurance are independent dimensions. A strong score can remain review-limited until open evidence is resolved. Client delivery remains a separate human-approval decision.",
        "",
        "| Control | Technical score | Technical band | Assurance | Risk disposition | Treatment |",
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
            "## Verified Green Readiness",
            "A control is green only when its technical score is at least 80 and its retained evidence assurance is VERIFIED. Pending human delivery approval remains separate.",
            "",
            "| Control | Current state | Evidence required for accurate green |",
            "|---|---|---|",
        ]
    )
    for item in records:
        current = f"{item['technical_band_label']} {item['technical_score_label']} · {item['assurance_label']}"
        requirements = " ".join(_green_requirements(item)).replace("|", "\\|")
        label = item["label"].replace("|", "\\|")
        rows.append(f"| {label} | {current} | {requirements} |")

    rows.extend(
        [
            "",
            "**Delivery status:** Human review required; client delivery is blocked until an authorized reviewer approves the exact report and evidence snapshot.",
            _MARKDOWN_END,
        ]
    )
    return "\n".join(rows)


def _html(records: list[dict[str, Any]]) -> str:
    score_rows = []
    readiness_rows = []
    for item in records:
        treatment = "Scored" if item["directly_scored"] else "Supplemental / review control"
        score_rows.append(
            "<tr>"
            f"<td>{html.escape(item['label'])}</td>"
            f"<td>{html.escape(item['technical_score_label'])}</td>"
            f"<td>{html.escape(item['technical_band_label'])}</td>"
            f"<td>{html.escape(item['assurance_label'])}</td>"
            f"<td>{html.escape(item['canonical_status'])}</td>"
            f"<td>{html.escape(treatment)}</td>"
            "</tr>"
        )
        current = f"{item['technical_band_label']} {item['technical_score_label']} · {item['assurance_label']}"
        requirements = " ".join(_green_requirements(item))
        readiness_rows.append(
            "<tr>"
            f"<td>{html.escape(item['label'])}</td>"
            f"<td>{html.escape(current)}</td>"
            f"<td>{html.escape(requirements)}</td>"
            "</tr>"
        )
    return (
        f"{_HTML_START}"
        '<section id="nico-score-assurance" data-nico-score-assurance="separate">'
        "<h2>Technical Score and Assurance</h2>"
        "<p>Technical health and evidence assurance are independent dimensions. A strong score can remain review-limited until open evidence is resolved. Client delivery remains a separate human-approval decision.</p>"
        '<table><thead><tr><th>Control</th><th>Technical score</th><th>Technical band</th><th>Assurance</th><th>Risk disposition</th><th>Treatment</th></tr></thead>'
        f"<tbody>{''.join(score_rows)}</tbody></table>"
        "<h2>Verified Green Readiness</h2>"
        "<p>A control is green only when its technical score is at least 80 and its retained evidence assurance is VERIFIED. Pending human delivery approval remains separate.</p>"
        '<table><thead><tr><th>Control</th><th>Current state</th><th>Evidence required for accurate green</th></tr></thead>'
        f"<tbody>{''.join(readiness_rows)}</tbody></table>"
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
    _normalize_not_scored_controls(result)
    records = _records(result)
    reports = result.get("reports")
    if isinstance(reports, dict):
        markdown = reports.get("markdown")
        if isinstance(markdown, str):
            markdown = _rewrite_markdown_section_headings(markdown, records)
            reports["markdown"] = _replace_bounded(markdown, _MARKDOWN_START, _MARKDOWN_END, _markdown(records))
        html_document = reports.get("html")
        if isinstance(html_document, str):
            html_document = _rewrite_html_section_headings(html_document, records)
            reports["html"] = _replace_html_bounded(html_document, _html(records))

    verified_green = [item["section_id"] for item in records if item["verified_green"]]
    green_blockers = {
        item["section_id"]: _green_requirements(item)
        for item in records
        if not item["verified_green"]
    }
    result["score_assurance_export"] = {
        "status": "complete",
        "version": VERSION,
        "records": records,
        "record_count": len(records),
        "score_and_assurance_are_independent": True,
        "legacy_status_colored_headings_rewritten": True,
        "verified_green_requires_score_and_assurance": True,
        "verified_green_controls": verified_green,
        "green_blockers": green_blockers,
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
        "verified_green_requires_score_and_assurance": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_score_assurance_export_v1",
    "publish_score_assurance_exports",
]
