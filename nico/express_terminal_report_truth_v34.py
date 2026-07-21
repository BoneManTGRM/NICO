from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_terminal_report_truth.v34"
_PATCH_MARKER = "_nico_express_terminal_report_truth_v34"
_SCANNER_IDS = {"scanner_worker", "scanner_worker_evidence"}
_CLIENT_ACCEPTANCE_IDS = {"client_acceptance", "client_human_acceptance"}


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        item = _text(value)
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _section_id(section: dict[str, Any]) -> str:
    return _text(section.get("id"), 100).casefold()


def _approved_acceptance(section: dict[str, Any]) -> bool:
    status = _text(section.get("status") or section.get("acceptance_status")).casefold()
    return bool(section.get("approved") or section.get("accepted") or status in {"approved", "accepted", "green"})


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _section_id(section)
    if section_id in _SCANNER_IDS:
        return True
    if section_id in _CLIENT_ACCEPTANCE_IDS:
        return not _approved_acceptance(section)
    return section.get("directly_scored") is False and section.get("presented_score", section.get("score")) is None


def _normalize_not_scored(section: dict[str, Any], *, scanner: bool) -> None:
    raw_score = section.get("source_score", section.get("score"))
    if isinstance(raw_score, (int, float)):
        section.setdefault("diagnostic_source_score", raw_score)
    section["id"] = "scanner_worker_evidence" if scanner else section.get("id")
    section["status"] = "supplemental" if scanner else "gray"
    section["presented_status"] = section["status"]
    section["score"] = None
    section["presented_score"] = None
    section["directly_scored"] = False
    section["exclude_from_maturity"] = True
    section["supplemental"] = scanner
    section["scoring_weight"] = 0
    section["score_label"] = "NOT SCORED"
    section["display_status"] = f"{section['status'].upper()} · NOT SCORED"
    section["presented_confidence"] = "review-limited"


def normalize_section_aliases(result: dict[str, Any]) -> dict[str, Any]:
    sections = result.get("sections")
    if not isinstance(sections, list):
        return result

    output: list[dict[str, Any]] = []
    scanner_section: dict[str, Any] | None = None
    scanner_index: int | None = None
    for raw in sections:
        if not isinstance(raw, dict):
            continue
        section = raw
        section_id = _section_id(section)
        if section_id in _SCANNER_IDS:
            if scanner_section is None:
                scanner_section = section
                scanner_index = len(output)
            else:
                for key in ("evidence", "findings", "unavailable", "limitations"):
                    scanner_section[key] = _unique([*(scanner_section.get(key) or []), *(section.get(key) or [])])
                for key, value in section.items():
                    scanner_section.setdefault(key, value)
            continue
        if section_id in _CLIENT_ACCEPTANCE_IDS and not _approved_acceptance(section):
            _normalize_not_scored(section, scanner=False)
        output.append(section)

    if scanner_section is not None:
        _normalize_not_scored(scanner_section, scanner=True)
        insert_at = scanner_index if scanner_index is not None else len(output)
        output.insert(min(insert_at, len(output)), scanner_section)
    result["sections"] = output
    return result


def _statement_authority(statement: str) -> int:
    lowered = statement.casefold()
    if lowered.startswith("canonical scanner disposition:"):
        return 0
    explicit_status = bool(re.search(r"\bstatus\s*[=:]\s*(?:completed|failed|timeout|timed[_ -]?out|unavailable|error)", lowered))
    immutable = "commit=" in lowered and "scan_id=" in lowered
    if explicit_status and immutable:
        return 4
    if explicit_status and ("exact-snapshot" in lowered or "current-run" in lowered or "scanner-worker" in lowered or "scanner worker" in lowered):
        return 3
    if explicit_status:
        return 2
    if "exact-snapshot" in lowered or "current-run" in lowered:
        return 1
    return 0


def _install_scanner_disposition_precedence() -> None:
    from nico import express_scanner_disposition_truth_v1 as scanner

    if getattr(scanner._dispositions, _PATCH_MARKER, False):
        return

    def merge_disposition(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
        if current is None:
            return dict(candidate)
        current_authority = int(current.get("authority") or 0)
        candidate_authority = int(candidate.get("authority") or 0)
        if candidate_authority > current_authority:
            winner, other = candidate, current
        elif candidate_authority < current_authority:
            winner, other = current, candidate
        else:
            current_rank = scanner._STATUS_ORDER.get(str(current.get("status")), 0)
            candidate_rank = scanner._STATUS_ORDER.get(str(candidate.get("status")), 0)
            winner, other = (candidate, current) if candidate_rank > current_rank else (current, candidate)
        merged = dict(winner)
        statements = list(merged.get("source_statements") or [])
        for item in other.get("source_statements") or []:
            if item not in statements:
                statements.append(item)
        merged["source_statements"] = statements
        counts = [value for value in (winner.get("findings"), other.get("findings")) if isinstance(value, int)]
        merged["findings"] = max(counts) if counts else None
        merged["authority"] = max(current_authority, candidate_authority)
        return merged

    def dispositions(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}
        for field in ("evidence", "findings", "unavailable", "limitations"):
            for raw in section.get(field) or []:
                statement = _text(raw)
                if not statement or statement.casefold().startswith("canonical scanner disposition:"):
                    continue
                tool = scanner._tool_from_text(statement)
                if not tool:
                    continue
                status, findings = scanner._classify(statement)
                candidate = {
                    "tool": tool,
                    "status": status,
                    "findings": findings,
                    "authority": _statement_authority(statement),
                    "source_statements": [statement],
                }
                output[tool] = merge_disposition(output.get(tool), candidate)
        return output

    previous_replace = scanner._replace_scope_conflicts

    def replace_scope_conflicts(section: dict[str, Any], dispositions_by_tool: dict[str, dict[str, Any]]) -> None:
        for field in ("evidence", "findings", "unavailable", "limitations"):
            retained: list[Any] = []
            for raw in section.get(field) or []:
                statement = _text(raw)
                if statement.casefold().startswith("canonical scanner disposition:"):
                    continue
                tool = scanner._tool_from_text(statement)
                winner = dispositions_by_tool.get(tool or "")
                if winner and tool:
                    candidate_status, _ = scanner._classify(statement)
                    candidate_authority = _statement_authority(statement)
                    winner_authority = int(winner.get("authority") or 0)
                    winner_status = str(winner.get("status") or "unknown")
                    if candidate_authority < winner_authority and candidate_status != winner_status:
                        continue
                retained.append(raw)
            section[field] = retained
        previous_replace(section, dispositions_by_tool)

    setattr(dispositions, _PATCH_MARKER, True)
    setattr(dispositions, "_nico_previous", scanner._dispositions)
    setattr(merge_disposition, _PATCH_MARKER, True)
    setattr(merge_disposition, "_nico_previous", scanner._merge_disposition)
    setattr(replace_scope_conflicts, _PATCH_MARKER, True)
    setattr(replace_scope_conflicts, "_nico_previous", previous_replace)
    scanner._merge_disposition = merge_disposition
    scanner._dispositions = dispositions
    scanner._replace_scope_conflicts = replace_scope_conflicts


def _presented_status(section: dict[str, Any]) -> str:
    if _not_scored(section):
        return "supplemental" if _section_id(section) in _SCANNER_IDS else "gray"
    return _text(section.get("presented_status") or section.get("status") or "unknown").casefold()


def _presented_score(section: dict[str, Any]) -> int | None:
    if _not_scored(section):
        return None
    value = section.get("presented_score", section.get("score"))
    return int(value) if isinstance(value, (int, float)) else None


def _maturity_level(score: int | None) -> str:
    value = int(score or 0)
    if value >= 82:
        return "Senior"
    if value >= 58:
        return "Mid"
    return "Junior"


def _transparent_executive_summary(result: dict[str, Any]) -> str:
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    source_score = maturity.get("source_score", maturity.get("score"))
    source_level = _text(maturity.get("level") or _maturity_level(source_score))
    adjusted_score = result.get("evidence_adjusted_score", maturity.get("presented_score"))
    adjusted_text = f"{int(adjusted_score)}/100" if isinstance(adjusted_score, (int, float)) else "not calculated"
    repository = _text(result.get("repository") or result.get("source_scope") or "the authorized repository")
    return (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repository}. "
        f"The baseline source maturity is {source_level} ({source_score}/100), while the evidence-adjusted score is {adjusted_text} after explicit deductions for failed, timed-out, unavailable, and triage-required evidence. "
        "Supplemental scanner evidence and pending client acceptance are not scored. "
        "Automated evidence collection and draft reporting are complete, but client delivery remains blocked pending exact-snapshot human review."
    )


def build_presentation_markdown(result: dict[str, Any]) -> str:
    normalize_section_aliases(result)
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    source_score = maturity.get("source_score", maturity.get("score"))
    adjusted_score = result.get("evidence_adjusted_score", maturity.get("presented_score"))
    lines = [
        f"# Express Technical Health Assessment — {result.get('repository') or result.get('source_scope') or 'authorized repository'}",
        "",
        f"Generated: {result.get('generated_at') or 'Not recorded'}",
        f"Client: {result.get('client_name') or 'Not specified'}",
        f"Project: {result.get('project_name') or 'Not specified'}",
        f"Coverage target: {((result.get('coverage_targets') or {}).get('express_technical_health_assessment') or {}).get('target') or '90-95%'}",
        "",
        "## Executive Summary",
        _text(result.get("executive_summary") or _transparent_executive_summary(result), 3000),
        "",
        "## Score Transparency",
        f"- Baseline source maturity: {_text(maturity.get('level') or _maturity_level(source_score))} ({source_score}/100).",
        f"- Evidence-adjusted score: {int(adjusted_score)}/100." if isinstance(adjusted_score, (int, float)) else "- Evidence-adjusted score: not calculated.",
        "- Failed, timed-out, unavailable, and triage-required evidence produces explicit section deductions.",
        "- Supplemental scanner evidence and pending client acceptance are NOT SCORED.",
        "",
        "## Human Review Requirement",
        "NICO can automate evidence collection and draft reporting, but final client-facing conclusions, Q&A, business context, resourcing decisions, and delivery approval require an authorized human reviewer.",
        "",
        "## Maturity Semaphore",
    ]
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = _text(section.get("label") or section.get("title") or section.get("id"))
        status = _presented_status(section)
        score = _presented_score(section)
        value = f"{status} · NOT SCORED" if score is None else f"{status} · {score}/100"
        lines.append(f"- **{label}**: {value}")
    if isinstance(adjusted_score, (int, float)):
        lines.append(f"- **Work vs Expected**: {_maturity_level(int(adjusted_score))}")
    lines.extend(["", "## Assessment Sections"])

    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = _text(section.get("label") or section.get("title") or section.get("id"))
        status = _presented_status(section).upper()
        score = _presented_score(section)
        score_label = "NOT SCORED" if score is None else f"{score}/100"
        lines.extend([f"### {label} — {status} ({score_label})", _text(section.get("summary"), 3000), "", "Evidence:"])
        lines.extend(f"- {_text(value, 1800)}" for value in _unique(section.get("evidence")))
        if section.get("findings"):
            lines.append("Findings:")
            lines.extend(f"- {_text(value, 1800)}" for value in _unique(section.get("findings")))
        for unavailable in _unique(section.get("unavailable")):
            lines.append(f"- Unavailable: {_text(unavailable, 1800)}")
        if score is not None:
            source = section.get("source_score", section.get("score"))
            deductions = section.get("score_deductions") if isinstance(section.get("score_deductions"), list) else []
            lines.extend(["Score reconciliation:", f"- Source score: {source}/100.", f"- Evidence-adjusted score: {score}/100."])
            for deduction in deductions:
                if isinstance(deduction, dict):
                    lines.append(
                        f"- {deduction.get('rule_id')}: -{deduction.get('points')} points — {_text(deduction.get('reason'))} Evidence: {_text(deduction.get('evidence'), 500)}"
                    )
        lines.append("")

    for title, key in (
        ("Priority Actions", "priority_actions"),
        ("Quick Wins", "quick_wins"),
        ("Medium-Term Plan", "medium_term_plan"),
        ("Resourcing Recommendation", "resourcing_recommendation"),
        ("Risk Register", "risk_register"),
        ("Verification Checklist", "verification_checklist"),
    ):
        values = _unique(result.get(key))
        if not values:
            continue
        lines.append(f"## {title}")
        prefix = "- [ ]" if key == "verification_checklist" else "-"
        lines.extend(f"{prefix} {_text(value, 1600)}" for value in values)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _finalize_result_truth(result: dict[str, Any]) -> None:
    from nico import express_client_report_postprocessor_v27 as postprocessor
    from nico import express_cross_format_contract_v24 as cross_format
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import express_scanner_disposition_truth_v1 as scanner

    normalize_section_aliases(result)
    scanner.reconcile_express_scanner_dispositions(result)
    scoring.reconcile_express_scores(result)
    result["executive_summary"] = _transparent_executive_summary(result)
    postprocessor.prepare_express_client_report(result)
    result["executive_summary"] = _transparent_executive_summary(result)
    scoring.rewrite_cross_format_scores(result)
    postprocessor.postprocess_express_client_reports(result)
    scoring.rewrite_cross_format_scores(result)
    cross_format.build_cross_format_contract(result)
    result["express_terminal_report_truth"] = {
        "status": "complete",
        "version": VERSION,
        "scanner_alias_normalized": True,
        "authoritative_current_run_scanner_precedence": True,
        "not_scored_numeric_leakage_blocked": True,
        "source_and_evidence_adjusted_scores_disclosed": True,
        "final_rebuild_uses_presented_fields": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _install_rebuild_patch() -> None:
    from nico import final_report_consistency as final
    from nico.hosted_assessment import build_html, build_pdf_base64

    if getattr(final._rebuild_reports, _PATCH_MARKER, False):
        return
    previous = final._rebuild_reports

    def rebuild_reports(result: dict[str, Any]) -> None:
        if final._wants_es_mx(result):
            previous(result)
            _finalize_result_truth(result)
            return
        _finalize_result_truth(result)
        reports = dict(result.get("reports") or {})
        markdown = build_presentation_markdown(result)
        reports["markdown"] = markdown
        reports["html"] = build_html(markdown)
        result["reports"] = reports
        try:
            from nico.assessment_quality import _build_polished_pdf_base64

            pdf_base64, pdf_error = _build_polished_pdf_base64(result)
        except Exception:
            pdf_base64, pdf_error = build_pdf_base64(markdown)
        if pdf_base64:
            reports["pdf_base64"] = pdf_base64
            reports["pdf_filename"] = f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf"
        elif pdf_error:
            reports["pdf_error"] = pdf_error
        result["reports"] = reports
        _finalize_result_truth(result)

    setattr(rebuild_reports, _PATCH_MARKER, True)
    setattr(rebuild_reports, "_nico_previous", previous)
    final._rebuild_reports = rebuild_reports
    final.build_markdown = build_presentation_markdown


def install_express_terminal_report_truth_v34() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_client_report_postprocessor_v27 as postprocessor
    from nico import express_client_report_postprocessor_v31_compat as compat

    _install_scanner_disposition_precedence()
    compat._NOT_SCORED_IDS = set(compat._NOT_SCORED_IDS) | _SCANNER_IDS
    postprocessor._not_scored = _not_scored
    _install_rebuild_patch()

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        _finalize_result_truth(result)
        payload = current(result)
        _finalize_result_truth(result)
        return payload

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "scanner_alias_normalized": True,
        "scanner_precedence_repaired": True,
        "presentation_rebuild_repaired": True,
        "not_scored_leakage_blocked": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "build_presentation_markdown",
    "install_express_terminal_report_truth_v34",
    "normalize_section_aliases",
]
