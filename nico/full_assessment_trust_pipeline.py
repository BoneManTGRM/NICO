from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.evidence_ledger import attach_evidence_ledger
from nico.export_truth_gate import apply_export_truth_gate
from nico.full_assessment_pdf import (
    FULL_ASSESSMENT_PDF_STYLE_VERSION,
    build_full_assessment_pdf_base64,
    full_assessment_pdf_filename,
)
from nico.reports import html_report, markdown_report
from nico.storage import STORE
from nico.trust_engine import apply_strict_trust_engine
from nico.trust_report_display import attach_trust_report_display

TOOL_SECTIONS = {
    "pip-audit": "dependency_health",
    "npm-audit": "dependency_health",
    "osv-scanner": "dependency_health",
    "bandit": "static_analysis",
    "semgrep": "static_analysis",
    "eslint": "static_analysis",
    "typescript": "static_analysis",
    "gitleaks": "secrets_review",
    "trufflehog": "secrets_review",
    "detect-secrets": "secrets_review",
    "complexity engine": "velocity_complexity",
}

ZERO_EXCEPTION_MARKERS = (
    "unavailable/failed/timed out: 0/0/0",
    "unavailable/failed/timed_out: 0/0/0",
)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tool_set(scanner: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in _list(scanner.get(key)) if str(item).strip()}


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and item.get("id")
    }


def _append_unique(section: dict[str, Any], field: str, line: str) -> None:
    values = section.setdefault(field, [])
    if not isinstance(values, list):
        values = [values]
        section[field] = values
    if line not in values:
        values.append(line)


def _normalize_zero_exception_lines(assessment: dict[str, Any]) -> None:
    for section in _section_map(assessment).values():
        evidence = section.get("evidence") if isinstance(section.get("evidence"), list) else []
        normalized: list[Any] = []
        for line in evidence:
            text = str(line)
            if any(marker in text.lower() for marker in ZERO_EXCEPTION_MARKERS):
                normalized.append("No scanner execution exceptions were recorded for this section.")
            else:
                normalized.append(line)
        section["evidence"] = normalized
        section["verified_claims"] = list(normalized)


def _attach_scanner_coverage_lines(assessment: dict[str, Any], scanner: dict[str, Any]) -> None:
    sections = _section_map(assessment)
    completed = _tool_set(scanner, "tools_run")
    unavailable = _tool_set(scanner, "unavailable_tools")
    failed = _tool_set(scanner, "failed_tools")
    timed_out = _tool_set(scanner, "timed_out_tools")

    for tool in sorted(completed | unavailable | failed | timed_out):
        section = sections.get(TOOL_SECTIONS.get(tool, ""))
        if not section:
            continue
        if tool in completed:
            _append_unique(
                section,
                "evidence",
                f"{tool} scanner execution completed for this exact report run; this coverage line represents execution only and does not establish a clean result.",
            )
        elif tool in unavailable:
            _append_unique(section, "unavailable", f"{tool} scanner execution was unavailable for this exact report run.")
        elif tool in failed:
            _append_unique(section, "unavailable", f"{tool} scanner execution failed for this exact report run.")
        elif tool in timed_out:
            _append_unique(section, "unavailable", f"{tool} scanner execution timed out for this exact report run.")

        section["verified_claims"] = list(section.get("evidence") or [])
        section["unverified_claims"] = list(section.get("unavailable") or [])


def _restore_weighted_technical_score(assessment: dict[str, Any]) -> None:
    from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS

    sections = _section_map(assessment)
    weighted = 0
    total_weight = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = sections.get(section_id)
        if not section:
            continue
        try:
            score = int(section.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        weighted += score * weight
        total_weight += weight
    score = round(weighted / total_weight) if total_weight else 0
    level = "Senior" if score >= 82 else "Mid" if score >= 58 else "Junior"
    signal = assessment.setdefault("maturity_signal", {})
    signal["level"] = level
    signal["score"] = score
    signal["summary"] = "Weighted technical score recomputed after strict trust caps were applied."
    scorecard = assessment.setdefault("scorecard", {})
    scorecard["technical_score"] = score
    scorecard["post_trust_caps"] = True


def _normalize_full_assessment_identity(result: dict[str, Any]) -> None:
    result["report_path"] = "full_run"
    result["report_path_label"] = "Full Assessment"
    summary = str(result.get("executive_summary") or "")
    result["executive_summary"] = summary.replace(
        "authorized hosted Express Technical Health Assessment",
        "authorized Full Assessment",
    )


def prepare_full_assessment_trust(
    assessment: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply evidence-ledger and strict trust rules before report rendering."""

    prepared = deepcopy(assessment)
    prepared["status"] = "complete"
    prepared["report_run_id"] = prepared.get("run_id") or ""
    _normalize_full_assessment_identity(prepared)
    _normalize_zero_exception_lines(prepared)
    _attach_scanner_coverage_lines(prepared, scanner_evidence)
    prepared = attach_evidence_ledger(prepared)
    prepared = apply_strict_trust_engine(prepared)
    _restore_weighted_technical_score(prepared)
    prepared["human_review_required"] = True
    prepared["client_ready"] = False
    verdict = prepared.setdefault("client_delivery_verdict", {})
    verdict["status"] = "human_review_required"
    verdict.setdefault("confidence", "limited")
    blockers = list(verdict.get("blockers") or [])
    for blocker in (
        "Final client delivery requires human review and approval.",
        "Evidence-ledger coverage and scanner execution do not establish exhaustive absence of defects, vulnerabilities, or secrets.",
    ):
        if blocker not in blockers:
            blockers.append(blocker)
    verdict["blockers"] = blockers
    prepared = attach_trust_report_display(prepared)
    _normalize_full_assessment_identity(prepared)
    prepared["status"] = "complete"
    prepared["report_finality"] = "final"
    prepared["review_status"] = "pending_human_approval"
    prepared["delivery_status"] = "blocked_pending_human_approval"
    prepared["draft_only"] = False
    return prepared


def _report_payload(package: dict[str, Any]) -> dict[str, Any]:
    formats = package.get("formats") if isinstance(package.get("formats"), dict) else {}
    return {
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": formats.get("pdf") or "",
        "pdf_filename": package.get("pdf_filename") or "",
        "pdf_style": package.get("pdf_style") or "",
        "pdf_error": package.get("pdf_error") or "",
    }


def _render_candidate(candidate: dict[str, Any]) -> None:
    _normalize_full_assessment_identity(candidate)
    markdown = markdown_report(candidate)
    candidate.setdefault("reports", {})["markdown"] = markdown
    candidate["reports"]["html"] = html_report(markdown)


def _render_pdf_candidate(candidate: dict[str, Any], *, report_id: str) -> None:
    reports = candidate.setdefault("reports", {})
    pdf, error = build_full_assessment_pdf_base64(candidate, report_id=report_id)
    if pdf:
        reports["pdf_base64"] = pdf
        reports["pdf_filename"] = full_assessment_pdf_filename(candidate)
        reports["pdf_style"] = FULL_ASSESSMENT_PDF_STYLE_VERSION
        reports["pdf_error"] = ""
    else:
        reports["pdf_base64"] = ""
        reports["pdf_filename"] = full_assessment_pdf_filename(candidate)
        reports["pdf_style"] = FULL_ASSESSMENT_PDF_STYLE_VERSION
        reports["pdf_error"] = error or "Full Assessment PDF export was unavailable for this report run."


def finalize_full_assessment_exports(
    assessment: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    """Validate rendered exports, generate a review PDF, and persist the guarded package."""

    candidate = deepcopy(assessment)
    candidate["status"] = "complete"
    candidate["reports"] = _report_payload(package)
    report_id = str(package.get("report_id") or "")
    candidate["report_id"] = report_id
    _normalize_full_assessment_identity(candidate)

    candidate = apply_export_truth_gate(candidate)
    candidate = attach_trust_report_display(candidate)
    _normalize_full_assessment_identity(candidate)
    _render_candidate(candidate)

    first_status = str((candidate.get("export_truth_gate") or {}).get("status") or "pending")
    candidate = apply_export_truth_gate(candidate)
    second_status = str((candidate.get("export_truth_gate") or {}).get("status") or "pending")
    if second_status != first_status:
        candidate = attach_trust_report_display(candidate)
        _normalize_full_assessment_identity(candidate)
        _render_candidate(candidate)
        candidate = apply_export_truth_gate(candidate)

    _render_pdf_candidate(candidate, report_id=report_id)
    candidate = apply_export_truth_gate(candidate)
    candidate["human_review_required"] = True
    candidate["client_ready"] = False
    candidate["delivery_verdict"] = "human_review_required"
    candidate["status"] = "complete"
    candidate["report_finality"] = "final"
    candidate["review_status"] = "pending_human_approval"
    candidate["delivery_status"] = "blocked_pending_human_approval"
    candidate["draft_only"] = False

    guarded_package = deepcopy(package)
    guarded_package["formats"] = dict(guarded_package.get("formats") or {})
    guarded_package["formats"]["markdown"] = candidate.get("reports", {}).get("markdown") or ""
    guarded_package["formats"]["html"] = candidate.get("reports", {}).get("html") or ""
    guarded_package["formats"]["json"] = candidate
    guarded_package["formats"]["pdf"] = candidate.get("reports", {}).get("pdf_base64") or None
    guarded_package["pdf_filename"] = candidate.get("reports", {}).get("pdf_filename") or full_assessment_pdf_filename(candidate)
    guarded_package["pdf_style"] = candidate.get("reports", {}).get("pdf_style") or FULL_ASSESSMENT_PDF_STYLE_VERSION
    guarded_package["pdf_error"] = candidate.get("reports", {}).get("pdf_error") or ""
    guarded_package["trust_level"] = candidate.get("trust_level") or "Review-limited"
    guarded_package["trust_report_display"] = candidate.get("trust_report_display") or {}
    guarded_package["evidence_ledger"] = candidate.get("evidence_ledger") or {}
    guarded_package["export_truth_gate"] = candidate.get("export_truth_gate") or {}
    guarded_package["client_delivery_allowed"] = False
    guarded_package["human_review_required"] = True
    guarded_package["report_finality"] = "final"
    guarded_package["review_status"] = "pending_human_approval"
    guarded_package["delivery_status"] = "blocked_pending_human_approval"
    guarded_package["draft_only"] = False
    guarded_package["legacy_export_draft_gate"] = bool((candidate.get("export_truth_gate") or {}).get("draft_only"))

    if report_id:
        STORE.put("reports", report_id, guarded_package)
        STORE.audit(
            "report.full_assessment_truth_gates_applied",
            {
                "report_id": report_id,
                "run_id": guarded_package.get("run_id") or candidate.get("run_id") or "",
                "trust_level": guarded_package.get("trust_level"),
                "export_truth_gate_status": guarded_package.get("export_truth_gate", {}).get("status"),
                "pdf_generated": bool(guarded_package.get("formats", {}).get("pdf")),
                "pdf_style": guarded_package.get("pdf_style"),
            },
            customer_id=guarded_package.get("customer_id") or "default_customer",
            project_id=guarded_package.get("project_id") or "default_project",
        )

    formats = guarded_package.get("formats") or {}
    reports = {
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": formats.get("pdf") or "",
        "pdf_filename": guarded_package.get("pdf_filename") or full_assessment_pdf_filename(candidate),
        "pdf_style": guarded_package.get("pdf_style") or FULL_ASSESSMENT_PDF_STYLE_VERSION,
        "pdf_error": guarded_package.get("pdf_error") or "",
        "report_id": report_id,
        "idempotency_key": guarded_package.get("idempotency_key") or "",
        "idempotent_reuse": bool(guarded_package.get("idempotent_reuse")),
        "scan_id": guarded_package.get("scan_id") or "",
        "trust_level": guarded_package.get("trust_level") or "Review-limited",
        "client_delivery_allowed": False,
        "human_review_required": True,
        "report_finality": "final",
        "review_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "draft_only": False,
        "evidence_ledger_status": str((candidate.get("evidence_ledger") or {}).get("status") or "missing"),
        "export_truth_gate": candidate.get("export_truth_gate") or {},
    }
    return {"assessment": candidate, "package": guarded_package, "reports": reports}
