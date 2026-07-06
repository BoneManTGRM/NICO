from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from nico.storage import STORE


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _status_counts(sections: list[Any]) -> dict[str, int]:
    counts = {"green": 0, "yellow": 0, "red": 0, "gray": 0, "unknown": 0}
    for item in sections:
        if not isinstance(item, dict):
            counts["unknown"] += 1
            continue
        status = str(item.get("status") or "unknown").lower()
        counts[status if status in counts else "unknown"] += 1
    return counts


def _delivery_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in payload.get("sections", []) if isinstance(item, dict)]
    counts = _status_counts(sections)
    unavailable = list(payload.get("unavailable_data_notes", []) or [])
    unavailable += [note for item in sections for note in item.get("unavailable", []) or []]
    blockers: list[str] = []
    if counts["red"]:
        blockers.append(f"{counts['red']} red section(s) require triage before client-final delivery.")
    if unavailable:
        blockers.append("Unavailable evidence must remain disclosed and reviewed.")
    if payload.get("assessment_quality") == "degraded_metadata":
        blockers.append("Metadata was degraded; rerun with authenticated source access before firm claims.")
    verdict = "review_ready" if not blockers else "human_review_required"
    return {"verdict": verdict, "status_counts": counts, "blockers": blockers, "unavailable_count": len(unavailable)}


def _section_line(item: dict[str, Any]) -> str:
    label = item.get("label") or item.get("id") or "Section"
    score = item.get("score", "N/A")
    status = str(item.get("status") or "unknown").upper()
    summary = item.get("summary") or "No summary returned."
    return f"- **{label}** - {status} {score}/100: {summary}"


def markdown_report(payload: dict[str, Any]) -> str:
    sections = [item for item in payload.get("sections", []) if isinstance(item, dict)]
    readiness = _delivery_readiness(payload)
    maturity = payload.get("maturity_signal") or {}
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
        f"Maturity: **{maturity.get('level', 'Unknown')}** | Score: **{maturity.get('score', 'N/A')}**",
        f"Section counts: green={readiness['status_counts']['green']}, yellow={readiness['status_counts']['yellow']}, red={readiness['status_counts']['red']}, unavailable/gray={readiness['status_counts']['gray']}",
        "",
        "## Required Human Review",
        "Final delivery, roadmap commitments, resourcing decisions, and code changes require human review. Missing evidence is disclosed and is not treated as verified.",
        "",
        "## Authorization Statement",
        payload.get("authorization_statement") or "Assessment output is valid only for explicitly authorized customer/project scope.",
        "",
    ]
    blockers = readiness.get("blockers") or []
    if blockers:
        lines += ["## Delivery Blockers / Review Notes"]
        for blocker in blockers:
            lines.append(f"- {blocker}")
        lines.append("")

    lines += [
        "## Executive Summary",
        payload.get("executive_summary") or "No executive summary returned.",
        "",
        "## Section Scorecard",
    ]
    if sections:
        for item in sections:
            lines.append(_section_line(item))
    else:
        lines.append("- No section scorecard was supplied.")

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
    lines.append(json.dumps({"maturity_signal": maturity, "evidence_readiness": payload.get("evidence_readiness") or {}, "assessment_quality": payload.get("assessment_quality", "standard")}, indent=2))

    lines += ["", "## Unavailable Data Notes"]
    unavailable = list(payload.get("unavailable_data_notes", []) or [])
    for item in sections:
        for note in item.get("unavailable", []) or []:
            unavailable.append(f"{item.get('label') or item.get('id')}: {note}")
    for note in unavailable or ["No unavailable-data notes returned."]:
        lines.append(f"- {_clean(note)}")

    lines += ["", "## Recommended Action Plan"]
    for step in payload.get("next_steps", []) or payload.get("quick_wins", []) or ["Review evidence.", "Prioritize repair plan.", "Approve or reject any production-impacting action."]:
        lines.append(f"- {_clean(step)}")

    lines += ["", "## Safety Boundary", "NICO does not automatically modify customer production systems, protected branches, deployments, secrets, or infrastructure. Suggested repairs remain recommendations until approved by a human reviewer."]
    return "\n".join(lines).strip() + "\n"


def html_report(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>NICO Report</title><style>body{{font-family:Arial,sans-serif;background:#f8fafc;color:#111827;margin:0}}main{{max-width:980px;margin:34px auto;padding:0 20px 50px}}.hero{{background:#0f172a;color:white;border-radius:28px;padding:30px;margin-bottom:22px}}.hero b{{color:#67e8f9;text-transform:uppercase;letter-spacing:.14em}}pre{{white-space:pre-wrap;background:white;border:1px solid #e5e7eb;border-radius:18px;padding:24px;line-height:1.55;box-shadow:0 18px 55px rgba(15,23,42,.08)}}footer{{color:#64748b;font-size:12px;margin-top:16px}}</style></head><body><main><section class=\"hero\"><b>NICO - Powered by Reparodynamics</b><h1>Client-Ready Report Package</h1><p>Evidence-bound assessment output. Human review required.</p></section><pre>{safe}</pre><footer>NICO reports are advisory until reviewed and approved.</footer></main></body></html>"""


def build_report_package(payload: dict[str, Any]) -> dict[str, Any]:
    report_id = f"report_{uuid4().hex[:16]}"
    markdown = markdown_report(payload)
    package = {
        "status": "complete",
        "report_id": report_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "run_id": payload.get("run_id") or payload.get("assessment_id") or report_id,
        "delivery_readiness": _delivery_readiness(payload),
        "formats": {
            "markdown": markdown,
            "html": html_report(markdown),
            "json": payload,
            "pdf": None,
        },
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
