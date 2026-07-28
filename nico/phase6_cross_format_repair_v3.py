from __future__ import annotations

import html
from copy import deepcopy
from typing import Any

from nico import phase6_canonical_truth_v2 as truth
from nico import phase6_final_remediation_v1 as phase6
from nico.comprehensive_decision_grade_csv_v6 import _findings_csv
from nico.scanner_evidence_pipeline_v1 import REQUIRED_EVIDENCE_TOOLS

VERSION = "nico.phase6_cross_format_repair.v3"
_PATCH_MARKER = "_nico_phase6_cross_format_repair_v3"


def _scanner_status_block(assessment: dict[str, Any]) -> tuple[str, str]:
    health = assessment.get("evidence_health_summary")
    if not isinstance(health, dict):
        return "", ""
    completed = sorted({str(item).strip() for item in health.get("completed_scanners") or [] if str(item).strip()})
    incomplete = [item for item in health.get("incomplete_scanners") or [] if isinstance(item, dict)]
    if not completed and not incomplete:
        return "", ""

    markdown_lines = ["", "## Scanner execution status", ""]
    html_rows: list[str] = []
    for tool in completed:
        markdown_lines.append(f"- `{tool}`: completed with retained exact-commit evidence")
        html_rows.append(
            "<tr><td><code>" + html.escape(tool) + "</code></td>"
            "<td>Completed</td><td>Retained exact-commit evidence</td></tr>"
        )
    for item in incomplete:
        tool = str(item.get("scanner") or "unknown")
        status = str(item.get("status") or "incomplete")
        markdown_lines.append(f"- `{tool}`: {status}; limitation remains visible")
        html_rows.append(
            "<tr><td><code>" + html.escape(tool) + "</code></td>"
            "<td>" + html.escape(status) + "</td><td>Limitation remains visible</td></tr>"
        )
    markdown = "\n".join(markdown_lines) + "\n"
    html_block = (
        '<section id="scanner-execution-status"><h2>Scanner execution status</h2>'
        '<table><thead><tr><th>Scanner</th><th>Status</th><th>Evidence</th></tr></thead><tbody>'
        + "".join(html_rows)
        + "</tbody></table></section>"
    )
    return markdown, html_block


def _repair_scanner_health(assessment: dict[str, Any]) -> None:
    """Restore every prevalidated exact-SHA scanner to the report health model.

    The verification builder has already fail-closed validated the complete raw
    scanner artifact before report construction.  Some dependency records lose
    lower-level capture flags while being projected into the assessment, which
    previously made completed dependency scanners disappear from the report.
    """

    records = assessment.get("scanner_execution_records")
    if not isinstance(records, dict):
        return
    completed = sorted(
        tool
        for tool in REQUIRED_EVIDENCE_TOOLS
        if isinstance(records.get(tool), dict)
        and str((records.get(tool) or {}).get("status") or "").casefold() == "completed"
        and (records.get(tool) or {}).get("verified_for_this_report") is True
        and (records.get(tool) or {}).get("output_capture_complete") is True
        and (records.get(tool) or {}).get("raw_artifact_retention_complete") is True
        and bool((records.get(tool) or {}).get("artifact_hash") or (records.get(tool) or {}).get("raw_artifact_sha256"))
    )
    if not completed:
        return
    health = assessment.get("evidence_health_summary")
    if not isinstance(health, dict):
        health = {}
    health["completed_scanners"] = completed
    health["incomplete_scanners"] = [
        item
        for item in health.get("incomplete_scanners") or []
        if isinstance(item, dict) and str(item.get("scanner") or "") not in completed
    ]
    if not health["incomplete_scanners"] and set(completed) == set(REQUIRED_EVIDENCE_TOOLS):
        health["confidence_effect"] = "Every required scanner has complete retained exact-SHA evidence."
    health["report_status_derived_from_retained_artifact"] = True
    assessment["evidence_health_summary"] = health


def _normalize_findings_for_csv(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    findings = [
        deepcopy(item)
        for item in assessment.get("decision_grade_findings_register")
        or assessment.get("findings_register")
        or []
        if isinstance(item, dict)
    ]
    # CSV has no null scalar representation. Normalize the canonical model to
    # the exact values that round-trip through DictReader before validation.
    for item in findings:
        for key in ("finding_id", "priority", "status", "canonical_path", "canonical_location"):
            if item.get(key) is None:
                item[key] = ""
        if not item.get("finding_id") and item.get("id"):
            item["finding_id"] = str(item.get("id"))
        if item.get("canonical_line") in ("", 0):
            item["canonical_line"] = None
        for key in ("acceptance_criteria", "roadmap_mappings", "backlog_mappings"):
            item[key] = truth._ordered_unique(item.get(key) or [])
    assessment["findings_register"] = findings
    assessment["decision_grade_findings_register"] = findings
    assessment["executive_risk_register"] = findings[:7]
    return findings


def _repair_result(result: dict[str, Any]) -> dict[str, Any]:
    package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
    canonical_json = package.get("json") if isinstance(package.get("json"), dict) else {}
    rendered_assessment = canonical_json.get("assessment") if isinstance(canonical_json.get("assessment"), dict) else None
    if rendered_assessment is not None:
        result["assessment"] = deepcopy(rendered_assessment)

    assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
    _repair_scanner_health(assessment)
    canonical_findings = _normalize_findings_for_csv(assessment)
    result["assessment"] = assessment

    # Keep canonical JSON and CSV derived from the exact same repaired model.
    canonical_json["assessment"] = deepcopy(assessment)
    package["json"] = canonical_json
    package["findings_csv"] = _findings_csv(canonical_findings)

    markdown_block, html_block = _scanner_status_block(assessment)
    completed = [str(item).casefold() for item in ((assessment.get("evidence_health_summary") or {}).get("completed_scanners") or [])]

    markdown = str(package.get("markdown") or "")
    missing_markdown = [tool for tool in completed if tool and tool not in markdown.casefold()]
    if missing_markdown and markdown_block:
        package["markdown"] = markdown.rstrip() + "\n" + markdown_block

    html_text = str(package.get("html") or "")
    missing_html = [tool for tool in completed if tool and tool not in html_text.casefold()]
    if missing_html and html_block:
        marker = "</body>"
        package["html"] = html_text.replace(marker, html_block + marker, 1) if marker in html_text else html_text + html_block

    result["report_package"] = package
    result = truth.validate_cross_format_truth(result)
    package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
    manifest = package.get("canonical_truth_manifest") if isinstance(package.get("canonical_truth_manifest"), dict) else {}
    artifacts_complete = all(
        bool(package.get(key))
        for key in ("markdown", "html", "pdf_base64", "findings_csv", "evidence_ledger_csv", "json")
    )
    approved = result.get("client_delivery_allowed") is True or package.get("client_delivery_allowed") is True
    package["pdf_filename"] = phase6.normalize_report_filename(
        str(package.get("pdf_filename") or "nico-comprehensive-assessment.pdf"),
        complete=manifest.get("status") == "valid" and artifacts_complete,
        approved=approved,
    )
    result["report_package"] = package
    if manifest.get("status") == "valid" and result.get("reason") == "phase6_cross_format_truth_mismatch":
        result["reason"] = "human_review_required"
    return result


def install_phase6_cross_format_repair_v3() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    current_build = report.build_comprehensive_report_package
    if getattr(current_build, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _repair_result(current_build(*args, **kwargs))

    setattr(build, _PATCH_MARKER, True)
    report.build_comprehensive_report_package = build
    return {
        "status": "installed",
        "version": VERSION,
        "canonical_json_and_csv_projection_reconciled": True,
        "completed_scanners_visible_in_markdown_and_html": True,
        "terminal_filename_recomputed_after_truth_validation": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_phase6_cross_format_repair_v3"]