from __future__ import annotations

import base64
import csv
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Iterable, Mapping

from pypdf import PdfReader, PdfWriter

VERSION = "nico.comprehensive-artifact-manifest-approval.v1"
MANIFEST_SCHEMA = "nico.comprehensive-artifact-manifest.v1"
APPROVAL_SCHEMA = "nico.comprehensive-exact-artifact-approval.v1"
MAX_CLIENT_PDF_PAGES = 60

_FINALIZER_MARKER = "__nico_artifact_manifest_finalizer_v1__"
_GATE_MARKER = "__nico_artifact_manifest_gate_v1__"
_VALIDATION_MARKER = "__nico_artifact_manifest_validation_v1__"
_REQUEST_MARKER = "__nico_artifact_manifest_request_v1__"
_TRANSITION_MARKER = "__nico_artifact_manifest_transition_v1__"


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_filename(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", _text(value, 300)).strip("-._")
    return cleaned or fallback


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(dict(item)) for item in value or [] if isinstance(item, Mapping)]


def _csv_bytes(records: list[dict[str, Any]], fields: list[str]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in records:
        row: dict[str, Any] = {}
        for field in fields:
            value = item.get(field)
            if isinstance(value, (dict, list, tuple)):
                row[field] = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
            elif value is None:
                row[field] = ""
            else:
                row[field] = value
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _canonical_identity(canonical: Mapping[str, Any]) -> dict[str, str]:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    return {
        "repository": _text(identity.get("repository") or canonical.get("repository"), 400),
        "commit_sha": _text(identity.get("commit_sha") or canonical.get("commit_sha"), 120),
        "run_id": _text(identity.get("run_id") or canonical.get("run_id"), 180),
        "customer_id": _text(identity.get("customer_id") or canonical.get("customer_id"), 180),
        "project_id": _text(identity.get("project_id") or canonical.get("project_id"), 180),
        "evidence_ledger_id": _text(
            identity.get("evidence_ledger_id") or canonical.get("evidence_ledger_id"),
            180,
        ),
        "generation_timestamp": _text(
            identity.get("generated_at")
            or identity.get("generation_timestamp")
            or canonical.get("generated_at"),
            180,
        ),
        "report_language": _text(
            identity.get("report_language")
            or canonical.get("report_language")
            or "en",
            40,
        ),
    }


def _lifecycle() -> dict[str, Any]:
    return {
        "report_finality": "automated_draft",
        "automated_status": "complete",
        "client_review_package_status": "ready",
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
        "review_package_ready": True,
        "human_approval_required": True,
        "client_delivery_allowed": False,
    }


def _pending_approval_record() -> dict[str, Any]:
    return {
        "artifact_schema": APPROVAL_SCHEMA,
        "reviewer_identity": None,
        "reviewer_role": None,
        "reviewer_authorized": False,
        "review_timestamp": None,
        "decision": "pending",
        "residual_risk_acceptance": None,
        "approved_pdf_sha256": None,
        "approved_json_sha256": None,
        "evidence_manifest_sha256": None,
        "approval_record_id": None,
        "reviewer_notes": None,
        "exact_artifact_approval_required": True,
        "client_delivery_allowed": False,
    }


def _candidate_register(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    register = assessment.get("canonical_scanner_finding_register")
    if not isinstance(register, Mapping):
        register = canonical.get("canonical_scanner_finding_register")
    return deepcopy(dict(register)) if isinstance(register, Mapping) else {}


def _finding_register(canonical: Mapping[str, Any]) -> dict[str, Any]:
    register = canonical.get("client_finding_remediation_register")
    return deepcopy(dict(register)) if isinstance(register, Mapping) else {}


def _backlog(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    return {
        "roadmap": deepcopy(canonical.get("roadmap") or assessment.get("roadmap") or []),
        "backlog": deepcopy(canonical.get("backlog") or assessment.get("backlog") or []),
        "work_packages": deepcopy(
            canonical.get("work_packages") or assessment.get("work_packages") or []
        ),
        "staffing_plan": deepcopy(
            canonical.get("staffing_plan") or assessment.get("staffing_plan") or []
        ),
        "approval_state": "illustrative_or_pending_stakeholder_validation",
    }


def _build_structured_exports(canonical: Mapping[str, Any]) -> dict[str, bytes]:
    findings_register = _finding_register(canonical)
    findings = _records(findings_register.get("code_findings")) + _records(
        findings_register.get("operational_findings")
    )
    candidate_register = _candidate_register(canonical)
    candidates = _records(candidate_register.get("findings"))
    finding_fields = [
        "finding_id",
        "priority",
        "priority_score",
        "priority_rationale",
        "technical_severity",
        "category",
        "finding_family",
        "title",
        "path",
        "line",
        "location",
        "observed_evidence",
        "business_impact",
        "recommended_correction",
        "verification",
        "disposition",
        "evidence_confidence",
        "critical_path_relevance",
    ]
    evidence_fields = [
        "candidate_id",
        "finding_id",
        "scanner",
        "category",
        "rule_id",
        "normalized_rule_family",
        "severity",
        "scanner_severity",
        "confidence",
        "reachability",
        "production_classification",
        "source_path",
        "line",
        "evidence",
        "evidence_quality",
        "evidence_digest_sha256",
        "duplicate_group_id",
        "batch_disposition_key",
        "proposed_disposition",
        "human_disposition",
        "disposition_rationale",
        "reviewer_identity",
        "review_timestamp",
        "raw_payload_retention_state",
    ]
    return {
        "findings_csv": _csv_bytes(findings, finding_fields),
        "evidence_csv": _csv_bytes(candidates, evidence_fields),
        "candidate_register_json": _json_bytes(candidate_register),
        "remediation_backlog_json": _json_bytes(_backlog(canonical)),
    }


def _artifact_entry(
    *,
    artifact_type: str,
    filename: str,
    content: bytes | None,
    schema_version: str,
    identity: Mapping[str, str],
    digest_status: str = "retained",
) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "filename": filename,
        "sha256": _sha256(content) if content is not None else None,
        "size_bytes": len(content) if content is not None else None,
        "schema_version": schema_version,
        "run_id": identity.get("run_id"),
        "commit_sha": identity.get("commit_sha"),
        "digest_status": digest_status,
    }


def _preliminary_entries(
    canonical: Mapping[str, Any],
    exports: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    identity = _canonical_identity(canonical)
    run = _safe_filename(identity.get("run_id"), "run")
    return [
        _artifact_entry(
            artifact_type="findings_csv",
            filename=f"nico-{run}-findings.csv",
            content=exports["findings_csv"],
            schema_version="nico.findings-csv.v1",
            identity=identity,
        ),
        _artifact_entry(
            artifact_type="evidence_csv",
            filename=f"nico-{run}-evidence.csv",
            content=exports["evidence_csv"],
            schema_version="nico.evidence-csv.v1",
            identity=identity,
        ),
        _artifact_entry(
            artifact_type="candidate_register_json",
            filename=f"nico-{run}-candidate-register.json",
            content=exports["candidate_register_json"],
            schema_version="nico.canonical-scanner-findings.v1",
            identity=identity,
        ),
        _artifact_entry(
            artifact_type="remediation_backlog_json",
            filename=f"nico-{run}-remediation-backlog.json",
            content=exports["remediation_backlog_json"],
            schema_version="nico.remediation-backlog.v1",
            identity=identity,
        ),
    ]


def _render_manifest_approval_supplement(
    canonical: Mapping[str, Any],
    entries: list[dict[str, Any]],
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    identity = _canonical_identity(canonical)
    lifecycle = canonical.get("lifecycle") if isinstance(canonical.get("lifecycle"), Mapping) else _lifecycle()
    approval = canonical.get("approval") if isinstance(canonical.get("approval"), Mapping) else _pending_approval_record()
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ManifestTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=9,
    )
    heading = ParagraphStyle(
        "ManifestHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=colors.HexColor("#075985"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "ManifestBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.1,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "ManifestSmall",
        parent=body,
        fontSize=6.7,
        leading=8.3,
        textColor=colors.HexColor("#475569"),
        spaceAfter=2,
    )
    warning = ParagraphStyle(
        "ManifestWarning",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.7,
        borderPadding=7,
        spaceAfter=8,
    )

    def p(value: Any, style: ParagraphStyle = body, limit: int = 1800) -> Paragraph:
        return Paragraph(html.escape(_text(value, limit)), style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, "NICO | exact-artifact review package | automated draft")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Integrity {doc.page}")
        canvas.restoreState()

    identity_rows = [
        ["Repository", identity.get("repository") or "Not available"],
        ["Exact commit", identity.get("commit_sha") or "Not available"],
        ["Run ID", identity.get("run_id") or "Not available"],
        ["Evidence ledger ID", identity.get("evidence_ledger_id") or "Not available"],
        ["Generated", identity.get("generation_timestamp") or "Not available"],
    ]
    identity_table = Table(
        [[p(left, small), p(right, small)] for left, right in identity_rows],
        colWidths=[1.35 * inch, 6.05 * inch],
    )
    identity_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    artifact_rows = [["Artifact", "Filename", "SHA-256"]]
    for item in entries:
        artifact_rows.append(
            [
                item.get("artifact_type") or "",
                item.get("filename") or "",
                item.get("sha256") or "Bound in detached manifest after final rendering",
            ]
        )
    artifact_table = Table(
        [[p(cell, small, 900) for cell in row] for row in artifact_rows],
        colWidths=[1.35 * inch, 2.75 * inch, 3.3 * inch],
        repeatRows=1,
    )
    artifact_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story: list[Any] = [
        p("Client Artifact Manifest", title),
        p("AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED", warning),
        identity_table,
        p("Retained structured artifacts", heading),
        artifact_table,
        Spacer(1, .08 * inch),
        p(
            "The final PDF and canonical JSON byte digests are recorded in the detached evidence manifest after rendering. A document cannot truthfully embed its own final byte digest without changing that digest. The detached manifest binds those final hashes to the same run, commit, and manifest ID.",
            body,
        ),
        PageBreak(),
        p("Human Review and Exact-Artifact Approval Record", title),
        p("REVIEW PACKAGE READY · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", warning),
        p("Lifecycle", heading),
        p(f"Review package ready: {'Yes' if lifecycle.get('review_package_ready') else 'No'}", body),
        p(f"Human approval: {_text(lifecycle.get('human_review_status') or 'pending').title()}", body),
        p(f"Client delivery: {_text(lifecycle.get('client_delivery_status') or 'blocked').title()}", body),
        p("Required approval record", heading),
    ]
    approval_rows = [
        ["Reviewer identity", approval.get("reviewer_identity") or "Pending"],
        ["Reviewer role", approval.get("reviewer_role") or "Pending"],
        ["Reviewer authorization", "Confirmed" if approval.get("reviewer_authorized") else "Pending"],
        ["Review timestamp", approval.get("review_timestamp") or "Pending"],
        ["Decision", approval.get("decision") or "Pending"],
        ["Residual-risk acceptance", approval.get("residual_risk_acceptance") or "Pending"],
        ["Approved PDF SHA-256", approval.get("approved_pdf_sha256") or "Recorded in detached approval receipt after decision"],
        ["Approved JSON SHA-256", approval.get("approved_json_sha256") or "Recorded in detached approval receipt after decision"],
        ["Evidence manifest SHA-256", approval.get("evidence_manifest_sha256") or "Recorded in detached approval receipt after decision"],
        ["Approval record ID", approval.get("approval_record_id") or "Pending"],
        ["Reviewer notes", approval.get("reviewer_notes") or "Pending"],
    ]
    approval_table = Table(
        [[p(left, small), p(right, small, 1000)] for left, right in approval_rows],
        colWidths=[1.65 * inch, 5.75 * inch],
    )
    approval_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend(
        [
            approval_table,
            p("Approval rule", heading),
            p(
                "Only an authorized human reviewer may approve the exact immutable PDF, canonical JSON, and detached evidence manifest digests. Any regeneration, score change, finding change, candidate disposition change, evidence change, or artifact replacement creates a new draft and invalidates prior approval.",
                body,
            ),
            p(
                "Automation cannot change this package to APPROVED FINAL or CLIENT DELIVERY AUTHORIZED.",
                warning,
            ),
        ]
    )
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Client Artifact Manifest and Approval Record",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _append_pdf(base_pdf: bytes, supplement: bytes) -> bytes:
    writer = PdfWriter()
    for source in (base_pdf, supplement):
        for page in PdfReader(io.BytesIO(source)).pages:
            writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _markdown_manifest(
    identity: Mapping[str, str],
    entries: list[dict[str, Any]],
    *,
    pdf_sha256: str,
    canonical_json_sha256: str,
    manifest_sha256: str,
) -> str:
    lines = [
        "## Client Artifact Manifest",
        "",
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        "",
        f"- Repository: {identity.get('repository') or 'Not available'}",
        f"- Exact commit: {identity.get('commit_sha') or 'Not available'}",
        f"- Run ID: {identity.get('run_id') or 'Not available'}",
        f"- Evidence ledger ID: {identity.get('evidence_ledger_id') or 'Not available'}",
        "",
        "| Artifact | Filename | SHA-256 |",
        "|---|---|---|",
    ]
    for item in entries:
        lines.append(
            f"| {item.get('artifact_type')} | {item.get('filename')} | {item.get('sha256')} |"
        )
    lines.extend(
        [
            f"| comprehensive_pdf | nico-{_safe_filename(identity.get('run_id'), 'run')}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf | {pdf_sha256} |",
            f"| canonical_json | nico-{_safe_filename(identity.get('run_id'), 'run')}-canonical.json | {canonical_json_sha256} |",
            f"| evidence_manifest_json | nico-{_safe_filename(identity.get('run_id'), 'run')}-evidence-manifest.json | {manifest_sha256} |",
            "",
            "## Human Review and Exact-Artifact Approval Record",
            "",
            "- Review package ready: Yes",
            "- Human approval: Pending",
            "- Client delivery: Blocked",
            "- Reviewer identity: Pending",
            "- Reviewer role: Pending",
            "- Reviewer authorization: Pending",
            "- Decision: Pending",
            "- Approved PDF SHA-256: Pending exact-artifact approval",
            "- Approved JSON SHA-256: Pending exact-artifact approval",
            "- Evidence manifest SHA-256: Pending exact-artifact approval",
            "",
            "Only an authorized human reviewer may approve these exact digests. Any regenerated artifact returns to Automated Draft and blocks delivery.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def attach_artifact_manifest(package: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(package))
    canonical = (
        deepcopy(dict(output.get("json") or {}))
        if isinstance(output.get("json"), Mapping)
        else {}
    )
    identity = _canonical_identity(canonical)
    canonical["lifecycle"] = _lifecycle()
    canonical["approval"] = _pending_approval_record()
    canonical["review_package_ready"] = True
    canonical["human_review_required"] = True
    canonical["client_delivery_allowed"] = False
    canonical["report_finality"] = "automated_draft"
    canonical["approval_status"] = "pending_human_approval"
    canonical["delivery_status"] = "blocked_pending_human_approval"

    exports = _build_structured_exports(canonical)
    entries = _preliminary_entries(canonical, exports)
    base_pdf = base64.b64decode(str(output.get("pdf_base64") or ""))
    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("Artifact manifest requires a valid Comprehensive PDF.")
    supplement_entries = deepcopy(entries)
    for item in supplement_entries:
        item["sha256"] = None
        item["digest_status"] = "bound_in_detached_manifest_after_final_rendering"
    supplement = _render_manifest_approval_supplement(canonical, supplement_entries)
    final_pdf = _append_pdf(base_pdf, supplement)
    page_count = len(PdfReader(io.BytesIO(final_pdf)).pages)
    if page_count > MAX_CLIENT_PDF_PAGES:
        raise ValueError(
            f"Comprehensive client package exceeds the {MAX_CLIENT_PDF_PAGES}-page hard boundary: {page_count}"
        )
    pdf_sha256 = _sha256(final_pdf)

    run = _safe_filename(identity.get("run_id"), "run")
    pdf_entry = _artifact_entry(
        artifact_type="comprehensive_pdf",
        filename=f"nico-{run}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf",
        content=final_pdf,
        schema_version="application/pdf",
        identity=identity,
    )
    canonical_truth_payload = deepcopy(canonical)
    canonical_truth_payload.pop("artifacts", None)
    canonical_truth_payload.pop("artifact_manifest", None)
    canonical_truth_payload_sha256 = _sha256(_json_bytes(canonical_truth_payload))
    canonical["artifacts"] = [
        *deepcopy(entries),
        deepcopy(pdf_entry),
        {
            "artifact_type": "canonical_json",
            "filename": f"nico-{run}-canonical.json",
            "sha256": canonical_truth_payload_sha256,
            "digest_scope": "canonical_truth_payload_excluding_artifact_self_reference",
            "schema_version": "nico.canonical-report-truth.v1",
            "run_id": identity.get("run_id"),
            "commit_sha": identity.get("commit_sha"),
            "digest_status": "payload_digest_retained; file_digest_in_detached_manifest",
        },
        {
            "artifact_type": "evidence_manifest_json",
            "filename": f"nico-{run}-evidence-manifest.json",
            "sha256": None,
            "digest_scope": "detached_self_digest_returned_outside_manifest",
            "schema_version": MANIFEST_SCHEMA,
            "run_id": identity.get("run_id"),
            "commit_sha": identity.get("commit_sha"),
            "digest_status": "detached_self_digest",
        },
    ]
    canonical["artifact_manifest"] = {
        "artifact_schema": MANIFEST_SCHEMA,
        "manifest_id": f"NICO-MANIFEST-{_sha256(_json_bytes({'identity': identity, 'pdf': pdf_sha256, 'entries': entries}))[:20].upper()}",
        "identity": identity,
        "artifact_count": len(canonical["artifacts"]),
        "artifacts": deepcopy(canonical["artifacts"]),
        "pdf_self_digest_bound_externally": True,
        "canonical_json_file_digest_bound_externally": True,
        "manifest_self_digest_bound_externally": True,
        "exact_artifact_approval_required": True,
        "digest_independent_manifest_supplement": True,
    }
    canonical_json = _json_bytes(canonical)
    canonical_json_sha256 = _sha256(canonical_json)

    manifest = {
        "artifact_schema": MANIFEST_SCHEMA,
        "manifest_id": canonical["artifact_manifest"]["manifest_id"],
        "identity": identity,
        "lifecycle": deepcopy(canonical["lifecycle"]),
        "artifacts": [
            *deepcopy(entries),
            deepcopy(pdf_entry),
            _artifact_entry(
                artifact_type="canonical_json",
                filename=f"nico-{run}-canonical.json",
                content=canonical_json,
                schema_version="nico.canonical-report-truth.v1",
                identity=identity,
            ),
        ],
        "approval": deepcopy(canonical["approval"]),
        "self_digest_location": "package.evidence_manifest_sha256",
        "rule": "Approval is valid only for the exact PDF, canonical JSON, and detached manifest digests retained with this run and commit.",
        "digest_independent_manifest_supplement": True,
    }
    manifest_json = _json_bytes(manifest)
    manifest_sha256 = _sha256(manifest_json)

    markdown = str(output.get("markdown") or "").rstrip()
    manifest_markdown = _markdown_manifest(
        identity,
        entries,
        pdf_sha256=pdf_sha256,
        canonical_json_sha256=canonical_json_sha256,
        manifest_sha256=manifest_sha256,
    )
    markdown = markdown + "\n\n" + manifest_markdown
    rendered_html = str(output.get("html") or "")
    html_section = (
        "<section data-nico-artifact-manifest=\"true\"><pre>"
        + html.escape(manifest_markdown)
        + "</pre></section>"
    )
    rendered_html = (
        rendered_html.replace("</body>", html_section + "</body>", 1)
        if "</body>" in rendered_html
        else rendered_html + html_section
    )

    draft_identity = {
        "artifact_schema": "nico.comprehensive-draft-artifact-identity.v1",
        "repository": identity.get("repository"),
        "commit_sha": identity.get("commit_sha"),
        "run_id": identity.get("run_id"),
        "pdf_sha256": pdf_sha256,
        "canonical_json_sha256": canonical_json_sha256,
        "evidence_manifest_sha256": manifest_sha256,
        "manifest_id": manifest["manifest_id"],
        "report_finality": "automated_draft",
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
    }
    output.update(
        {
            "json": canonical,
            "canonical_json": canonical_json.decode("utf-8"),
            "canonical_json_sha256": canonical_json_sha256,
            "findings_csv": exports["findings_csv"].decode("utf-8"),
            "findings_csv_sha256": _sha256(exports["findings_csv"]),
            "evidence_csv": exports["evidence_csv"].decode("utf-8"),
            "evidence_csv_sha256": _sha256(exports["evidence_csv"]),
            "candidate_register_json": exports["candidate_register_json"].decode("utf-8"),
            "candidate_register_sha256": _sha256(exports["candidate_register_json"]),
            "remediation_backlog_json": exports["remediation_backlog_json"].decode("utf-8"),
            "remediation_backlog_sha256": _sha256(exports["remediation_backlog_json"]),
            "artifact_manifest": manifest,
            "evidence_manifest_json": manifest_json.decode("utf-8"),
            "evidence_manifest_sha256": manifest_sha256,
            "draft_artifact_identity": draft_identity,
            "pdf_base64": base64.b64encode(final_pdf).decode("ascii"),
            "pdf_sha256": pdf_sha256,
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "markdown": markdown,
            "markdown_sha256": _sha256(markdown.encode("utf-8")),
            "html": rendered_html,
            "html_sha256": _sha256(rendered_html.encode("utf-8")),
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
            "report_finality": "automated_draft",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "client_delivery_allowed": False,
            "digest_independent_manifest_supplement": True,
        }
    )
    completion = deepcopy(dict(output.get("client_report_completion") or {}))
    completion.update(
        {
            "artifact_manifest_version": VERSION,
            "artifact_manifest_present": True,
            "detached_manifest_binds_final_pdf": True,
            "detached_manifest_binds_canonical_json": True,
            "exact_artifact_approval_record_present": True,
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
            "page_count": page_count,
            "digest_independent_manifest_supplement": True,
        }
    )
    output["client_report_completion"] = completion
    return output


def rebind_artifact_manifest(package: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute a pending draft manifest after a pre-approval artifact update.

    The manifest/approval supplement already retained in the PDF is deliberately
    digest-independent. Re-rendering it would duplicate pages and navigation. This
    path therefore keeps the current report bytes, rebuilds every retained digest
    from those bytes, and resets the exact-artifact lifecycle to pending.
    """

    output = deepcopy(dict(package))
    existing_manifest = output.get("artifact_manifest")
    if not isinstance(existing_manifest, Mapping):
        raise ValueError("Artifact manifest rebinding requires an existing detached manifest.")
    existing_identity = output.get("draft_artifact_identity")
    if (
        _text(existing_manifest.get("artifact_schema")) != MANIFEST_SCHEMA
        or not _text(existing_manifest.get("manifest_id"))
        or not isinstance(existing_identity, Mapping)
        or _text(existing_identity.get("artifact_schema"))
        != "nico.comprehensive-draft-artifact-identity.v1"
        or any(
            not _text(existing_identity.get(field))
            for field in (
                "pdf_sha256",
                "canonical_json_sha256",
                "evidence_manifest_sha256",
                "manifest_id",
            )
        )
    ):
        raise ValueError("Artifact manifest rebinding requires a complete exact draft identity.")
    lifecycle = output.get("json")
    lifecycle = lifecycle.get("lifecycle") if isinstance(lifecycle, Mapping) else {}
    lifecycle = lifecycle if isinstance(lifecycle, Mapping) else {}
    if (
        output.get("client_delivery_allowed") is True
        or isinstance(output.get("accepted_edition"), Mapping)
        or _text(output.get("human_review_status")).casefold() == "approved"
        or _text(output.get("approval_status")).casefold() in {"approved", "approved_final"}
        or _text(lifecycle.get("human_review_status")).casefold() == "approved"
        or lifecycle.get("client_delivery_allowed") is True
    ):
        raise ValueError("Approved or delivery-authorized artifacts cannot be rebound in place.")
    completion = output.get("client_report_completion")
    completion = completion if isinstance(completion, Mapping) else {}
    embedded_manifest = output.get("json")
    embedded_manifest = (
        embedded_manifest.get("artifact_manifest")
        if isinstance(embedded_manifest, Mapping)
        else {}
    )
    embedded_manifest = embedded_manifest if isinstance(embedded_manifest, Mapping) else {}
    if not all(
        marker is True
        for marker in (
            output.get("digest_independent_manifest_supplement"),
            completion.get("digest_independent_manifest_supplement"),
            existing_manifest.get("digest_independent_manifest_supplement"),
            embedded_manifest.get("digest_independent_manifest_supplement"),
        )
    ):
        raise ValueError(
            "Artifact manifest rebinding requires a digest-independent manifest supplement; regenerate this draft first."
        )
    canonical = (
        deepcopy(dict(output.get("json") or {}))
        if isinstance(output.get("json"), Mapping)
        else {}
    )
    identity = _canonical_identity(canonical)
    canonical["lifecycle"] = _lifecycle()
    canonical["approval"] = _pending_approval_record()
    canonical["review_package_ready"] = True
    canonical["human_review_required"] = True
    canonical["client_delivery_allowed"] = False
    canonical["report_finality"] = "automated_draft"
    canonical["approval_status"] = "pending_human_approval"
    canonical["delivery_status"] = "blocked_pending_human_approval"

    markdown = str(output.get("markdown") or "")
    rendered_html = str(output.get("html") or "")
    if not markdown or not rendered_html:
        raise ValueError("Artifact manifest rebinding requires retained Markdown and HTML.")
    try:
        pdf = base64.b64decode(str(output.get("pdf_base64") or ""), validate=True)
        page_count = len(PdfReader(io.BytesIO(pdf)).pages)
    except Exception as exc:
        raise ValueError("Artifact manifest rebinding requires a valid Comprehensive PDF.") from exc
    if not pdf.startswith(b"%PDF") or page_count < 1:
        raise ValueError("Artifact manifest rebinding requires a valid Comprehensive PDF.")
    if page_count > MAX_CLIENT_PDF_PAGES:
        raise ValueError(
            f"Comprehensive client package exceeds the {MAX_CLIENT_PDF_PAGES}-page hard boundary: {page_count}"
        )

    from nico import comprehensive_manifest_navigation_v1 as navigation

    run = _safe_filename(identity.get("run_id"), "run")
    retained = {
        "findings_csv": str(output.get("findings_csv") or "").encode("utf-8"),
        "evidence_csv": str(output.get("evidence_csv") or "").encode("utf-8"),
        "candidate_register_json": str(
            output.get("candidate_register_json") or ""
        ).encode("utf-8"),
        "remediation_backlog_json": str(
            output.get("remediation_backlog_json") or ""
        ).encode("utf-8"),
    }
    missing_retained = sorted(name for name, content in retained.items() if not content)
    if missing_retained:
        raise ValueError(
            "Artifact manifest rebinding omitted retained structured artifacts: "
            + ", ".join(missing_retained)
        )
    token = navigation._CONTEXT.set(deepcopy(output))
    try:
        entries = [
            _artifact_entry(
                artifact_type="findings_csv",
                filename=f"nico-{run}-findings.csv",
                content=retained["findings_csv"],
                schema_version="nico.findings-csv.v1",
                identity=identity,
            ),
            _artifact_entry(
                artifact_type="evidence_csv",
                filename=f"nico-{run}-evidence.csv",
                content=retained["evidence_csv"],
                schema_version="nico.evidence-csv.v1",
                identity=identity,
            ),
            _artifact_entry(
                artifact_type="candidate_register_json",
                filename=f"nico-{run}-candidate-register.json",
                content=retained["candidate_register_json"],
                schema_version="nico.canonical-scanner-findings.v1",
                identity=identity,
            ),
            _artifact_entry(
                artifact_type="remediation_backlog_json",
                filename=f"nico-{run}-remediation-backlog.json",
                content=retained["remediation_backlog_json"],
                schema_version="nico.remediation-backlog.v1",
                identity=identity,
            ),
            _artifact_entry(
                artifact_type="markdown_report",
                filename=f"nico-{run}.md",
                content=markdown.encode("utf-8"),
                schema_version="text/markdown",
                identity=identity,
            ),
            _artifact_entry(
                artifact_type="html_report",
                filename=f"nico-{run}.html",
                content=rendered_html.encode("utf-8"),
                schema_version="text/html",
                identity=identity,
            ),
        ]
        pdf_entry = _artifact_entry(
            artifact_type="comprehensive_pdf",
            filename=f"nico-{run}-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf",
            content=pdf,
            schema_version="application/pdf",
            identity=identity,
        )
    finally:
        navigation._CONTEXT.reset(token)

    pdf_sha256 = _sha256(pdf)
    canonical_truth_payload = deepcopy(canonical)
    canonical_truth_payload.pop("artifacts", None)
    canonical_truth_payload.pop("artifact_manifest", None)
    canonical_truth_payload_sha256 = _sha256(_json_bytes(canonical_truth_payload))
    canonical["artifacts"] = [
        *deepcopy(entries),
        deepcopy(pdf_entry),
        {
            "artifact_type": "canonical_json",
            "filename": f"nico-{run}-canonical.json",
            "sha256": canonical_truth_payload_sha256,
            "digest_scope": "canonical_truth_payload_excluding_artifact_self_reference",
            "schema_version": "nico.canonical-report-truth.v1",
            "run_id": identity.get("run_id"),
            "commit_sha": identity.get("commit_sha"),
            "digest_status": "payload_digest_retained; file_digest_in_detached_manifest",
        },
        {
            "artifact_type": "evidence_manifest_json",
            "filename": f"nico-{run}-evidence-manifest.json",
            "sha256": None,
            "digest_scope": "detached_self_digest_returned_outside_manifest",
            "schema_version": MANIFEST_SCHEMA,
            "run_id": identity.get("run_id"),
            "commit_sha": identity.get("commit_sha"),
            "digest_status": "detached_self_digest",
        },
    ]
    manifest_id = (
        f"NICO-MANIFEST-{_sha256(_json_bytes({'identity': identity, 'pdf': pdf_sha256, 'entries': entries}))[:20].upper()}"
    )
    canonical["artifact_manifest"] = {
        "artifact_schema": MANIFEST_SCHEMA,
        "manifest_id": manifest_id,
        "identity": identity,
        "artifact_count": len(canonical["artifacts"]),
        "artifacts": deepcopy(canonical["artifacts"]),
        "pdf_self_digest_bound_externally": True,
        "canonical_json_file_digest_bound_externally": True,
        "manifest_self_digest_bound_externally": True,
        "exact_artifact_approval_required": True,
        "digest_independent_manifest_supplement": True,
    }
    canonical_json = _json_bytes(canonical)
    canonical_json_sha256 = _sha256(canonical_json)
    token = navigation._CONTEXT.set(deepcopy(output))
    try:
        canonical_entry = _artifact_entry(
            artifact_type="canonical_json",
            filename=f"nico-{run}-canonical.json",
            content=canonical_json,
            schema_version="nico.canonical-report-truth.v1",
            identity=identity,
        )
    finally:
        navigation._CONTEXT.reset(token)
    manifest = {
        "artifact_schema": MANIFEST_SCHEMA,
        "manifest_id": manifest_id,
        "identity": identity,
        "lifecycle": deepcopy(canonical["lifecycle"]),
        "artifacts": [*deepcopy(entries), deepcopy(pdf_entry), canonical_entry],
        "approval": deepcopy(canonical["approval"]),
        "self_digest_location": "package.evidence_manifest_sha256",
        "rule": "Approval is valid only for the exact PDF, canonical JSON, and detached manifest digests retained with this run and commit.",
        "digest_independent_manifest_supplement": True,
    }
    manifest_json = _json_bytes(manifest)
    manifest_sha256 = _sha256(manifest_json)
    draft_identity = {
        "artifact_schema": "nico.comprehensive-draft-artifact-identity.v1",
        "repository": identity.get("repository"),
        "commit_sha": identity.get("commit_sha"),
        "run_id": identity.get("run_id"),
        "pdf_sha256": pdf_sha256,
        "canonical_json_sha256": canonical_json_sha256,
        "evidence_manifest_sha256": manifest_sha256,
        "manifest_id": manifest_id,
        "report_finality": "automated_draft",
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
    }
    output.update(
        {
            "json": canonical,
            "canonical_json": canonical_json.decode("utf-8"),
            "canonical_json_sha256": canonical_json_sha256,
            "json_sha256": canonical_json_sha256,
            "canonical_truth_sha256": canonical_json_sha256,
            "findings_csv_sha256": _sha256(retained["findings_csv"]),
            "evidence_csv_sha256": _sha256(retained["evidence_csv"]),
            "candidate_register_sha256": _sha256(retained["candidate_register_json"]),
            "remediation_backlog_sha256": _sha256(retained["remediation_backlog_json"]),
            "artifact_manifest": manifest,
            "evidence_manifest_json": manifest_json.decode("utf-8"),
            "evidence_manifest_sha256": manifest_sha256,
            "draft_artifact_identity": draft_identity,
            "pdf_sha256": pdf_sha256,
            "pdf_size_bytes": len(pdf),
            "pdf_page_count": page_count,
            "final_package_page_count": page_count,
            "markdown_sha256": _sha256(markdown.encode("utf-8")),
            "html_sha256": _sha256(rendered_html.encode("utf-8")),
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
            "report_finality": "automated_draft",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "client_delivery_allowed": False,
            "digest_independent_manifest_supplement": True,
        }
    )
    updated_completion = deepcopy(dict(output.get("client_report_completion") or {}))
    updated_completion.update(
        {
            "artifact_manifest_present": True,
            "detached_manifest_binds_final_pdf": True,
            "detached_manifest_binds_canonical_json": True,
            "exact_artifact_approval_record_present": True,
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
            "page_count": page_count,
            "digest_independent_manifest_supplement": True,
        }
    )
    output["client_report_completion"] = updated_completion
    content_integrity = deepcopy(dict(output.get("content_integrity") or {}))
    content_integrity.update(
        {
            "markdown_sha256": output["markdown_sha256"],
            "html_sha256": output["html_sha256"],
            "pdf_sha256": output["pdf_sha256"],
            "json_sha256": canonical_json_sha256,
            "canonical_json_sha256": canonical_json_sha256,
            "evidence_manifest_sha256": manifest_sha256,
        }
    )
    output["content_integrity"] = content_integrity
    return output


def _patch_final_review_gate() -> None:
    from nico import client_final_review_gate_patch as gate

    current = gate.build_client_final_review_gate
    if getattr(current, _GATE_MARKER, False):
        return

    @wraps(current)
    def build_client_final_review_gate(result: dict[str, Any]) -> dict[str, Any]:
        output = deepcopy(current(result))
        manifest = result.get("artifact_manifest")
        identity = result.get("draft_artifact_identity")
        checks = list(output.get("checklist") or [])
        manifest_present = isinstance(manifest, Mapping) and bool(manifest.get("manifest_id"))
        identity_present = isinstance(identity, Mapping) and all(
            _text(identity.get(key))
            for key in ("pdf_sha256", "canonical_json_sha256", "evidence_manifest_sha256")
        )
        checks.extend(
            [
                {
                    "id": "detached_artifact_manifest_present",
                    "passed": manifest_present,
                    "label": "Detached exact-artifact manifest is present.",
                },
                {
                    "id": "draft_artifact_identity_complete",
                    "passed": identity_present,
                    "label": "Draft PDF, canonical JSON, and manifest digests are retained.",
                },
            ]
        )
        blockers = [item["label"] for item in checks if not item.get("passed")]
        output.update(
            {
                "artifact_schema": "nico.client_final_review_gate.v2",
                "status": (
                    "ready_for_final_human_review_with_disclosures"
                    if not blockers
                    else "blocked_missing_final_review_evidence"
                ),
                "report_finality": "automated_draft",
                "automation_finality": "automated_draft_pending_human_approval",
                "review_package_ready": not blockers,
                "approval_status": "pending_human_approval",
                "delivery_status": "blocked_pending_human_approval",
                "client_delivery_allowed": False,
                "checklist": checks,
                "blockers": blockers,
                "draft_artifact_identity": deepcopy(identity) if isinstance(identity, Mapping) else {},
                "artifact_manifest_id": manifest.get("manifest_id") if isinstance(manifest, Mapping) else "",
                "rule": "Client delivery remains blocked until authorized human reviewers approve the exact PDF, canonical JSON, and detached manifest digests.",
            }
        )
        return output

    setattr(build_client_final_review_gate, _GATE_MARKER, True)
    setattr(build_client_final_review_gate, "_nico_previous", current)
    gate.build_client_final_review_gate = build_client_final_review_gate


def _patch_final_review_workflow() -> None:
    from nico import final_review_workflow as workflow

    current_validation = workflow.final_review_validation
    if not getattr(current_validation, _VALIDATION_MARKER, False):

        @wraps(current_validation)
        def final_review_validation(approval: dict[str, Any]) -> dict[str, Any]:
            output = deepcopy(current_validation(approval))
            report = workflow._report_for_run(
                str(approval.get("report_id") or approval.get("run_id") or "")
            )
            formats = report.get("formats") if isinstance(report.get("formats"), Mapping) else {}
            canonical = formats.get("json") if isinstance(formats.get("json"), Mapping) else {}
            identity = (
                canonical.get("draft_artifact_identity")
                if isinstance(canonical.get("draft_artifact_identity"), Mapping)
                else report.get("draft_artifact_identity")
            )
            manifest = (
                canonical.get("artifact_manifest")
                if isinstance(canonical.get("artifact_manifest"), Mapping)
                else report.get("artifact_manifest")
            )
            encoded_pdf = formats.get("pdf")
            try:
                pdf = base64.b64decode(str(encoded_pdf or ""), validate=True)
            except Exception:
                pdf = b""
            stored_pdf_sha = _sha256(pdf) if pdf.startswith(b"%PDF") else ""
            expected_pdf_sha = _text(identity.get("pdf_sha256")) if isinstance(identity, Mapping) else ""
            exact_digests = isinstance(identity, Mapping) and all(
                _text(identity.get(key))
                for key in ("pdf_sha256", "canonical_json_sha256", "evidence_manifest_sha256")
            )
            checks = list(output.get("checks") or [])
            checks.extend(
                [
                    {
                        "id": "artifact_manifest_present",
                        "passed": isinstance(manifest, Mapping) and bool(manifest.get("manifest_id")),
                        "message": "Detached artifact manifest is retained.",
                    },
                    {
                        "id": "exact_artifact_digests_present",
                        "passed": exact_digests,
                        "message": "Exact PDF, canonical JSON, and manifest digests are retained.",
                    },
                    {
                        "id": "stored_pdf_digest_matches",
                        "passed": bool(stored_pdf_sha and expected_pdf_sha and stored_pdf_sha == expected_pdf_sha),
                        "message": "Stored PDF bytes match the exact draft digest submitted for approval.",
                    },
                    {
                        "id": "reviewer_role_present",
                        "passed": bool(_text(approval.get("reviewer_role"))),
                        "message": "Reviewer role is recorded.",
                    },
                    {
                        "id": "reviewer_authorized",
                        "passed": approval.get("reviewer_authorized") is True,
                        "message": "Reviewer authorization is explicitly confirmed.",
                    },
                ]
            )
            blockers = [item["message"] for item in checks if not item.get("passed")]
            output.update(
                {
                    "artifact_schema": "nico.final-review-validation.v2",
                    "status": "ready_for_human_decision" if not blockers else "blocked",
                    "ready_for_approval": not blockers,
                    "checks": checks,
                    "blockers": blockers,
                    "draft_artifact_identity": deepcopy(identity) if isinstance(identity, Mapping) else {},
                    "artifact_manifest_id": manifest.get("manifest_id") if isinstance(manifest, Mapping) else "",
                    "rule": "Approval requires an authorized reviewer and exact matching PDF, canonical JSON, and detached manifest digests.",
                }
            )
            return output

        setattr(final_review_validation, _VALIDATION_MARKER, True)
        setattr(final_review_validation, "_nico_previous", current_validation)
        workflow.final_review_validation = final_review_validation

    current_request = workflow.request_final_review
    if not getattr(current_request, _REQUEST_MARKER, False):

        @wraps(current_request)
        def request_final_review(payload: dict[str, Any]) -> dict[str, Any]:
            result = current_request(payload)
            approval = result.get("approval") if isinstance(result.get("approval"), dict) else None
            if approval:
                approval["reviewer_role"] = _text(payload.get("reviewer_role"))
                approval["reviewer_authorized"] = payload.get("reviewer_authorized") is True
                approval["residual_risk_acceptance"] = payload.get("residual_risk_acceptance")
                approval["reviewer_notes"] = _text(payload.get("reviewer_notes"))
                approval["exact_artifact_approval_required"] = True
                workflow.STORE.put("approvals", approval["approval_id"], approval)
                approval["review_validation"] = workflow.final_review_validation(approval)
                workflow.STORE.put("approvals", approval["approval_id"], approval)
                result["approval"] = approval
            return result

        setattr(request_final_review, _REQUEST_MARKER, True)
        setattr(request_final_review, "_nico_previous", current_request)
        workflow.request_final_review = request_final_review

    current_transition = workflow.transition_final_review
    if not getattr(current_transition, _TRANSITION_MARKER, False):

        @wraps(current_transition)
        def transition_final_review(
            approval_id: str,
            state: str,
            actor: str = "human_reviewer",
            note: str = "",
        ) -> dict[str, Any]:
            if str(state or "").strip().lower() == "approved":
                approval = workflow.STORE.get("approvals", approval_id)
                if not isinstance(approval, Mapping):
                    return {"status": "not_found", "approval_id": approval_id}
                if not _text(approval.get("reviewer_role")):
                    return {
                        "status": "blocked",
                        "error": "Reviewer role is required before exact-artifact approval.",
                        "approval_id": approval_id,
                    }
                if approval.get("reviewer_authorized") is not True:
                    return {
                        "status": "blocked",
                        "error": "Reviewer authorization must be explicitly confirmed before approval.",
                        "approval_id": approval_id,
                    }
                validation = workflow.final_review_validation(dict(approval))
                if not validation.get("ready_for_approval"):
                    return {
                        "status": "blocked",
                        "error": "Exact-artifact approval validation failed.",
                        "approval_id": approval_id,
                        "review_validation": validation,
                    }
            return current_transition(approval_id, state, actor=actor, note=note)

        setattr(transition_final_review, _TRANSITION_MARKER, True)
        setattr(transition_final_review, "_nico_previous", current_transition)
        workflow.transition_final_review = transition_final_review


def install_comprehensive_artifact_manifest_approval_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17

    current = completion.finalize_client_report_package
    if not getattr(current, _FINALIZER_MARKER, False):

        @wraps(current)
        def finalize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
            return attach_artifact_manifest(current(package))

        setattr(finalize_client_report_package, _FINALIZER_MARKER, True)
        setattr(finalize_client_report_package, "_nico_previous", current)
        completion.finalize_client_report_package = finalize_client_report_package
        phase17.finalize_client_report_package = finalize_client_report_package

    _patch_final_review_gate()
    _patch_final_review_workflow()
    return {
        "status": "installed",
        "version": VERSION,
        "manifest_schema": MANIFEST_SCHEMA,
        "approval_schema": APPROVAL_SCHEMA,
        "detached_manifest_binds_final_pdf": True,
        "detached_manifest_binds_canonical_json": True,
        "reviewer_role_required": True,
        "reviewer_authorization_required": True,
        "regeneration_invalidates_approval": True,
        "review_package_ready": True,
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
        "client_delivery_allowed": False,
    }


__all__ = [
    "APPROVAL_SCHEMA",
    "MANIFEST_SCHEMA",
    "MAX_CLIENT_PDF_PAGES",
    "VERSION",
    "attach_artifact_manifest",
    "rebind_artifact_manifest",
    "install_comprehensive_artifact_manifest_approval_v1",
]
