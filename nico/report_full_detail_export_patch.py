from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any, Callable


def _detail_limit() -> int:
    try:
        return max(8, min(200, int(os.getenv("NICO_PDF_DETAIL_MAX_ITEMS", "50"))))
    except ValueError:
        return 50


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_full_detail_export(result: dict[str, Any]) -> dict[str, Any]:
    sections = []
    for section in _safe_list(result.get("sections")):
        if not isinstance(section, dict):
            continue
        sections.append(
            {
                "id": section.get("id"),
                "label": section.get("label"),
                "score": section.get("score"),
                "status": section.get("status"),
                "summary": section.get("summary"),
                "evidence": deepcopy(_safe_list(section.get("evidence"))),
                "findings": deepcopy(_safe_list(section.get("findings"))),
                "unavailable": deepcopy(_safe_list(section.get("unavailable"))),
                "evidence_count": len(_safe_list(section.get("evidence"))),
                "finding_count": len(_safe_list(section.get("findings"))),
                "unavailable_count": len(_safe_list(section.get("unavailable"))),
            }
        )

    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    bundle = result.get("evidence_artifact_bundle") if isinstance(result.get("evidence_artifact_bundle"), dict) else {}
    ledger = result.get("evidence_ledger") if isinstance(result.get("evidence_ledger"), dict) else bundle.get("evidence_ledger", {}) if isinstance(bundle.get("evidence_ledger"), dict) else {}
    scanner = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}

    return {
        "artifact_schema": "nico.report_full_detail.v1",
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "assessment_mode": result.get("assessment_mode"),
        "human_review_required": bool(result.get("human_review_required", True)),
        "section_count": len(sections),
        "sections": sections,
        "scanner_worker_execution": deepcopy(result.get("scanner_worker_execution") if isinstance(result.get("scanner_worker_execution"), dict) else {}),
        "scanner_worker_artifact_summary": {
            "tool_count": len(scanner.get("tools") if isinstance(scanner.get("tools"), dict) else {}),
            "tools": {
                name: {
                    "status": payload.get("status") if isinstance(payload, dict) else "unknown",
                    "current_run": bool(payload.get("current_run")) if isinstance(payload, dict) else False,
                    "verified_for_this_report": bool(payload.get("verified_for_this_report")) if isinstance(payload, dict) else False,
                    "findings_count": int(payload.get("findings_count") or payload.get("finding_count") or 0) if isinstance(payload, dict) else 0,
                    "reason": payload.get("reason") or payload.get("failure_or_unavailable_reason") if isinstance(payload, dict) else "",
                }
                for name, payload in sorted((scanner.get("tools") if isinstance(scanner.get("tools"), dict) else {}).items())
            },
        },
        "complexity_engine_summary": deepcopy(result.get("complexity_engine_summary") if isinstance(result.get("complexity_engine_summary"), dict) else {}),
        "bandit_triage_summary": deepcopy(result.get("bandit_triage_summary") if isinstance(result.get("bandit_triage_summary"), dict) else {}),
        "secret_history_scan": deepcopy(result.get("secret_history_scan") if isinstance(result.get("secret_history_scan"), dict) else {}),
        "evidence_ledger_summary": {
            "entry_count": ledger.get("entry_count"),
            "verified_entry_count": ledger.get("verified_entry_count"),
            "partial_entry_count": ledger.get("partial_entry_count"),
            "unavailable_entry_count": ledger.get("unavailable_entry_count"),
            "finding_entry_count": ledger.get("finding_entry_count"),
            "ledger_hash": ledger.get("ledger_hash"),
        },
        "export_files": {
            "evidence_bundle_filename": reports.get("evidence_bundle_filename"),
            "evidence_ledger_filename": reports.get("evidence_ledger_filename"),
            "pdf_filename": reports.get("pdf_filename"),
        },
        "guardrail": "Full-detail exports preserve evidence, findings, and unavailable data; they do not convert unavailable evidence into verified proof.",
    }


def _markdown_appendix(detail: dict[str, Any]) -> str:
    lines = [
        "",
        "## Full Evidence Detail Appendix",
        "This appendix preserves full section evidence, findings, unavailable-data notes, and attached artifact summaries. Human review is still required before client-final conclusions.",
        "",
        f"- Repository: {detail.get('repository') or 'Not specified'}",
        f"- Evidence ledger hash: {detail.get('evidence_ledger_summary', {}).get('ledger_hash') or 'not attached'}",
        f"- Evidence ledger entries: {detail.get('evidence_ledger_summary', {}).get('entry_count') or 0}",
        f"- Verified entries: {detail.get('evidence_ledger_summary', {}).get('verified_entry_count') or 0}",
        f"- Partial entries: {detail.get('evidence_ledger_summary', {}).get('partial_entry_count') or 0}",
        f"- Unavailable entries: {detail.get('evidence_ledger_summary', {}).get('unavailable_entry_count') or 0}",
        "",
    ]
    tools = detail.get("scanner_worker_artifact_summary", {}).get("tools") if isinstance(detail.get("scanner_worker_artifact_summary"), dict) else {}
    if isinstance(tools, dict) and tools:
        lines += ["### Scanner Tool Detail", ""]
        for name, payload in tools.items():
            lines.append(
                f"- **{name}**: status={payload.get('status')}; current_run={payload.get('current_run')}; "
                f"verified={payload.get('verified_for_this_report')}; findings={payload.get('findings_count')}; reason={payload.get('reason') or 'none'}"
            )
        lines.append("")
    for section in detail.get("sections", []):
        if not isinstance(section, dict):
            continue
        lines += [
            f"### {section.get('label') or section.get('id')} full detail",
            f"Status: {str(section.get('status') or 'unknown').upper()} | Score: {section.get('score', 'N/A')}/100",
            section.get("summary") or "",
            "",
            f"Evidence items: {section.get('evidence_count', 0)}",
        ]
        for item in section.get("evidence", []):
            lines.append(f"- {item}")
        lines.append(f"Findings: {section.get('finding_count', 0)}")
        for item in section.get("findings", []):
            lines.append(f"- {item}")
        lines.append(f"Unavailable data items: {section.get('unavailable_count', 0)}")
        for item in section.get("unavailable", []):
            lines.append(f"- Unavailable: {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def attach_full_detail_report_exports(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("status") != "complete":
        return result
    output = result
    reports = output.setdefault("reports", {})
    detail = build_full_detail_export(output)
    reports["full_detail_json"] = json.dumps(detail, indent=2, sort_keys=True, default=str)
    reports["full_detail_filename"] = f"nico-full-detail-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    appendix = _markdown_appendix(detail)
    markdown = reports.get("markdown") if isinstance(reports.get("markdown"), str) else ""
    if "## Full Evidence Detail Appendix" not in markdown:
        reports["markdown"] = (markdown.rstrip() + "\n" + appendix).lstrip()
    reports["full_detail_markdown"] = appendix
    reports["full_detail_markdown_filename"] = f"nico-full-detail-{str(output.get('repository') or 'assessment').replace('/', '-')}.md"
    try:
        from nico.hosted_assessment import build_html

        reports["html"] = build_html(reports["markdown"])
    except Exception:
        pass
    output["report_full_detail_export"] = detail
    return output


def _patch_pdf_bullets_for_detail() -> None:
    from nico import assessment_quality

    original: Callable[..., list[Any]] | None = getattr(assessment_quality, "_nico_original_bullets_for_full_detail", None)
    if original is None:
        original = assessment_quality._bullets
        assessment_quality._nico_original_bullets_for_full_detail = original

    def bullets_with_fuller_detail(items: list[str], style: Any, max_items: int = 6) -> list[Any]:
        return original(items, style, max_items=max(max_items, min(_detail_limit(), len(items) if items else max_items)))

    assessment_quality._bullets = bullets_with_fuller_detail


def _patch_polish_for_full_detail_exports() -> None:
    from nico import assessment_quality

    original = getattr(assessment_quality, "_nico_original_polish_express_result_full_detail", None)
    if original is None:
        original = assessment_quality.polish_express_result
        assessment_quality._nico_original_polish_express_result_full_detail = original

    def polish_express_result_with_full_detail(result: dict[str, Any]) -> dict[str, Any]:
        polished = assessment_quality._nico_original_polish_express_result_full_detail(result)
        return attach_full_detail_report_exports(polished)

    assessment_quality.polish_express_result = polish_express_result_with_full_detail


def install_report_full_detail_export_patch() -> None:
    _patch_pdf_bullets_for_detail()
    _patch_polish_for_full_detail_exports()
