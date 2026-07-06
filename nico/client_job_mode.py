from __future__ import annotations

import base64
import html
import json
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import uuid4

from nico.storage import STORE


EXPRESS_SCOPE = [
    "Code audit and recent development activity",
    "Library/dependency ecosystem health",
    "CI/CD reliability and release process",
    "Architecture and technical debt",
    "Maturity semaphore by audit area",
    "Velocity and complexity signal",
    "Strategic quick wins and medium-term action plan",
    "Resourcing recommendation",
]

ARTIFACT_EVIDENCE_PATTERNS = {
    "unverified_output": "The product artifact reports that the output is not verified.",
    "no_verified_picks": "No verified picks were available in the product artifact.",
    "provider_gate": "A provider/data-source gate blocked publishable output.",
    "current_provider_gate": "Current provider gate blocked publishable output.",
    "provider_not_matched": "Provider data did not match a current source row.",
    "data_unavailable": "Required product or market metrics were unavailable.",
    "research_only": "Final recommendation was research-only rather than client-publishable.",
    "enrichment_unverified": "Operational enrichment evidence was not verified.",
    "lineup_injury_unverified": "Lineup or injury evidence was not verified.",
    "snapshot_missing": "Live snapshot evidence was not returned.",
}

SUPPORTED_EXPORT_FORMATS = {"json", "markdown", "html", "pdf"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _contains(text: str, *needles: str) -> bool:
    value = text.lower()
    return any(needle.lower() in value for needle in needles)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def quote_facts(quote_text: str) -> dict[str, Any]:
    text = quote_text or ""
    facts = {
        "service_detected": "Express Technical Health Assessment" if _contains(text, "express technical health assessment") else "Unknown",
        "timeline": "2 weeks" if _contains(text, "2 weeks", "2 semanas") else "not detected",
        "price": "$4,500.00 USD + IVA" if _contains(text, "$4,500", "4500") else "not detected",
        "payment_terms": "50% upfront / 50% on final report" if _contains(text, "50%", "2,250") else "not detected",
        "client_responsibilities": [],
    }
    if _contains(text, "read-only", "solo lectura"):
        facts["client_responsibilities"].append("Read-only repository access")
    if _contains(text, "ci/cd", "pipelines"):
        facts["client_responsibilities"].append("CI/CD configuration and logs")
    if _contains(text, "documentacion tecnica", "documentación técnica", "technical documentation"):
        facts["client_responsibilities"].append("Technical documentation")
    if _contains(text, "q&a"):
        facts["client_responsibilities"].append("Q&A session with development or technical leadership")
    if _contains(text, "pm/lead"):
        facts["client_responsibilities"].append("Assigned PM or technical lead")
    return facts


def product_artifact_findings(product_evidence_text: str) -> list[dict[str, str]]:
    text = product_evidence_text or ""
    findings: list[dict[str, str]] = []
    checks = {
        "unverified_output": ("not verified", "no verified"),
        "no_verified_picks": ("no verified picks",),
        "provider_gate": ("provider gate", "source gate"),
        "current_provider_gate": ("current provider gate",),
        "provider_not_matched": ("provider not matched", "source not matched", "not matched to a live provider"),
        "data_unavailable": ("data unavailable", "metric unavailable", "status unavailable"),
        "research_only": ("research only",),
        "enrichment_unverified": ("not verified update", "verify before", "unverified update"),
        "lineup_injury_unverified": ("no verified lineup", "verify lineup", "injury update"),
        "snapshot_missing": ("no live snapshot", "no live team snapshot"),
    }
    for key, needles in checks.items():
        if _contains(text, *needles):
            severity = "high" if key in {"unverified_output", "no_verified_picks", "provider_gate", "current_provider_gate", "research_only"} else "medium"
            findings.append({"id": key, "finding": ARTIFACT_EVIDENCE_PATTERNS[key], "severity": severity})
    return findings


def deliverable_checklist(assessment: dict[str, Any] | None, scanner_attached: bool) -> list[dict[str, str]]:
    assessment = assessment or {}
    sections = {str(item.get("id") or item.get("label") or "").lower(): item for item in assessment.get("sections", []) if isinstance(item, dict)}
    unavailable_notes = assessment.get("unavailable_data_notes") or []

    def status_for(*keys: str) -> str:
        if not assessment:
            return "needs_evidence"
        if any(key in sections for key in keys):
            return "complete_with_review"
        if unavailable_notes:
            return "limited"
        return "needs_evidence"

    return [
        {"deliverable": "Code audit", "status": status_for("code_audit", "code audit"), "required_evidence": "Repository metadata, files, PR/commit patterns"},
        {"deliverable": "Library/dependency health", "status": "complete_with_review" if scanner_attached else status_for("dependency_health", "library ecosystem"), "required_evidence": "scanner evidence, lockfiles, dependency manifests"},
        {"deliverable": "CI/CD analysis", "status": status_for("ci_cd", "ci/cd"), "required_evidence": "Workflow files, logs, check history, deployment signals"},
        {"deliverable": "Architecture and technical debt", "status": status_for("architecture", "technical debt"), "required_evidence": "Repo structure, modules, report pipeline, API boundaries"},
        {"deliverable": "Product/report pipeline review", "status": "needs_human_review", "required_evidence": "Generated reports, provider-gate behavior, stale data checks"},
        {"deliverable": "Maturity semaphore", "status": "needs_human_review", "required_evidence": "NICO sections plus verified/unavailable evidence"},
        {"deliverable": "Action plan and quick wins", "status": "draftable", "required_evidence": "Findings ranked by impact and confidence"},
        {"deliverable": "Resourcing recommendation", "status": "draftable", "required_evidence": "Risk concentration, execution complexity, roadmap needs"},
        {"deliverable": "Client-ready package", "status": "human_review_required", "required_evidence": "Final factual review and signoff"},
    ]


def provider_gate_root_cause_prompts() -> list[str]:
    return [
        "Confirm API keys are loaded and health checks pass without exposing secrets.",
        "Trace provider-gate rules and log why each candidate row is rejected.",
        "Check whether saved rows are stale, duplicated, or disconnected from current provider data.",
        "Verify source freshness, metric availability, enrichment data, and report timestamps before export.",
        "Ensure report exports drop unavailable sections or mark them unavailable instead of publishing placeholders.",
        "Add evidence IDs for source, timestamp, provider, and rejection reason.",
    ]


def build_client_job_package(payload: dict[str, Any]) -> dict[str, Any]:
    quote_text = str(payload.get("quote_text") or "")
    product_evidence_text = str(payload.get("product_evidence_text") or "")
    assessment = payload.get("assessment") if isinstance(payload.get("assessment"), dict) else {}
    scanner_attached = bool(
        assessment.get("worker_evidence_attachment", {}).get("status") == "complete"
        or assessment.get("evidence_readiness", {}).get("scanner_worker_attached")
        or assessment.get("evidence_readiness", {}).get("existing_worker_evidence_attached")
    )
    findings = product_artifact_findings(product_evidence_text)
    job_id = str(payload.get("job_id") or f"client_job_{uuid4().hex[:16]}")
    return {
        "status": "ok",
        "mode": "client_job_mode_v8",
        "job_id": job_id,
        "customer_id": payload.get("customer_id") or "default_customer",
        "project_id": payload.get("project_id") or "default_project",
        "client_name": payload.get("client_name") or "Client",
        "project_name": payload.get("project_name") or "Project",
        "repository": payload.get("repository") or "",
        "service_scope": "Express Technical Health Assessment",
        "source_scope": payload.get("source_scope") or "authorized technical assessment",
        "authorization_statement": payload.get("authorization_statement") or "Client package is valid only for explicitly authorized customer/project scope.",
        "scope_remap_note": "For non-mobile products, map the quoted iOS/Android audit categories to the real backend, frontend, CI/CD, data-provider, and report-export surfaces.",
        "quote_facts": quote_facts(quote_text),
        "express_scope": EXPRESS_SCOPE,
        "product_artifact_findings": findings,
        "provider_gate_root_cause_prompts": provider_gate_root_cause_prompts() if findings else [],
        "deliverable_checklist": deliverable_checklist(assessment, scanner_attached),
        "report_outline": [
            "Executive Summary",
            "Technical Maturity Semaphore",
            "Evidence Sources and Limitations",
            "Code Audit",
            "Library / Dependency Health",
            "CI/CD Analysis",
            "Architecture and Technical Debt",
            "Product Report Pipeline Findings",
            "Verified / Unverified Claims",
            "Unavailable Evidence",
            "Quick Wins",
            "30/60/90-Day Action Plan",
            "Resourcing Recommendation",
            "Human Review Required",
        ],
        "assessment": assessment,
        "human_review_required": True,
        "delivery_verdict": "draft_ready_for_human_review" if assessment else "needs_scanner_express_evidence",
        "available_export_formats": sorted(SUPPORTED_EXPORT_FORMATS),
        "created_at": now_iso(),
    }


def create_client_job_package(payload: dict[str, Any]) -> dict[str, Any]:
    package = build_client_job_package(payload)
    STORE.put("client_jobs", package["job_id"], package)
    STORE.audit("client_job.created", {"job_id": package["job_id"], "delivery_verdict": package["delivery_verdict"]}, customer_id=package["customer_id"], project_id=package["project_id"])
    return package


def get_client_job_package(job_id: str) -> dict[str, Any]:
    package = STORE.get("client_jobs", job_id)
    if not package:
        return {"status": "not_found", "job_id": job_id}
    return package


def client_job_markdown(package: dict[str, Any]) -> str:
    lines = [
        "# NICO Client Job Package",
        "",
        "**Powered by Reparodynamics**",
        "",
        f"Generated: {now_iso()}",
        f"Job ID: {package.get('job_id')}",
        f"Client: {package.get('client_name')}",
        f"Project: {package.get('project_name')}",
        f"Repository/source: {package.get('repository') or package.get('source_scope')}",
        "",
        "## Delivery Verdict",
        f"Verdict: **{package.get('delivery_verdict')}**",
        f"Human review required: **{package.get('human_review_required')}**",
        "",
        "## Authorization Statement",
        _clean(package.get("authorization_statement")),
        "",
        "## Quote Facts",
    ]
    quote = package.get("quote_facts") or {}
    for key, value in quote.items():
        lines.append(f"- **{key}**: {_clean(value)}")
    lines += ["", "## Express Scope"]
    for item in package.get("express_scope") or []:
        lines.append(f"- {_clean(item)}")
    lines += ["", "## Deliverable Checklist"]
    for item in package.get("deliverable_checklist") or []:
        lines.append(f"- **{item.get('deliverable')}**: {item.get('status')} — {_clean(item.get('required_evidence'))}")
    lines += ["", "## Product Artifact Findings"]
    for item in package.get("product_artifact_findings") or [{"finding": "No product artifact findings returned.", "severity": "none"}]:
        lines.append(f"- **{item.get('severity')}**: {_clean(item.get('finding'))}")
    lines += ["", "## Root-Cause Prompts"]
    for item in package.get("provider_gate_root_cause_prompts") or ["No root-cause prompts generated."]:
        lines.append(f"- {_clean(item)}")
    lines += ["", "## Report Outline"]
    for item in package.get("report_outline") or []:
        lines.append(f"- {_clean(item)}")
    lines += ["", "## Required Human Review", "This package is a draft until a qualified human reviewer validates evidence, unavailable data, findings, and delivery language."]
    return "\n".join(lines).strip() + "\n"


def client_job_html(package: dict[str, Any]) -> str:
    safe = html.escape(client_job_markdown(package))
    return f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>NICO Client Job Package</title><style>body{{font-family:Arial,sans-serif;background:#f8fafc;color:#111827;margin:0}}main{{max-width:980px;margin:34px auto;padding:0 20px 50px}}.hero{{background:#0f172a;color:white;border-radius:28px;padding:30px;margin-bottom:22px}}.hero b{{color:#67e8f9;text-transform:uppercase;letter-spacing:.14em}}pre{{white-space:pre-wrap;background:white;border:1px solid #e5e7eb;border-radius:18px;padding:24px;line-height:1.55}}</style></head><body><main><section class=\"hero\"><b>NICO - Powered by Reparodynamics</b><h1>Client Job Package</h1><p>Evidence-bound draft package. Human review required.</p></section><pre>{safe}</pre></main></body></html>"""


def client_job_pdf_base64(package: dict[str, Any]) -> str:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 54
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(54, y, "NICO Client Job Package")
    y -= 24
    pdf.setFont("Helvetica", 9)
    for raw_line in client_job_markdown(package).splitlines():
        line = raw_line.replace("**", "")
        if not line:
            y -= 8
            continue
        if y < 54:
            pdf.showPage()
            pdf.setFont("Helvetica", 9)
            y = height - 54
        pdf.drawString(54, y, line[:110])
        y -= 12
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def render_client_job_export(package: dict[str, Any], export_format: str = "json") -> dict[str, Any]:
    fmt = (export_format or "json").lower()
    if fmt not in SUPPORTED_EXPORT_FORMATS:
        return {"status": "unavailable", "job_id": package.get("job_id"), "format": fmt, "available_formats": sorted(SUPPORTED_EXPORT_FORMATS)}
    filename = f"{package.get('job_id', 'client_job')}.{ 'md' if fmt == 'markdown' else fmt }"
    if fmt == "json":
        rendered = {"content": json.dumps(package, indent=2), "mime_type": "application/json"}
    elif fmt == "markdown":
        rendered = {"content": client_job_markdown(package), "mime_type": "text/markdown"}
    elif fmt == "html":
        rendered = {"content": client_job_html(package), "mime_type": "text/html"}
    else:
        rendered = {"content_base64": client_job_pdf_base64(package), "mime_type": "application/pdf"}
    export_id = f"client_job_export_{uuid4().hex[:16]}"
    result = {
        "status": "complete",
        "export_id": export_id,
        "job_id": package.get("job_id"),
        "format": fmt,
        "filename": filename,
        "human_review_required": True,
        "created_at": now_iso(),
        **rendered,
    }
    STORE.put("client_job_exports", export_id, result)
    STORE.audit("client_job.exported", {"job_id": package.get("job_id"), "export_id": export_id, "format": fmt}, customer_id=package.get("customer_id"), project_id=package.get("project_id"))
    return result


def export_client_job_package(job_id: str, export_format: str = "json") -> dict[str, Any]:
    package = get_client_job_package(job_id)
    if package.get("status") == "not_found":
        return package
    return render_client_job_export(package, export_format)


def export_client_job_payload(payload: dict[str, Any], export_format: str = "json") -> dict[str, Any]:
    package = create_client_job_package(payload)
    return render_client_job_export(package, export_format)


def list_client_job_exports(job_id: str) -> dict[str, Any]:
    exports = [item for item in STORE.list("client_job_exports") if item.get("job_id") == job_id]
    return {"status": "ok", "job_id": job_id, "exports": exports, "available_formats": sorted(SUPPORTED_EXPORT_FORMATS)}
