from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.evidence_ledger import attach_evidence_ledger
from nico.export_truth_gate import apply_export_truth_gate
from nico.reports import html_report, markdown_report
from nico.storage import STORE
from nico.trust_engine import apply_strict_trust_engine
from nico.trust_report_display import attach_trust_report_display

TOOL_CATEGORIES = {
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "osv-scanner": "dependency",
    "bandit": "static",
    "semgrep": "static",
    "eslint": "static",
    "typescript": "static",
    "gitleaks": "secret",
    "trufflehog": "secret",
    "detect-secrets": "secret",
    "complexity engine": "complexity",
}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _tool_set(scanner: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in _list(scanner.get(key)) if str(item).strip()}


def _scanner_worker_artifact(assessment: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    requested = _tool_set(scanner, "tools_requested")
    completed = _tool_set(scanner, "tools_run")
    unavailable = _tool_set(scanner, "unavailable_tools")
    failed = _tool_set(scanner, "failed_tools")
    timed_out = _tool_set(scanner, "timed_out_tools")
    names = sorted(requested | completed | unavailable | failed | timed_out)
    tools: dict[str, Any] = {}

    for name in names:
        if name in completed:
            status = "completed"
            verified = True
        elif name in unavailable:
            status = "unavailable"
            verified = False
        elif name in failed or name in timed_out:
            status = "failed"
            verified = False
        else:
            status = "not_verified"
            verified = False
        tools[name] = {
            "tool": name,
            "category": TOOL_CATEGORIES.get(name, "other"),
            "evidence_status": status,
            "verified_for_this_report": verified,
            "findings_count": None,
            "findings_count_status": "unknown_from_summary",
            "repository": assessment.get("repository") or "",
            "report_run_id": assessment.get("run_id") or "",
        }

    return {
        "report_run_id": assessment.get("run_id") or "",
        "repository": assessment.get("repository") or "",
        "generated_at": assessment.get("generated_at") or "",
        "tools": tools,
        "source": "full_assessment_scanner_summary",
        "guardrail": "Completed tool execution is attached as run-bound coverage. Finding counts remain unknown unless parsed evidence supplies them.",
    }


def prepare_full_assessment_trust(
    assessment: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply evidence-ledger and strict trust rules before report rendering."""

    prepared = deepcopy(assessment)
    prepared["status"] = "complete"
    prepared["report_run_id"] = prepared.get("run_id") or ""
    prepared["scanner_worker_artifact"] = _scanner_worker_artifact(prepared, scanner_evidence)
    prepared = attach_evidence_ledger(prepared)
    prepared = apply_strict_trust_engine(prepared)
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
    prepared["status"] = "draft"
    return prepared


def _report_payload(package: dict[str, Any]) -> dict[str, Any]:
    formats = package.get("formats") if isinstance(package.get("formats"), dict) else {}
    return {
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": formats.get("pdf") or "",
    }


def _render_candidate(candidate: dict[str, Any]) -> None:
    markdown = markdown_report(candidate)
    candidate.setdefault("reports", {})["markdown"] = markdown
    candidate["reports"]["html"] = html_report(markdown)


def finalize_full_assessment_exports(
    assessment: dict[str, Any],
    package: dict[str, Any],
) -> dict[str, Any]:
    """Validate rendered exports, refresh trust display, and persist the guarded package."""

    candidate = deepcopy(assessment)
    candidate["status"] = "complete"
    candidate["reports"] = _report_payload(package)

    candidate = apply_export_truth_gate(candidate)
    candidate = attach_trust_report_display(candidate)
    _render_candidate(candidate)

    first_status = str((candidate.get("export_truth_gate") or {}).get("status") or "pending")
    candidate = apply_export_truth_gate(candidate)
    second_status = str((candidate.get("export_truth_gate") or {}).get("status") or "pending")
    if second_status != first_status:
        candidate = attach_trust_report_display(candidate)
        _render_candidate(candidate)
        candidate = apply_export_truth_gate(candidate)

    candidate["human_review_required"] = True
    candidate["client_ready"] = False
    candidate["delivery_verdict"] = "human_review_required"
    candidate["status"] = "draft"

    guarded_package = deepcopy(package)
    guarded_package["formats"] = dict(guarded_package.get("formats") or {})
    guarded_package["formats"]["markdown"] = candidate.get("reports", {}).get("markdown") or ""
    guarded_package["formats"]["html"] = candidate.get("reports", {}).get("html") or ""
    guarded_package["formats"]["json"] = candidate
    guarded_package["trust_level"] = candidate.get("trust_level") or "Review-limited"
    guarded_package["trust_report_display"] = candidate.get("trust_report_display") or {}
    guarded_package["evidence_ledger"] = candidate.get("evidence_ledger") or {}
    guarded_package["export_truth_gate"] = candidate.get("export_truth_gate") or {}
    guarded_package["client_delivery_allowed"] = False
    guarded_package["human_review_required"] = True
    guarded_package["draft_only"] = bool((candidate.get("export_truth_gate") or {}).get("draft_only"))

    report_id = str(guarded_package.get("report_id") or "")
    if report_id:
        STORE.put("reports", report_id, guarded_package)
        STORE.audit(
            "report.full_assessment_truth_gates_applied",
            {
                "report_id": report_id,
                "run_id": guarded_package.get("run_id") or candidate.get("run_id") or "",
                "trust_level": guarded_package.get("trust_level"),
                "export_truth_gate_status": guarded_package.get("export_truth_gate", {}).get("status"),
            },
            customer_id=guarded_package.get("customer_id") or "default_customer",
            project_id=guarded_package.get("project_id") or "default_project",
        )

    formats = guarded_package.get("formats") or {}
    reports = {
        "markdown": formats.get("markdown") or "",
        "html": formats.get("html") or "",
        "pdf_base64": "",
        "pdf_filename": "nico-assessment.pdf",
        "pdf_error": "PDF export is not produced by this report package path; Markdown, HTML, and JSON were generated.",
        "report_id": report_id,
        "idempotency_key": guarded_package.get("idempotency_key") or "",
        "idempotent_reuse": bool(guarded_package.get("idempotent_reuse")),
        "scan_id": guarded_package.get("scan_id") or "",
        "trust_level": guarded_package.get("trust_level") or "Review-limited",
        "client_delivery_allowed": False,
        "human_review_required": True,
        "draft_only": bool(guarded_package.get("draft_only")),
        "evidence_ledger_status": str((candidate.get("evidence_ledger") or {}).get("status") or "missing"),
        "export_truth_gate": candidate.get("export_truth_gate") or {},
    }
    return {
        "assessment": candidate,
        "package": guarded_package,
        "reports": reports,
    }
