from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.report_accuracy import apply_report_accuracy
from nico.scanner_evidence import enrich_payload_with_scanner_evidence
from nico.storage import STORE


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _status_counts(sections: list[Any]) -> dict[str, int]:
    counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0, "unknown": 0}
    for item in sections:
        if isinstance(item, dict):
            status = str(item.get("status") or "unknown").lower()
            counts[status if status in counts else "unknown"] += 1
        else:
            counts["unknown"] += 1
    return counts


def _guard_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return apply_report_accuracy(enrich_payload_with_scanner_evidence(payload))


def _delivery_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    validated = _guard_payload(payload)
    verdict = validated.get("client_delivery_verdict") or {}
    sections = [item for item in validated.get("sections", []) if isinstance(item, dict)]
    return {
        "verdict": verdict.get("status", "human_review_required"),
        "confidence": verdict.get("confidence", "limited"),
        "status_counts": _status_counts(sections),
        "blockers": verdict.get("blockers", []),
        "unavailable_count": verdict.get("unavailable_items", 0),
    }


def _artifact_lines(payload: dict[str, Any]) -> list[str]:
    artifacts = [item for item in payload.get("evidence_artifacts", []) or [] if isinstance(item, dict)]
    if not artifacts:
        return ["No evidence artifacts were supplied. Missing artifacts are not treated as passing scans."]
    lines: list[str] = []
    for item in artifacts:
        affected = "affected score" if item.get("affects_score") else "no score lift"
        flags = []
        if item.get("missing"):
            flags.append("missing")
        if item.get("stale"):
            flags.append("stale")
        suffix = f"; {', '.join(flags)}" if flags else ""
        lines.append(f"{item.get('artifact_name')} from {item.get('workflow_name')} - {str(item.get('status') or 'unknown').upper()} ({affected}{suffix}): {item.get('summary')}")
    return lines


def markdown_report(payload: dict[str, Any]) -> str:
    payload = _guard_payload(payload)
    sections = [item for item in payload.get("sections", []) if isinstance(item, dict)]
    readiness = _delivery_readiness(payload)
    maturity = payload.get("maturity_signal") or {}
    repair_loop = payload.get("reparodynamics") or {}
    artifact_summary = payload.get("evidence_artifact_summary") or {}
    lines = [
        "# NICO Client-Ready Report Package",
        "",
        "**Powered by Reparodynamics**",
        "",
        f"Generated: {now_iso()}",
        f"Client: {payload.get('client_name') or 'Not specified'}",
        f"Project: {payload.get('project_name') or 'Not specified'}",
        f"Repository/source scope: {payload.get('repository') or payload.get('source_scope') or 'Not specified'}",
        "",
        "## Client Delivery Verdict",
        f"Verdict: **{readiness['verdict']}**",
        f"Confidence: **{readiness['confidence']}**",
        f"Maturity: **{maturity.get('level', 'Unknown')}** | Score: **{maturity.get('score', 'N/A')}**",
        f"Section counts: green={readiness['status_counts']['green']}, yellow={readiness['status_counts']['yellow']}, red={readiness['status_counts']['red']}, unavailable/gray={readiness['status_counts']['gray']}",
        "",
        "## Reparodynamic Repair Loop",
        f"Loop: {' -> '.join(repair_loop.get('loop', [])) if repair_loop else 'Not available'}",
        f"Detection strength: **{repair_loop.get('detection_strength', 'N/A')}**",
        f"Unavailable-evidence burden: **{repair_loop.get('unavailable_evidence_burden', 'N/A')}**",
        f"Repair pressure: **{repair_loop.get('repair_pressure', 'N/A')}**",
        f"Stabilization score: **{repair_loop.get('stabilization_score', 'N/A')}**",
        repair_loop.get("interpretation") or "Reparodynamic metrics require report sections with evidence confidence metadata.",
        "",
        "## Required Human Review",
        "Final delivery, roadmap commitments, resourcing decisions, and code changes require human review. Missing evidence is disclosed and is not treated as verified.",
        "",
        "## Evidence Artifacts",
        f"Summary: total={artifact_summary.get('total', 0)}, passed={artifact_summary.get('passed', 0)}, failed={artifact_summary.get('failed', 0)}, missing={artifact_summary.get('missing', 0)}, stale={artifact_summary.get('stale', 0)}, unavailable={artifact_summary.get('unavailable', 0)}, score-affecting={artifact_summary.get('score_affecting', 0)}.",
        artifact_summary.get("rule") or "Workflow presence alone does not improve scores; parsed artifact contents are required.",
    ]
    for line in _artifact_lines(payload):
        lines.append(f"- {_clean(line)}")
    lines += ["", "## Authorization Statement", payload.get("authorization_statement") or "Assessment output is valid only for explicitly authorized customer/project scope.", ""]
    if repair_loop.get("repair_queue"):
        lines += ["## Repair Queue"]
        for item in repair_loop.get("repair_queue", [])[:8]:
            lines.append(f"- {item.get('priority', 'normal').upper()}: {item.get('section')} ({item.get('status')}, confidence={item.get('confidence')}) - {item.get('reason')}")
        lines.append("")
    if readiness["blockers"]:
        lines += ["## Delivery Blockers / Review Notes"]
        for blocker in readiness["blockers"]:
            lines.append(f"- {blocker}")
        lines.append("")
    lines += ["## Executive Summary", payload.get("executive_summary") or "No executive summary returned.", "", "## Section Scorecard"]
    if sections:
        for item in sections:
            label = item.get("label") or item.get("id") or "Section"
            lines.append(f"- **{label}** - {str(item.get('status') or 'unknown').upper()} {item.get('score', 'N/A')}/100; confidence={item.get('confidence', 'unknown')}: {item.get('summary') or 'No summary returned.'}")
    else:
        lines.append("- No section scorecard was supplied.")
    lines += ["", "## Verified / Unverified Claims"]
    for item in sections:
        label = item.get("label") or item.get("id") or "Section"
        lines.append(f"### {label}")
        verified = item.get("verified_claims") or item.get("evidence") or []
        unverified = item.get("unverified_claims") or item.get("unavailable") or []
        lines.append("Verified/evidence-bound:")
        for claim in verified[:6] or ["No verified claim returned."]:
            lines.append(f"- {_clean(claim)}")
        lines.append("Unverified/degraded/unavailable:")
        for claim in unverified[:6] or ["No unverified claim returned."]:
            lines.append(f"- {_clean(claim)}")
    lines += ["", "## Findings and Risks"]
    findings = payload.get("findings", []) or []
    if findings:
        for item in findings:
            lines.append(f"- {_clean(item)}")
    elif sections:
        for item in sections:
            for finding in item.get("findings", []) or []:
                lines.append(f"- {_clean(finding)}")
    else:
        lines.append("- No findings returned.")
    lines += ["", "## Evidence Quality"]
    lines.append(json.dumps({"maturity_signal": maturity, "client_delivery_verdict": payload.get("client_delivery_verdict") or {}, "reparodynamics": repair_loop, "evidence_artifact_summary": artifact_summary, "truthfulness_rules": payload.get("truthfulness_rules") or [], "assessment_quality": payload.get("assessment_quality", "standard")}, indent=2))
    lines += ["", "## Unavailable Data Notes"]
    unavailable = list(payload.get("unavailable_data_notes", []) or [])
    for item in sections:
        for note in item.get("unavailable", []) or []:
            unavailable.append(f"{item.get('label') or item.get('id')}: {note}")
    for note in unavailable or ["No unavailable-data notes returned."]:
        lines.append(f"- {_clean(note)}")
    lines += ["", "## Recommended Action Plan"]
    for step in payload.get("next_steps", []) or payload.get("quick_wins", []) or ["Review evidence.", "Prioritize repair plan.", "Approve or reject any high-impact action."]:
        lines.append(f"- {_clean(step)}")
    return "\n".join(lines).strip() + "\n"


def html_report(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>NICO Report</title><style>body{{font-family:Arial,sans-serif;background:#f8fafc;color:#111827;margin:0}}main{{max-width:980px;margin:34px auto;padding:0 20px 50px}}.hero{{background:#0f172a;color:white;border-radius:28px;padding:30px;margin-bottom:22px}}.hero b{{color:#67e8f9;text-transform:uppercase;letter-spacing:.14em}}pre{{white-space:pre-wrap;background:white;border:1px solid #e5e7eb;border-radius:18px;padding:24px;line-height:1.55}}</style></head><body><main><section class=\"hero\"><b>NICO - Powered by Reparodynamics</b><h1>Client-Ready Report Package</h1><p>Evidence-bound assessment output. Human review required.</p></section><pre>{safe}</pre></main></body></html>"""


def build_report_package(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _guard_payload(payload)
    report_id = f"report_{uuid4().hex[:16]}"
    markdown = markdown_report(payload)
    package = {
        "status": "complete",
        "report_id": report_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "run_id": payload.get("run_id") or payload.get("assessment_id") or report_id,
        "delivery_readiness": _delivery_readiness(payload),
        "reparodynamics": payload.get("reparodynamics") or {},
        "evidence_artifact_summary": payload.get("evidence_artifact_summary") or {},
        "evidence_artifacts": payload.get("evidence_artifacts") or [],
        "formats": {"markdown": markdown, "html": html_report(markdown), "json": payload, "pdf": None},
        "unavailable_data_notes": ["PDF export is generated by the Express report path or a configured report worker; this package stores Markdown, HTML, and JSON."],
        "created_at": now_iso(),
    }
    STORE.put("reports", report_id, package)
    STORE.audit("report.created", {"report_id": report_id, "run_id": package["run_id"]}, customer_id=package["customer_id"], project_id=package["project_id"])
    return package


def get_report(run_id: str) -> dict[str, Any]:
    for report in STORE.list("reports"):
        if report.get("run_id") == run_id or report.get("report_id") == run_id:
            return report
    return {"status": "not_found", "run_id": run_id}


def export_report(run_id: str, export_format: str = "json") -> dict[str, Any]:
    report = get_report(run_id)
    if report.get("status") == "not_found":
        return report
    formats = report.get("formats", {})
    if export_format not in formats or formats.get(export_format) is None:
        return {"status": "unavailable", "run_id": run_id, "format": export_format, "available_formats": [key for key, value in formats.items() if value is not None]}
    return {"status": "complete", "run_id": run_id, "format": export_format, "content": formats[export_format]}
