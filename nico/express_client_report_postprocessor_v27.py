from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_client_report_postprocessor.v27"
_MARKER = "_nico_express_client_report_postprocessor_v27"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _text(section.get("id")).casefold()
    if section_id == "scanner_worker_evidence":
        return True
    if section_id in {"client_acceptance", "client_human_acceptance"}:
        return _text(section.get("status")).casefold() != "green"
    return section.get("score") is None and section.get("directly_scored") is False


def _priority_items(result: dict[str, Any], limit: int = 5) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict) or _not_scored(section):
            continue
        label = _text(section.get("label") or section.get("title") or section.get("id"))
        status = _text(section.get("status")).casefold()
        score = section.get("score")
        for item in section.get("findings") or []:
            finding = _text(item)
            if not finding:
                continue
            severity = 3 if status == "red" else 2 if status == "yellow" else 1
            if isinstance(score, (int, float)) and score < 80:
                severity += 1
            ranked.append((severity, f"**{label}:** {finding}"))
    seen: set[str] = set()
    output: list[str] = []
    for _, item in sorted(ranked, key=lambda pair: pair[0], reverse=True):
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _replace_section(markdown: str, heading: str, body_lines: list[str]) -> str:
    replacement = f"## {heading}\n" + "\n".join(f"- {line}" for line in body_lines) + "\n"
    pattern = rf"## {re.escape(heading)}\n[\s\S]*?(?=\n## |\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, replacement.rstrip(), markdown)
    return markdown.rstrip() + "\n\n" + replacement


def _rewrite_not_scored(markdown: str, result: dict[str, Any]) -> str:
    output = markdown
    for section in result.get("sections") or []:
        if not isinstance(section, dict) or not _not_scored(section):
            continue
        label = _text(section.get("label") or section.get("title"))
        status = _text(section.get("status") or "gray").upper()
        output = re.sub(
            rf"(###\s+{re.escape(label)}\s+—\s+)[A-Z]+\s*\((?:None|0|\d+)/100\)",
            rf"\1{status} (NOT SCORED)",
            output,
            flags=re.I,
        )
        output = re.sub(
            rf"(-\s+\*\*{re.escape(label)}\*\*:\s*)[^\n]+",
            rf"\1{status.casefold()} · not scored",
            output,
            flags=re.I,
        )
    return output


def postprocess_express_client_reports(result: dict[str, Any]) -> dict[str, Any]:
    reports = result.get("reports")
    if not isinstance(reports, dict):
        return result
    markdown = reports.get("markdown")
    if isinstance(markdown, str):
        markdown = _rewrite_not_scored(markdown, result)
        priorities = _priority_items(result)
        if priorities:
            markdown = _replace_section(markdown, "Priority Actions", priorities)
        quick_wins = priorities[:3] or ["No evidence-backed quick win was identified in this run; retain human review before delivery."]
        markdown = _replace_section(markdown, "Quick Wins", quick_wins)
        plan = [
            "Resolve every current-run failed, timed-out, unavailable, or triage-required analyzer before asserting clean coverage.",
            "Decompose the highest verified complexity hotspots and add focused regression tests around changed behavior.",
            "Re-run the assessment against the same immutable commit and compare evidence fingerprints before closure.",
        ]
        markdown = _replace_section(markdown, "Medium-Term Plan", plan)
        checklist = [
            "[ ] Exact repository commit SHA is recorded and matches the scanner snapshot.",
            "[ ] Every scored section has evidence or an explicit access limitation.",
            "[ ] Failed, timed-out, unavailable, and triage-required analyzers are not presented as GREEN.",
            "[ ] PDF, Markdown, HTML, and JSON present the same statuses and scores.",
            "[ ] Authorized human reviewer approves the exact-snapshot report before client delivery.",
        ]
        markdown = _replace_section(markdown, "Verification Checklist", checklist)
        reports["markdown"] = markdown
    html = reports.get("html")
    if isinstance(html, str):
        for section in result.get("sections") or []:
            if not isinstance(section, dict) or not _not_scored(section):
                continue
            label = _text(section.get("label") or section.get("title"))
            status = _text(section.get("status") or "gray").upper()
            html = re.sub(
                rf"({re.escape(label)}\s*[—-]\s*)[A-Z]+\s*\((?:None|0|\d+)/100\)",
                rf"\1{status} (NOT SCORED)",
                html,
                flags=re.I,
            )
        reports["html"] = html
    result["express_client_report_postprocessor"] = {
        "status": "complete",
        "version": VERSION,
        "not_scored_numeric_leakage_removed": True,
        "priority_actions_evidence_derived": True,
        "generic_quick_wins_replaced": True,
        "verification_checklist_replaced": True,
        "human_review_required": True,
    }
    return result


def install_express_client_report_postprocessor_v27() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        payload = current(result)
        postprocess_express_client_reports(result)
        return payload

    setattr(render, _MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {"status": "installed", "version": VERSION, "post_generation_bound": True}


__all__ = ["VERSION", "install_express_client_report_postprocessor_v27", "postprocess_express_client_reports"]
