from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from typing import Any

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from nico.admin_security import require_admin_write
from nico.mid_assessment_runs import load_mid_assessment_run
from nico.mid_review_by_exception import build_mid_review_packet
from nico.storage import STORE, StorageAdapter, utc_now

MID_REPORT_VERSION = "mid-assessment-final-pending-approval-v2"
MID_REPORT_PATH = "mid_run"
MID_REPORT_TYPE = "mid_assessment"
DRAFT_LABEL = "FINAL REPORT - PENDING HUMAN APPROVAL"

PAGE_WIDTH, PAGE_HEIGHT = LETTER
LEFT = 54
RIGHT = 54
TOP = 58
BOTTOM = 52
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _list(value) if str(item).strip()]


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "mid-assessment"))
    return cleaned.strip("-._") or "mid-assessment"


def _source_identity(record: dict[str, Any], packet: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    coverage = _dict(truth.get("evidence_coverage"))
    return {
        "report_version": MID_REPORT_VERSION,
        "report_type": MID_REPORT_TYPE,
        "report_path": MID_REPORT_PATH,
        "run_id": record.get("run_id") or "",
        "customer_id": record.get("customer_id") or "default_customer",
        "project_id": record.get("project_id") or "default_project",
        "repository": record.get("repository") or "",
        "snapshot_id": record.get("snapshot_id") or "",
        "snapshot_commit_sha": record.get("snapshot_commit_sha") or "",
        "review_packet_id": packet.get("review_packet_id") or "",
        "review_packet_sha256": packet.get("review_packet_sha256") or "",
        "truth_version": truth.get("version") or "",
        "truth_sha256": _canonical_hash(truth),
        "evidence_coverage_percent": coverage.get("percent"),
        "evidence_coverage_numerator": coverage.get("numerator"),
        "evidence_coverage_denominator": coverage.get("denominator"),
    }


def _report_id(identity: dict[str, Any]) -> str:
    return f"mid_report_{_canonical_hash(identity)[:24]}"


def _section_payload(section: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": section.get("id") or "unknown",
        "label": section.get("label") or str(section.get("id") or "Section").replace("_", " ").title(),
        "score": section.get("score"),
        "truth_status": section.get("truth_status") or "Unavailable",
        "summary": section.get("summary") or "No supported conclusion was available.",
        "evidence": _text_list(section.get("evidence")),
        "findings": _text_list(section.get("findings")),
        "unavailable": _text_list(section.get("unavailable")),
        "missing_evidence_sources": _text_list(section.get("missing_evidence_sources")),
        "failed_evidence_tools": _text_list(section.get("failed_evidence_tools")),
        "source_classification": section.get("source_classification") or "repository_evidence",
        "direct_repository_proof": section.get("direct_repository_proof", True),
        "human_review_required": bool(section.get("human_review_required")),
        "unsupported_claims_permitted": False,
    }


def _report_payload(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
    response = _dict(record.get("response"))
    truth = _dict(response.get("mid_truth_status"))
    sections = [_section_payload(item) for item in _list(truth.get("sections")) if isinstance(item, dict)]
    request = _dict(record.get("request"))
    coverage = _dict(truth.get("evidence_coverage"))
    return {
        "status": "final_pending_human_approval",
        "report_version": MID_REPORT_VERSION,
        "report_type": MID_REPORT_TYPE,
        "report_path": MID_REPORT_PATH,
        "title": "NICO MID ASSESSMENT",
        "subtitle": "Complete evidence-bound technical assessment",
        "draft_label": DRAFT_LABEL,
        "report_id": _report_id(identity),
        "run_id": identity["run_id"],
        "customer_id": identity["customer_id"],
        "project_id": identity["project_id"],
        "client_name": request.get("client_name") or "",
        "project_name": request.get("project_name") or "",
        "repository": identity["repository"],
        "snapshot_id": identity["snapshot_id"],
        "snapshot_commit_sha": identity["snapshot_commit_sha"],
        "generated_at": generated_at,
        "source_identity": identity,
        "source_identity_sha256": _canonical_hash(identity),
        "review_packet": {
            "review_packet_id": packet.get("review_packet_id") or "",
            "review_packet_sha256": packet.get("review_packet_sha256") or "",
            "summary": deepcopy(packet.get("summary") or {}),
            "exceptions": deepcopy(packet.get("exceptions") or []),
            "verified_sections": deepcopy(packet.get("verified_sections") or []),
        },
        "evidence_coverage": deepcopy(coverage),
        "sections": sections,
        "executive_summary": {
            "assessment_status": record.get("status") or "unknown",
            "section_count": len(sections),
            "verified_sections": int(_dict(truth.get("summary")).get("verified") or 0),
            "verified_with_limitations": int(_dict(truth.get("summary")).get("verified_with_limitations") or 0),
            "unavailable_sections": int(_dict(truth.get("summary")).get("unavailable") or 0),
            "failed_sections": int(_dict(truth.get("summary")).get("failed") or 0),
            "human_review_sections": int(_dict(truth.get("summary")).get("human_review_required") or 0),
            "items_requiring_review": int(_dict(packet.get("summary")).get("items_requiring_review") or 0),
            "unsupported_claims_permitted": 0,
        },
        "disclosures": [
            "This is a complete final assessment report pending required human approval; client delivery remains blocked until approval.",
            "Every code-based section is bound to the captured repository commit shown in this report.",
            "Commit, pull-request, CI job, and deployment history is time-window operational evidence and is identified separately from exact-commit code evidence.",
            "User-submitted external context is not direct repository proof and cannot change a score without human validation.",
            "Unavailable or failed evidence is not represented as zero findings, a healthy result, or a passed control.",
            "A clean scanner result does not prove that no vulnerability exists.",
            "Unsupported claims permitted: 0.",
        ],
        "human_review_required": True,
        "approval_required": True,
        "client_delivery_allowed": False,
        "approved": False,
        "unsupported_claims_permitted": 0,
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# NICO MID ASSESSMENT",
        "",
        f"**{DRAFT_LABEL}**",
        "",
        f"- Report ID: `{payload['report_id']}`",
        f"- Mid run ID: `{payload['run_id']}`",
        f"- Repository: `{payload['repository']}`",
        f"- Snapshot commit: `{payload['snapshot_commit_sha']}`",
        f"- Review packet: `{payload['review_packet']['review_packet_id']}`",
        f"- Generated: {payload['generated_at']}",
        "",
        "## Executive summary",
        "",
    ]
    summary = payload["executive_summary"]
    for key, value in summary.items():
        lines.append(f"- {str(key).replace('_', ' ').title()}: {value}")
    coverage = payload["evidence_coverage"]
    lines.extend([
        "",
        "## Automated evidence coverage",
        "",
        f"**{coverage.get('percent', 0)}%** ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)} explicit evidence units)",
        "",
        str(coverage.get("method") or "Coverage was calculated from explicit evidence units."),
    ])
    for section in payload["sections"]:
        score = "Not scored" if section.get("score") is None else f"{section['score']}/100"
        lines.extend([
            "",
            f"## {section['label']}",
            "",
            f"- Truth status: **{section['truth_status']}**",
            f"- Score: {score}",
            f"- Source: {section['source_classification']}",
            f"- Direct repository proof: {section['direct_repository_proof']}",
            "",
            section["summary"],
        ])
        if section["evidence"]:
            lines.extend(["", "### Evidence"] + [f"- {item}" for item in section["evidence"]])
        limitations = section["unavailable"] + section["missing_evidence_sources"] + section["failed_evidence_tools"]
        if limitations:
            lines.extend(["", "### Limitations / unavailable evidence"] + [f"- {item}" for item in limitations])
    lines.extend(["", "## Review by exception", ""])
    exceptions = payload["review_packet"]["exceptions"]
    if exceptions:
        for item in exceptions:
            lines.extend([
                f"### {item.get('title') or item.get('category')}",
                "",
                f"- Severity: {item.get('severity') or 'medium'}",
                f"- Category: {item.get('category') or 'unknown'}",
                f"- Section: {item.get('section_id') or 'unknown'}",
                f"- Score-changing: {bool(item.get('score_change_material'))}",
                f"- Inference-based: {bool(item.get('inference_based'))}",
                "",
                str(item.get("reason") or "Human review required."),
                "",
            ])
    else:
        lines.append("No review exceptions were generated; human approval is still required.")
    lines.extend(["", "## Disclosures", ""] + [f"- {item}" for item in payload["disclosures"]])
    lines.extend([
        "",
        "## Integrity identity",
        "",
        f"- Source identity SHA-256: `{payload['source_identity_sha256']}`",
        f"- Review packet SHA-256: `{payload['review_packet']['review_packet_sha256']}`",
        f"- Snapshot commit SHA: `{payload['snapshot_commit_sha']}`",
    ])
    return "\n".join(lines).strip() + "\n"


def _html(payload: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value or ""))

    sections = []
    for section in payload["sections"]:
        limitations = section["unavailable"] + section["missing_evidence_sources"] + section["failed_evidence_tools"]
        evidence_html = "".join(f"<li>{esc(item)}</li>" for item in section["evidence"]) or "<li>No direct evidence item was retained.</li>"
        limit_html = "".join(f"<li>{esc(item)}</li>" for item in limitations)
        score = "Not scored" if section.get("score") is None else f"{section['score']}/100"
        sections.append(
            f"<section><h2>{esc(section['label'])}</h2><p><b>Truth status:</b> {esc(section['truth_status'])} · <b>Score:</b> {esc(score)}</p>"
            f"<p>{esc(section['summary'])}</p><h3>Evidence</h3><ul>{evidence_html}</ul>"
            + (f"<h3>Limitations / unavailable evidence</h3><ul>{limit_html}</ul>" if limit_html else "")
            + "</section>"
        )
    exception_html = "".join(
        f"<article><h3>{esc(item.get('title') or item.get('category'))}</h3><p><b>{esc(item.get('severity'))}</b> · {esc(item.get('category'))}</p><p>{esc(item.get('reason'))}</p></article>"
        for item in payload["review_packet"]["exceptions"]
    ) or "<p>No review exceptions were generated; human approval is still required.</p>"
    disclosures = "".join(f"<li>{esc(item)}</li>" for item in payload["disclosures"])
    coverage = payload["evidence_coverage"]
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>NICO Mid Assessment</title><style>
body{{font-family:Arial,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;color:#17202a;line-height:1.5}}h1,h2{{color:#101820}}.draft{{padding:12px;border:2px solid #a32121;background:#fff2f2;font-weight:bold}}section,article{{border-top:1px solid #d9dee3;padding:18px 0}}code{{word-break:break-all}}.meta{{background:#f3f5f7;padding:14px}}
</style></head><body><h1>NICO MID ASSESSMENT</h1><p class=\"draft\">{esc(DRAFT_LABEL)}</p><div class=\"meta\"><p>Report ID: <code>{esc(payload['report_id'])}</code><br>Mid run: <code>{esc(payload['run_id'])}</code><br>Repository: <code>{esc(payload['repository'])}</code><br>Snapshot: <code>{esc(payload['snapshot_commit_sha'])}</code></p></div><h2>Automated evidence coverage</h2><p><b>{esc(coverage.get('percent'))}%</b> ({esc(coverage.get('numerator'))}/{esc(coverage.get('denominator'))})</p><p>{esc(coverage.get('method'))}</p>{''.join(sections)}<section><h2>Review by exception</h2>{exception_html}</section><section><h2>Disclosures</h2><ul>{disclosures}</ul></section><section><h2>Integrity identity</h2><p>Source identity SHA-256: <code>{esc(payload['source_identity_sha256'])}</code><br>Review packet SHA-256: <code>{esc(payload['review_packet']['review_packet_sha256'])}</code></p></section></body></html>"""


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = str(text or "").replace("\n", " ").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _pdf(payload: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=LETTER, pageCompression=1, invariant=1)
    page_number = 0
    y = PAGE_HEIGHT - TOP

    def page_header() -> None:
        nonlocal page_number, y
        page_number += 1
        canvas.setFillColorRGB(0.64, 0.08, 0.08)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(LEFT, PAGE_HEIGHT - 28, DRAFT_LABEL)
        canvas.setFillColorRGB(0.15, 0.18, 0.21)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_WIDTH - RIGHT, 24, f"NICO Mid Assessment · Page {page_number}")
        canvas.setStrokeColorRGB(0.82, 0.84, 0.87)
        canvas.line(LEFT, PAGE_HEIGHT - 36, PAGE_WIDTH - RIGHT, PAGE_HEIGHT - 36)
        canvas.line(LEFT, 36, PAGE_WIDTH - RIGHT, 36)
        y = PAGE_HEIGHT - TOP

    def new_page() -> None:
        canvas.showPage()
        page_header()

    def ensure(height: float) -> None:
        nonlocal y
        if y - height < BOTTOM:
            new_page()

    def paragraph(text: Any, *, font: str = "Helvetica", size: float = 9.2, leading: float = 12, indent: float = 0, before: float = 0, after: float = 4) -> None:
        nonlocal y
        lines = _wrap(str(text or ""), font, size, CONTENT_WIDTH - indent)
        ensure(before + len(lines) * leading + after)
        y -= before
        canvas.setFont(font, size)
        canvas.setFillColorRGB(0.12, 0.15, 0.18)
        for line in lines:
            canvas.drawString(LEFT + indent, y, line)
            y -= leading
        y -= after

    def heading(text: str, level: int = 2) -> None:
        nonlocal y
        size = 18 if level == 1 else 13 if level == 2 else 10.5
        leading = size + 4
        ensure(leading + 8)
        y -= 5
        canvas.setFillColorRGB(0.05, 0.18, 0.28)
        canvas.setFont("Helvetica-Bold", size)
        for line in _wrap(text, "Helvetica-Bold", size, CONTENT_WIDTH):
            canvas.drawString(LEFT, y, line)
            y -= leading
        y -= 3

    def bullet(text: str) -> None:
        nonlocal y
        lines = _wrap(text, "Helvetica", 8.8, CONTENT_WIDTH - 16)
        ensure(len(lines) * 11 + 3)
        canvas.setFont("Helvetica", 8.8)
        canvas.setFillColorRGB(0.12, 0.15, 0.18)
        canvas.drawString(LEFT + 2, y, "-")
        for line in lines:
            canvas.drawString(LEFT + 14, y, line)
            y -= 11
        y -= 2

    page_header()
    heading("NICO MID ASSESSMENT", 1)
    paragraph("Complete evidence-bound technical assessment", font="Helvetica-Bold", size=11, leading=14)
    paragraph(f"Client: {payload.get('client_name') or 'Not provided'} · Project: {payload.get('project_name') or 'Not provided'}")
    paragraph(f"Repository: {payload['repository']}")
    paragraph(f"Mid run: {payload['run_id']}")
    paragraph(f"Snapshot commit: {payload['snapshot_commit_sha']}", size=8.2)
    paragraph(f"Review packet: {payload['review_packet']['review_packet_id']}", size=8.2)
    paragraph(f"Generated: {payload['generated_at']}")
    heading("Executive summary")
    for key, value in payload["executive_summary"].items():
        bullet(f"{str(key).replace('_', ' ').title()}: {value}")
    coverage = payload["evidence_coverage"]
    heading("Automated evidence coverage")
    paragraph(f"{coverage.get('percent', 0)}% ({coverage.get('numerator', 0)}/{coverage.get('denominator', 0)} explicit evidence units)", font="Helvetica-Bold", size=12)
    paragraph(coverage.get("method") or "Coverage was calculated from explicit evidence units.")

    heading("Assessment sections")
    for section in payload["sections"]:
        heading(str(section["label"]), 3)
        score = "Not scored" if section.get("score") is None else f"{section['score']}/100"
        paragraph(f"Truth status: {section['truth_status']} · Score: {score}", font="Helvetica-Bold")
        paragraph(section["summary"])
        if section["evidence"]:
            paragraph("Evidence", font="Helvetica-Bold", before=2, after=2)
            for item in section["evidence"][:12]:
                bullet(item)
        limitations = section["unavailable"] + section["missing_evidence_sources"] + section["failed_evidence_tools"]
        if limitations:
            paragraph("Limitations / unavailable evidence", font="Helvetica-Bold", before=2, after=2)
            for item in limitations[:12]:
                bullet(item)

    heading("Review by exception")
    exceptions = payload["review_packet"]["exceptions"]
    if exceptions:
        for item in exceptions:
            heading(str(item.get("title") or item.get("category") or "Review item"), 3)
            paragraph(f"Severity: {item.get('severity') or 'medium'} · Category: {item.get('category') or 'unknown'}", font="Helvetica-Bold")
            paragraph(item.get("reason") or "Human review required.")
            for blocker in _text_list(item.get("blockers"))[:8]:
                bullet(f"Blocker: {blocker}")
    else:
        paragraph("No review exceptions were generated; human approval is still required.")

    heading("Disclosures")
    for disclosure in payload["disclosures"]:
        bullet(disclosure)
    heading("Integrity identity")
    paragraph(f"Source identity SHA-256: {payload['source_identity_sha256']}", size=8)
    paragraph(f"Review packet SHA-256: {payload['review_packet']['review_packet_sha256']}", size=8)
    paragraph(f"Snapshot commit SHA: {payload['snapshot_commit_sha']}", size=8)
    canvas.save()
    return buffer.getvalue()


def _valid_existing(report: dict[str, Any], identity: dict[str, Any]) -> bool:
    if report.get("record_type") != "mid_assessment_report" or report.get("status") != "complete":
        return False
    if report.get("source_identity") != identity:
        return False
    formats = _dict(report.get("formats"))
    try:
        pdf = base64.b64decode(str(formats.get("pdf") or ""), validate=True)
    except Exception:
        return False
    return bool(pdf.startswith(b"%PDF") and hashlib.sha256(pdf).hexdigest() == report.get("pdf_sha256"))


def generate_mid_draft_report(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    """Generate one professional final report pending approval, bound to the current review packet."""

    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to generate a final report pending approval.", "admin_write": admin}
    active = _store(store)
    record = load_mid_assessment_run(str(run_id or ""), store=active)
    if not record:
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    if str(record.get("customer_id") or "default_customer") != str(customer_id) or str(record.get("project_id") or "default_project") != str(project_id):
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    if record.get("status") != "complete":
        return {"status": "blocked", "error": "The assessment run must complete before its final report can be generated.", "run_status": record.get("status") or "unknown"}

    response = _dict(record.get("response"))
    truth = _dict(response.get("mid_truth_status"))
    if not truth.get("sections") or int(_dict(truth.get("summary")).get("unsupported_claims_permitted") or truth.get("unsupported_claims_permitted") or 0) != 0:
        return {"status": "blocked", "error": "The Mid truth model is unavailable or permits unsupported claims."}
    packet = build_mid_review_packet(run_id, customer_id, project_id, admin_token=admin_token, store=active)
    if packet.get("status") != "ready_for_review":
        return {"status": "blocked", "error": "A verified Mid review packet is required before report generation.", "review_packet": packet}

    identity = _source_identity(record, packet, truth)
    report_id = _report_id(identity)
    existing = active.get("reports", report_id)
    if isinstance(existing, dict) and _valid_existing(existing, identity):
        reused = deepcopy(existing)
        reused["idempotent_reuse"] = True
        return reused

    generated_at = utc_now()
    payload = _report_payload(record, packet, identity, generated_at)
    markdown = _markdown(payload)
    html_report = _html(payload)
    try:
        pdf = _pdf(payload)
    except Exception as exc:
        return {"status": "blocked", "error": f"Final report PDF rendering failed: {type(exc).__name__}."}
    if not pdf.startswith(b"%PDF"):
        return {"status": "blocked", "error": "Final report PDF rendering did not produce a valid PDF."}
    pdf_hash = hashlib.sha256(pdf).hexdigest()
    filename = f"nico-mid-assessment-{_safe_filename(record.get('repository') or 'repository')}-{_safe_filename(run_id)}-FINAL-PENDING-APPROVAL.pdf"
    report = {
        "record_type": "mid_assessment_report",
        "status": "complete",
        "draft_status": "human_review_required",
        "report_version": MID_REPORT_VERSION,
        "report_type": MID_REPORT_TYPE,
        "report_path": MID_REPORT_PATH,
        "report_id": report_id,
        "run_id": run_id,
        "customer_id": customer_id,
        "project_id": project_id,
        "repository": record.get("repository") or "",
        "snapshot_id": record.get("snapshot_id") or "",
        "snapshot_commit_sha": record.get("snapshot_commit_sha") or "",
        "review_packet_id": packet.get("review_packet_id") or "",
        "review_packet_sha256": packet.get("review_packet_sha256") or "",
        "source_identity": identity,
        "source_identity_sha256": payload["source_identity_sha256"],
        "pdf_sha256": pdf_hash,
        "pdf_filename": filename,
        "generated_at": generated_at,
        "formats": {
            "json": payload,
            "markdown": markdown,
            "html": html_report,
            "pdf": base64.b64encode(pdf).decode("ascii"),
        },
        "human_review_required": True,
        "approval_required": True,
        "client_delivery_allowed": False,
        "approved": False,
        "unsupported_claims_permitted": 0,
        "idempotent_reuse": False,
    }
    active.put("reports", report_id, report)
    updated = deepcopy(record)
    updated["report_id"] = report_id
    updated["updated_at"] = utc_now()
    retained_response = deepcopy(_dict(updated.get("response")))
    retained_response["mid_report"] = {
        "status": "complete",
        "report_id": report_id,
        "report_path": MID_REPORT_PATH,
        "report_version": MID_REPORT_VERSION,
        "pdf_sha256": pdf_hash,
        "pdf_filename": filename,
        "review_packet_id": packet.get("review_packet_id") or "",
        "review_packet_sha256": packet.get("review_packet_sha256") or "",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    updated["response"] = retained_response
    active.put("assessment_runs", run_id, updated)
    active.audit(
        "mid.draft_report_generated",
        {
            "report_id": report_id,
            "run_id": run_id,
            "snapshot_id": record.get("snapshot_id") or "",
            "snapshot_commit_sha": record.get("snapshot_commit_sha") or "",
            "review_packet_id": packet.get("review_packet_id") or "",
            "review_packet_sha256": packet.get("review_packet_sha256") or "",
            "source_identity_sha256": payload["source_identity_sha256"],
            "pdf_sha256": pdf_hash,
            "client_delivery_allowed": False,
        },
        customer_id=customer_id,
        project_id=project_id,
    )
    return report
