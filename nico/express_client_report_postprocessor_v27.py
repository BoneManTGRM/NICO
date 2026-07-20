from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

from nico.service_catalog_v1 import apply_customer_service_identity

VERSION = "nico.express_client_report_postprocessor.v30"
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


def _scored_sections(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        section
        for section in result.get("sections") or []
        if isinstance(section, dict) and not _not_scored(section)
    ]


def _priority_items(result: dict[str, Any], limit: int = 6) -> list[str]:
    ranked: list[tuple[int, str]] = []
    for section in _scored_sections(result):
        label = _text(section.get("label") or section.get("title") or section.get("id"))
        status = _text(section.get("status")).casefold()
        score = section.get("score")
        for item in section.get("findings") or []:
            finding = _text(item)
            if not finding:
                continue
            severity = 5 if status == "red" else 3 if status == "yellow" else 1
            if isinstance(score, (int, float)) and score < 80:
                severity += 1
            if any(term in finding.casefold() for term in ("secret", "credential", "timeout", "failed", "unavailable")):
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


def _strengths(result: dict[str, Any], limit: int = 3) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for section in _scored_sections(result):
        if _text(section.get("status")).casefold() != "green":
            continue
        score = section.get("score")
        value = float(score) if isinstance(score, (int, float)) else 0.0
        label = _text(section.get("label") or section.get("title") or section.get("id"))
        summary = _text(section.get("summary"))
        ranked.append((value, f"{label} ({int(value)}/100): {summary}"))
    return [item for _, item in sorted(ranked, reverse=True)[:limit]]


def _executive_summary(result: dict[str, Any], priorities: list[str]) -> str:
    maturity = result.get("maturity_signal") or {}
    level = _text(maturity.get("level") or "Unclassified")
    score = maturity.get("score")
    scored = _scored_sections(result)
    yellow = [section for section in scored if _text(section.get("status")).casefold() == "yellow"]
    red = [section for section in scored if _text(section.get("status")).casefold() == "red"]
    strengths = _strengths(result)
    score_text = f"{score}/100" if isinstance(score, (int, float)) else "not calculated"
    posture = "not client-final" if red or yellow else "review-ready"
    sentences = [
        f"NICO assessed the exact authorized repository snapshot at a canonical {level} maturity level ({score_text}).",
        f"The technical posture is {posture}: {len(red)} red and {len(yellow)} yellow scored area(s) remain, while supplemental scanner output and unapproved client acceptance are excluded from maturity scoring.",
    ]
    if priorities:
        top = re.sub(r"\*\*", "", priorities[0])
        sentences.append(f"The highest-priority closure item is {top}")
    if strengths:
        sentences.append("The strongest verified areas are " + "; ".join(strengths) + ".")
    sentences.append("Client delivery remains blocked until an authorized human reviewer validates the same-snapshot evidence, resolves material analyzer exceptions, and approves the final report package.")
    return " ".join(sentences)


def _resourcing(result: dict[str, Any]) -> list[str]:
    sections = {str(section.get("id")): section for section in _scored_sections(result)}
    items = [
        "Engineering lead / architect: own the evidence-backed remediation sequence, approve architectural tradeoffs, and validate closure against the same repository snapshot.",
    ]
    if any(_text(sections.get(key, {}).get("status")).casefold() in {"yellow", "red"} for key in ("secrets_review", "dependency_health", "static_analysis")):
        items.append("Security-focused product engineer: triage scanner exceptions, verify suspected findings, repair confirmed issues, and produce clean rerun artifacts without suppressing evidence.")
    if "architecture_debt" in sections or "velocity_complexity" in sections:
        items.append("Senior product engineer: decompose the highest complexity/churn hotspots and add focused regression coverage around the changed behavior.")
    items.append("Product quality engineer: verify cross-format parity, exact-snapshot traceability, report readability, and final acceptance evidence before release.")
    return items


def _risk_register(result: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for section in _scored_sections(result):
        label = _text(section.get("label") or section.get("id"))
        status = _text(section.get("status")).casefold()
        if status not in {"yellow", "red"}:
            continue
        findings = [_text(value) for value in section.get("findings") or [] if _text(value)]
        unavailable = [_text(value) for value in section.get("unavailable") or [] if _text(value)]
        if findings:
            risks.append(f"{label}: {findings[0]} Mitigation: validate the underlying artifact, repair confirmed issues, and rerun on the same immutable commit.")
        elif unavailable:
            risks.append(f"{label}: {unavailable[0]} Mitigation: restore the missing evidence source before making a client-final claim.")
    risks.extend(
        [
            "Cross-format drift: Markdown, HTML, JSON, and PDF can diverge if generated from different truth states. Mitigation: bind all formats to one terminal contract and compare canonical status/score fingerprints.",
            "Approval risk: automated evidence can be technically correct but commercially incomplete. Mitigation: require an authorized reviewer to approve the exact-snapshot package before delivery.",
        ]
    )
    return risks[:6]


def _normalize_list_item(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^(?:-\s*)?(?:\[\s*[xX ]?\s*\]\s*)+", "", text)
    return text.strip()


def _replace_section(markdown: str, heading: str, body_lines: list[str]) -> str:
    checklist = heading.casefold() == "verification checklist"
    rendered: list[str] = []
    for value in body_lines:
        item = _normalize_list_item(value)
        if not item:
            continue
        rendered.append(f"- [ ] {item}" if checklist else f"- {item}")
    replacement = f"## {heading}\n" + "\n".join(rendered) + "\n"
    pattern = rf"## {re.escape(heading)}\n[\s\S]*?(?=\n## |\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, replacement.rstrip(), markdown)
    return markdown.rstrip() + "\n\n" + replacement


def _replace_paragraph_section(markdown: str, heading: str, paragraph: str) -> str:
    replacement = f"## {heading}\n{paragraph}\n"
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


def _merge_required_plan_items(existing: list[Any], generated: list[str]) -> list[str]:
    required_markers = (
        "evidence ledger attached",
        "maintain verified scanner-worker artifacts",
    )
    retained: list[str] = []
    for value in existing:
        text = _text(value)
        if text and any(marker in text.casefold() for marker in required_markers):
            retained.append(text)
    output: list[str] = []
    seen: set[str] = set()
    for value in [*retained, *generated]:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def prepare_express_client_report(result: dict[str, Any]) -> dict[str, Any]:
    result.setdefault("assessment_type", "express")
    apply_customer_service_identity(result)
    priorities = _priority_items(result)
    result["priority_actions"] = priorities or [
        "No material scored finding was identified; verify evidence completeness and obtain exact-snapshot human approval before delivery."
    ]
    result["executive_summary"] = _executive_summary(result, priorities)
    result["quick_wins"] = priorities[:3] or [
        "Confirm the evidence package is complete and cross-format consistent before requesting final human approval."
    ]
    generated_plan = [
        "Maintain verified scanner-worker artifacts for dependency, secret, static-analysis, coverage, and complexity evidence in each client-facing report.",
        "0-30 days: close current-run failed, timed-out, unavailable, and triage-required analyzer evidence; repair confirmed security and static-analysis issues.",
        "31-60 days: decompose the highest verified complexity/churn hotspots and add focused regression tests for the affected behavior.",
        "61-90 days: run two consecutive same-SHA assessments, verify identical truth fingerprints, and approve the complete PDF/Markdown/HTML/JSON delivery package.",
    ]
    result["medium_term_plan"] = _merge_required_plan_items(list(result.get("medium_term_plan") or []), generated_plan)
    result["resourcing_recommendation"] = _resourcing(result)
    result["risk_register"] = _risk_register(result)
    result["verification_checklist"] = [
        "Exact repository commit SHA is recorded and matches every scanner and complexity artifact.",
        "Every scored section has current-run evidence or an explicit access limitation.",
        "Failed, timed-out, unavailable, and triage-required analyzers are not presented as GREEN.",
        "Supplemental and pending-acceptance controls display NOT SCORED with no numeric score.",
        "PDF, Markdown, HTML, and JSON present the same statuses, scores, priorities, and approval state.",
        "Two consecutive same-SHA runs retain the same canonical truth fingerprint and report artifact digest.",
        "Authorized human reviewer approves the exact-snapshot report before client delivery.",
    ]
    return result


def postprocess_express_client_reports(result: dict[str, Any]) -> dict[str, Any]:
    reports = result.get("reports")
    if not isinstance(reports, dict):
        return result
    markdown = reports.get("markdown")
    if isinstance(markdown, str):
        markdown = _rewrite_not_scored(markdown, result)
        markdown = _replace_paragraph_section(markdown, "Executive Summary", _text(result.get("executive_summary")))
        for heading, key in (
            ("Priority Actions", "priority_actions"),
            ("Quick Wins", "quick_wins"),
            ("Medium-Term Plan", "medium_term_plan"),
            ("Resourcing Recommendation", "resourcing_recommendation"),
            ("Risk Register", "risk_register"),
            ("Verification Checklist", "verification_checklist"),
        ):
            markdown = _replace_section(markdown, heading, [str(value) for value in result.get(key) or []])
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
        "executive_summary_decision_oriented": True,
        "priority_actions_evidence_derived": True,
        "generic_quick_wins_replaced": True,
        "thirty_sixty_ninety_plan_generated": True,
        "required_evidence_plan_items_preserved": True,
        "checklist_rendering_normalized": True,
        "resourcing_evidence_derived": True,
        "risk_register_evidence_derived": True,
        "verification_checklist_replaced": True,
        "canonical_service_identity_applied": True,
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
        prepare_express_client_report(result)
        payload = current(result)
        postprocess_express_client_reports(result)
        return payload

    setattr(render, _MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {"status": "installed", "version": VERSION, "pre_and_post_generation_bound": True}


__all__ = [
    "VERSION",
    "install_express_client_report_postprocessor_v27",
    "postprocess_express_client_reports",
    "prepare_express_client_report",
]
