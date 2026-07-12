from __future__ import annotations

import html
import math
import re
from copy import deepcopy
from typing import Any

import nico.mid_assessment_report as report


MID_REPORT_PRESENTATION_VERSION = "mid-report-presentation-v1"
_ORIGINAL_SECTION_PAYLOAD = report._section_payload
_ORIGINAL_HTML = report._html


def _text_key(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return text.rstrip(" .;:")


def _unique_text(values: Any, seen: set[str] | None = None) -> list[str]:
    output: list[str] = []
    used = seen if seen is not None else set()
    for item in values if isinstance(values, list) else []:
        text = str(item or "").strip()
        key = _text_key(text)
        if not key or key in used:
            continue
        used.add(key)
        output.append(text)
    return output


def _score_label(value: Any) -> str:
    if isinstance(value, bool):
        return "NOT SCORED"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "NOT SCORED"
    if not math.isfinite(number):
        return "NOT SCORED"
    rendered = str(int(number)) if number.is_integer() else f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{rendered}/100"


def normalized_section_payload(section: dict[str, Any]) -> dict[str, Any]:
    """Normalize one report section without changing its truth or evidence meaning."""

    payload = deepcopy(_ORIGINAL_SECTION_PAYLOAD(section))
    score_label = _score_label(payload.get("score"))
    if score_label == "NOT SCORED":
        payload["score"] = None
    payload["score_label"] = score_label

    evidence_seen: set[str] = set()
    payload["evidence"] = _unique_text(payload.get("evidence"), evidence_seen)
    payload["findings"] = _unique_text(payload.get("findings"))

    limitation_seen = {_text_key(payload.get("summary"))}
    limitation_seen.update(_text_key(item) for item in payload["evidence"])
    payload["unavailable"] = _unique_text(payload.get("unavailable"), limitation_seen)
    payload["missing_evidence_sources"] = _unique_text(payload.get("missing_evidence_sources"), limitation_seen)
    payload["failed_evidence_tools"] = _unique_text(payload.get("failed_evidence_tools"), limitation_seen)
    payload["presentation_version"] = MID_REPORT_PRESENTATION_VERSION
    return payload


def _presentation_limitations(section: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in section.get("unavailable") or []:
        output.extend(_unique_text([item], seen))
    for item in section.get("missing_evidence_sources") or []:
        text = str(item or "").strip()
        if text and not text.lower().startswith(("missing ", "unavailable")):
            text = f"Missing source: {text}"
        output.extend(_unique_text([text], seen))
    for item in section.get("failed_evidence_tools") or []:
        text = str(item or "").strip()
        if text and not text.lower().startswith("failed tool"):
            text = f"Failed tool: {text}"
        output.extend(_unique_text([text], seen))
    return output


def collapsible_mid_report_html(payload: dict[str, Any]) -> str:
    """Render mobile-readable Mid HTML with truthful score labels and collapsed detail."""

    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    section_html: list[str] = []
    for raw in payload.get("sections") or []:
        section = normalized_section_payload(raw) if isinstance(raw, dict) else {}
        evidence = section.get("evidence") or []
        limitations = _presentation_limitations(section)
        evidence_html = "".join(f"<li>{esc(item)}</li>" for item in evidence)
        limitation_html = "".join(f"<li>{esc(item)}</li>" for item in limitations)
        details = ""
        if evidence_html:
            details += f"<details><summary>Evidence ({len(evidence)})</summary><ul>{evidence_html}</ul></details>"
        if limitation_html:
            details += f"<details><summary>Limitations and missing evidence ({len(limitations)})</summary><ul>{limitation_html}</ul></details>"
        section_html.append(
            "<section class=\"assessment-section\">"
            f"<div class=\"section-heading\"><h2>{esc(section.get('label'))}</h2>"
            f"<span class=\"score-label\">{esc(section.get('score_label'))}</span></div>"
            f"<p class=\"truth-status\"><b>Truth status:</b> {esc(section.get('truth_status'))}</p>"
            f"<p>{esc(section.get('summary'))}</p>{details}</section>"
        )

    exception_parts: list[str] = []
    for item in payload.get("review_packet", {}).get("exceptions", []):
        if not isinstance(item, dict):
            continue
        title = item.get("title") or item.get("category") or "Review item"
        exception_parts.append(
            f"<details><summary>{esc(title)} · {esc(item.get('severity') or 'medium')}</summary>"
            f"<p>{esc(item.get('reason') or 'Human review required.')}</p></details>"
        )
    exception_html = "".join(exception_parts) or "<p>No review exceptions were generated; human approval is still required.</p>"
    disclosures = "".join(f"<li>{esc(item)}</li>" for item in payload.get("disclosures") or [])
    coverage = payload.get("evidence_coverage") or {}

    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>NICO Mid Assessment</title><style>
body{{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#17202a;line-height:1.5}}h1,h2{{color:#101820}}.draft{{padding:12px;border:2px solid #a32121;background:#fff2f2;font-weight:bold}}.meta{{background:#f3f5f7;padding:14px;border-radius:10px}}.assessment-section{{border-top:1px solid #d9dee3;padding:18px 0}}.section-heading{{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}}.section-heading h2{{margin:0}}.score-label{{border:1px solid #667085;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:700;white-space:nowrap}}.truth-status{{margin-top:8px}}details{{border:1px solid #d9dee3;border-radius:10px;margin:10px 0;overflow:hidden}}summary{{cursor:pointer;font-weight:700;padding:11px 12px;background:#f8fafc}}details ul,details p{{margin:0;padding:12px 30px}}code{{word-break:break-all}}@media(max-width:600px){{body{{margin:18px auto;padding:0 14px}}.section-heading{{display:block}}.score-label{{display:inline-block;margin-top:8px}}details:not([open])>*:not(summary){{display:none}}}}
</style></head><body><h1>NICO MID ASSESSMENT</h1><p class=\"draft\">{esc(report.DRAFT_LABEL)}</p><div class=\"meta\"><p>Report ID: <code>{esc(payload.get('report_id'))}</code><br>Mid run: <code>{esc(payload.get('run_id'))}</code><br>Repository: <code>{esc(payload.get('repository'))}</code><br>Snapshot: <code>{esc(payload.get('snapshot_commit_sha'))}</code></p></div><h2>Automated evidence coverage</h2><p><b>{esc(coverage.get('percent'))}%</b> ({esc(coverage.get('numerator'))}/{esc(coverage.get('denominator'))})</p><p>{esc(coverage.get('method'))}</p>{''.join(section_html)}<section><h2>Review by exception</h2>{exception_html}</section><section><h2>Disclosures</h2><ul>{disclosures}</ul></section><section><h2>Integrity identity</h2><p>Source identity SHA-256: <code>{esc(payload.get('source_identity_sha256'))}</code><br>Review packet SHA-256: <code>{esc(payload.get('review_packet', {}).get('review_packet_sha256'))}</code></p></section></body></html>"""


def install_mid_report_presentation() -> dict[str, Any]:
    installed = bool(getattr(report, "_nico_mid_report_presentation_installed", False))
    report._section_payload = normalized_section_payload
    report._html = collapsible_mid_report_html
    report._nico_mid_report_presentation_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": MID_REPORT_PRESENTATION_VERSION,
        "rule": "Unscored sections render as NOT SCORED, repeated evidence is de-duplicated, and detailed HTML evidence remains collapsed until opened.",
    }


__all__ = [
    "MID_REPORT_PRESENTATION_VERSION",
    "collapsible_mid_report_html",
    "install_mid_report_presentation",
    "normalized_section_payload",
]
