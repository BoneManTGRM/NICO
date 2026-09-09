from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.decision_grade_accepted_edition_guard_v1 import (
    current_report_artifact_digest,
)


VERSION = "nico.comprehensive_approved_report.v1"

_MANIFEST_FAMILY_FIELDS = (
    "artifact_manifest",
    "evidence_manifest_json",
    "evidence_manifest_sha256",
    "canonical_json",
    "canonical_json_sha256",
    "draft_artifact_identity",
)

_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (
        "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
        "APPROVED FINAL · HUMAN REVIEW RECORDED · DELIVERY CONTROLLED SEPARATELY",
    ),
    (
        "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED",
        "APPROVED FINAL | HUMAN REVIEW RECORDED | DELIVERY CONTROLLED SEPARATELY",
    ),
    (
        "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED",
        "APPROVED FINAL | HUMAN DECISION RECORDED | DELIVERY CONTROLLED SEPARATELY",
    ),
    (
        "REVIEW PACKAGE READY · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED",
        "APPROVED FINAL · HUMAN REVIEW RECORDED · DELIVERY CONTROLLED SEPARATELY",
    ),
    (
        "BLOCKED - AUTHORIZED HUMAN APPROVAL REQUIRED",
        "APPROVED - AUTHORIZED HUMAN REVIEW RECORDED",
    ),
    (
        "Client delivery remains blocked until explicit authorized human approval",
        "Delivery authority is recorded in the separate certified package",
    ),
    (
        "Client delivery remains blocked until the separate protected approval and delivery gates succeed.",
        "Delivery authority is established by the separate protected approval and delivery certificates.",
    ),
    (
        "Client delivery remains blocked until the separate protected gates succeed.",
        "Delivery authority is established by the separate protected certificates.",
    ),
    (
        "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
        "FINAL APROBADO · REVISIÓN HUMANA REGISTRADA · ENTREGA CONTROLADA POR SEPARADO",
    ),
    (
        "BORRADOR AUTOMATIZADO | DECISIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA",
        "FINAL APROBADO | DECISIÓN HUMANA REGISTRADA | ENTREGA CONTROLADA POR SEPARADO",
    ),
    (
        "PAQUETE DE REVISIÓN LISTO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA",
        "FINAL APROBADO · REVISIÓN HUMANA REGISTRADA · ENTREGA CONTROLADA POR SEPARADO",
    ),
    ("AUTOMATED DRAFT", "APPROVED FINAL"),
    ("automated draft", "approved final"),
    ("PENDING HUMAN APPROVAL", "HUMAN APPROVAL RECORDED"),
    ("HUMAN APPROVAL PENDING", "HUMAN APPROVAL RECORDED"),
    ("HUMAN DECISION PENDING", "HUMAN DECISION RECORDED"),
    ("CLIENT DELIVERY BLOCKED", "DELIVERY CONTROLLED SEPARATELY"),
    ("BORRADOR AUTOMATIZADO", "FINAL APROBADO"),
    ("APROBACIÓN HUMANA PENDIENTE", "REVISIÓN HUMANA REGISTRADA"),
    ("DECISIÓN HUMANA PENDIENTE", "DECISIÓN HUMANA REGISTRADA"),
    ("ENTREGA AL CLIENTE BLOQUEADA", "ENTREGA CONTROLADA POR SEPARADO"),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _replace_finality_text(value: str) -> str:
    output = str(value or "")
    for previous, replacement in _TEXT_REPLACEMENTS:
        output = output.replace(previous, replacement)
    for pattern, replacement in (
        (
            r"(?m)(^|>|&gt;)(-\s*)?estado de (revisi[oó]n|aprobaci[oó]n)\s*:\s*(?:aprobaci[oó]n humana )?pendiente\b",
            r"\1\2Estado de \3: Aprobada",
        ),
        (
            r"(?m)(^|>|&gt;)(-\s*)?(identidad|rol|autorizaci[oó]n) del revisor\s*:\s*pendiente\b",
            r"\1\2\3 del revisor: Registrado en el certificado de revisión",
        ),
        (r"(?m)(^|>|&gt;)(-\s*)?decisi[oó]n\s*:\s*pendiente\b", r"\1\2Decisión: Aprobada"),
        (
            r"\bla aprobaci[oó]n humana autorizada sigue pendiente\b",
            "La aprobación autorizada está registrada",
        ),
        (
            r"\bla entrega al cliente est[aá] bloqueada\b",
            "La entrega se controla por separado",
        ),
        (r"\bborrador automatizado\b", "FINAL APROBADO"),
        (
            r"\baprobaci[oó]n humana\s*:\s*pendiente\b",
            "Aprobación humana: Registrada",
        ),
        (
            r"\b(?:entrega al cliente|entrega)\s*:\s*bloqueada\b",
            "Entrega al cliente: Controlada por separado",
        ),
        (
            r"\bclient delivery\s*:\s*blocked\b",
            "Client delivery: Controlled separately",
        ),
        (
            r"\b(?:entrega al cliente|entrega) (?:permanece )?bloqueada\b",
            "la entrega se controla por separado",
        ),
        (
            r"\bbloqueada\s*-\s*requiere aprobaci[oó]n humana\b",
            "FINAL APROBADO - REVISIÓN HUMANA REGISTRADA",
        ),
        (
            r"\bblocked\s*-\s*authorized human approval(?: required)?\b",
            "APPROVED - AUTHORIZED HUMAN REVIEW RECORDED",
        ),
        (
            r"\bno constituye aprobaci[oó]n ni autorizaci[oó]n de entrega\b",
            "la aprobación está registrada y la entrega se controla por separado",
        ),
        (
            r"\bautomated evidence and recommendations are not client approval or delivery authorization\b",
            "human review approval is recorded; delivery authorization remains separately controlled",
        ),
        (
            r"\bla evidencia y las recomendaciones automatizadas no constituyen (?:aprobaci[oó]n del cliente ni autorizaci[oó]n de entrega|aprobaci[oó]n humana ni autorizaci[oó]n de entrega al cliente)\b",
            "la aprobación de revisión humana está registrada; la autorización de entrega se controla por separado",
        ),
        (
            r"\bit is not approval or client[- ]delivery authorization\b",
            "human review approval is recorded; delivery authorization is controlled separately",
        ),
        (
            r"\bel informe es un borrador basado en evidencia\b",
            "El informe es un final aprobado basado en evidencia",
        ),
        (r"\bhuman review required\b", "HUMAN REVIEW RECORDED"),
        (r"\brevisi[oó]n humana requerida\b", "REVISIÓN HUMANA REGISTRADA"),
        (r"\beste borrador inmutable\b", "esta edición aprobada inmutable"),
        (r"\bnuevo borrador\b", "nueva edición"),
        (
            r"\bidentidad exacta del borrador\b",
            "identidad exacta de la edición",
        ),
    ):
        output = re.sub(pattern, replacement, output, flags=re.IGNORECASE)
    # The review-truth appendix uses a distinct approval label in Markdown/HTML.
    # The immutable edition names the separate delivery certificate, never authorization.
    output = re.sub(
        r"(\bFinal human approval\s*:\s*(?:</strong>\s*)?)pending\b",
        r"\1APPROVED",
        output,
        flags=re.IGNORECASE,
    )
    output = re.sub(
        r"(\bClient-delivery authorization\s*:\s*(?:</strong>\s*)?)(?:blocked|pending_authorization)\b",
        r"\1Controlled separately",
        output,
        flags=re.IGNORECASE,
    )
    output = re.sub(
        r"\bthe report is an evidence-bound draft\b",
        "the report is an evidence-bound approved assessment",
        output,
        flags=re.IGNORECASE,
    )
    output = re.sub(
        r"\bNICO generated an automated Comprehensive Technical Assessment draft\b",
        "NICO generated a Comprehensive Technical Assessment",
        output,
        flags=re.IGNORECASE,
    )
    return output


def _completed_briefing_text(value: str) -> str:
    # One current-status label retained in older exact PDFs. Conditional scoring
    # policy and historical scanner observations remain unchanged.
    return re.sub(
        r"(Complete automated briefing\s*[—–Š\x01-]\s*)human disposition pending",
        r"\1candidate dispositions recorded",
        value,
    )


def _approved_node(value: Any) -> Any:
    if isinstance(value, str):
        return _replace_finality_text(value)
    if isinstance(value, list):
        return [_approved_node(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_approved_node(item) for item in value)
    if not isinstance(value, Mapping):
        return value

    output = {str(key): _approved_node(item) for key, item in value.items()}
    authority = {
        "report_finality": "approved_final",
        "automation_finality": "human_approved_accepted_edition",
        "human_review_status": "approved",
        "approval_status": "approved_final",
        "delivery_status": "certificate_controlled",
        "client_delivery_status": "certificate_controlled",
        "human_review_completed": True,
        "client_delivery_allowed": False,
    }
    if isinstance(output.get("human_review_truth"), dict):
        output["human_review_truth"]["final_human_approval_status"] = "approved"
        output["human_review_truth"]["client_delivery_authorization_status"] = "certificate_controlled"
    for key, replacement in authority.items():
        if key in output:
            output[key] = replacement
    return output


def _certificate_pdf(
    *,
    reviewer: str,
    reviewer_role: str,
    decision_reason: str,
    decided_at: str,
    source_pdf_sha256: str,
    run_id: str,
    repository: str,
    commit_sha: str,
    spanish: bool,
) -> bytes:
    from html import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if spanish:
        title = "NICO Comprehensive — FINAL APROBADO"
        heading = "Certificado de revisión humana"
        rows = [
            ["Estado", "FINAL APROBADO"],
            ["Revisor", reviewer],
            ["Función", reviewer_role],
            ["Fecha", decided_at],
            ["Ejecución", run_id],
            ["Repositorio", repository],
            ["Commit", commit_sha],
            ["SHA-256 del PDF fuente", source_pdf_sha256],
        ]
        explanation = (
            "Este PDF final deriva de forma determinista del paquete exacto revisado. "
            "El análisis técnico no cambió; únicamente se sustituyeron los marcadores "
            "de ciclo de vida previos a la aprobación y se agregó este certificado."
        )
        delivery = (
            "La autoridad de entrega se registra por separado en el certificado del "
            "paquete de entrega; este PDF no sustituye ese control."
        )
        reason_label = "Motivo de aprobación"
    else:
        title = "NICO Comprehensive — APPROVED FINAL"
        heading = "Human Review Certificate"
        rows = [
            ["Status", "APPROVED FINAL"],
            ["Reviewer", reviewer],
            ["Reviewer role", reviewer_role],
            ["Approved at", decided_at],
            ["Run", run_id],
            ["Repository", repository],
            ["Commit", commit_sha],
            ["Source PDF SHA-256", source_pdf_sha256],
        ]
        explanation = (
            "This final PDF is deterministically derived from the exact package that "
            "was reviewed. The technical analysis is unchanged; only pre-approval "
            "lifecycle markers were replaced and this certificate was added."
        )
        delivery = (
            "Delivery authority is recorded separately in the certified delivery "
            "package; this PDF does not bypass that control."
        )
        reason_label = "Approval reason"

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        title=title,
        author="NICO",
        invariant=1,
    )
    table = Table(rows, colWidths=[145, 325])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(heading, styles["Heading2"]),
        Spacer(1, 10),
        Paragraph(explanation, styles["BodyText"]),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph(reason_label, styles["Heading3"]),
        Paragraph(escape(decision_reason), styles["BodyText"]),
        Spacer(1, 12),
        Paragraph(delivery, styles["BodyText"]),
    ]
    document.build(story)
    return buffer.getvalue()


def _rewrite_pdf(
    source_pdf: bytes,
    *,
    certificate_pdf: bytes,
    spanish: bool,
    candidate_dispositions_completed: bool = False,
) -> bytes:
    if not source_pdf.startswith(b"%PDF") or not certificate_pdf.startswith(b"%PDF"):
        raise ValueError("comprehensive_approved_report_pdf_invalid")
    writer = PdfWriter(clone_from=io.BytesIO(source_pdf))
    for page_index, page in enumerate(writer.pages):
        page_text = (page.extract_text() or "").upper()
        approval_record_page = (
            "HUMAN REVIEW AND EXACT-ARTIFACT APPROVAL" in page_text
            or "REVISIÓN HUMANA" in page_text and "APROBACIÓN" in page_text
        )
        cover_page = page_index == 0
        stream = ContentStream(page.get_contents(), writer)
        changed = False
        # ReportLab can wrap this exact lifecycle sentence across text operators.
        # Require both adjacent fragments; never rewrite an isolated technical status.
        fragments = []
        for operands, operator in stream.operations:
            targets = operands[0] if operator == b"TJ" and operands else operands
            if operator not in {b"Tj", b"'", b'"', b"TJ"}:
                continue
            fragments.extend((targets, index) for index, item in enumerate(targets)
                             if isinstance(item, TextStringObject))
        for (left, left_index), (right, right_index) in zip(fragments, fragments[1:]):
            if (re.search(r"la entrega al cliente permanece$", str(left[left_index]), re.IGNORECASE)
                    and str(right[right_index]).strip().casefold() == "bloqueada."):
                left[left_index] = TextStringObject(re.sub(
                    r"la entrega al cliente permanece$", "la entrega se controla",
                    str(left[left_index]), flags=re.IGNORECASE,
                ))
                right[right_index] = TextStringObject("por separado.")
                changed = True
        review_truth_page = "HUMAN REVIEW AND APPROVAL TRUTH" in page_text
        review_truth_value_label = ""
        for operands, operator in stream.operations:
            if operator in {b"Tj", b"'", b'"'}:
                targets = operands
            elif operator == b"TJ" and operands:
                targets = operands[0]
            else:
                continue
            for index, operand in enumerate(targets):
                if isinstance(operand, TextStringObject):
                    original = str(operand)
                    updated = _replace_finality_text(original)
                    if candidate_dispositions_completed:
                        updated = _completed_briefing_text(updated)
                    if review_truth_page:
                        normalized = original.strip().casefold()
                        if review_truth_value_label == "final human approval" and normalized == "pending":
                            updated = "APPROVED"
                        elif review_truth_value_label == "client-delivery authorization" and normalized in {
                            "blocked", "pending_authorization"
                        }:
                            updated = "Controlled separately"
                        review_truth_value_label = normalized if normalized in {
                            "final human approval", "client-delivery authorization"
                        } else ""
                    if (cover_page or approval_record_page) and updated == original:
                        normalized = original.strip().casefold()
                        if normalized == "pending":
                            updated = "Approved"
                        elif normalized == "blocked":
                            updated = "Controlled"
                        elif normalized == "pendiente":
                            updated = "Aprobada"
                        elif normalized == "bloqueada":
                            updated = "Controlada"
                    if updated != original:
                        targets[index] = TextStringObject(updated)
                        changed = True
                elif isinstance(operand, ByteStringObject):
                    original_bytes = bytes(operand)
                    updated_bytes = original_bytes
                    for encoding in ("utf-8", "latin-1"):
                        try:
                            decoded = original_bytes.decode(encoding)
                        except UnicodeDecodeError:
                            continue
                        rewritten = _replace_finality_text(decoded)
                        if candidate_dispositions_completed:
                            rewritten = _completed_briefing_text(rewritten)
                        if rewritten != decoded:
                            try:
                                updated_bytes = rewritten.encode(encoding)
                            except UnicodeEncodeError:
                                continue
                            break
                    if updated_bytes != original_bytes:
                        targets[index] = ByteStringObject(updated_bytes)
                        changed = True
        if changed:
            page.replace_contents(stream)

    certificate = PdfReader(io.BytesIO(certificate_pdf))
    for page in certificate.pages:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": (
                "NICO Comprehensive — Final aprobado"
                if spanish
                else "NICO Comprehensive — Approved Final"
            ),
            "/Author": "NICO",
            "/Producer": "NICO deterministic approved-report finalizer",
        }
    )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def build_approved_report_package(
    package: Mapping[str, Any],
    *,
    reviewer: str,
    reviewer_role: str,
    decision_reason: str,
    decided_at: str,
) -> dict[str, Any]:
    """Create the post-review PDF that the separate delivery action may authorize.

    The source review artifact stays independently hash-bound. The approved edition
    contains the same technical content, deterministic lifecycle substitutions, and
    a human-review certificate; delivery authorization remains a later action.
    """

    output = deepcopy(dict(package))
    try:
        source_pdf = base64.b64decode(_text(output.get("pdf_base64")), validate=True)
    except Exception as exc:
        raise ValueError("comprehensive_approved_report_source_pdf_invalid") from exc
    source_pdf_sha256 = hashlib.sha256(source_pdf).hexdigest()
    if (
        not source_pdf.startswith(b"%PDF")
        or source_pdf_sha256 != _text(output.get("pdf_sha256")).casefold()
    ):
        raise ValueError("comprehensive_approved_report_source_pdf_hash_mismatch")

    canonical = _approved_node(output.get("json") or {})
    if not isinstance(canonical, dict) or not canonical:
        raise ValueError("comprehensive_approved_report_canonical_required")
    for field in _MANIFEST_FAMILY_FIELDS:
        canonical.pop(field, None)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or identity.get("report_language")
        or "en"
    )
    spanish = language.casefold().replace("_", "-").startswith("es")
    source_identity = {
        "artifact_schema": "nico.comprehensive_review_source.v1",
        "run_id": _text(identity.get("run_id")),
        "repository": _text(identity.get("repository")),
        "commit_sha": _text(identity.get("commit_sha")),
        "pdf_sha256": source_pdf_sha256,
        "report_artifact_digest": current_report_artifact_digest(output),
    }
    if isinstance(output.get("human_review_truth"), Mapping):
        output["human_review_truth"] = deepcopy(dict(output["human_review_truth"]))
        output["human_review_truth"]["final_human_approval_status"] = "approved"
        output["human_review_truth"]["client_delivery_authorization_status"] = "certificate_controlled"
        output["phase2_review_truth_sha256"] = canonical_sha256(output["human_review_truth"])
    for key in ("findings_csv", "evidence_csv", "jira_csv", "linear_csv"):
        text = output.get(key)
        if not isinstance(text, str) or not text.strip():
            continue
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or "final_human_approval_status" not in reader.fieldnames:
            continue
        finalized_csv = io.StringIO(newline="")
        csv_writer = csv.DictWriter(finalized_csv, fieldnames=reader.fieldnames, lineterminator="\n")
        csv_writer.writeheader()
        for row in reader:
            row["final_human_approval_status"] = "approved"
            if "client_delivery_authorization_status" in row:
                row["client_delivery_authorization_status"] = "certificate_controlled"
            csv_writer.writerow(row)
        output[key] = finalized_csv.getvalue()
        output[f"{key}_sha256"] = hashlib.sha256(output[key].encode("utf-8")).hexdigest()
    canonical["approval_projection"] = {
        "artifact_schema": VERSION,
        "status": "approved_final",
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "decision_reason": decision_reason,
        "decided_at": decided_at,
        "source_review_pdf_sha256": source_pdf_sha256,
        "delivery_authority": "separate_certificate_required",
        "client_delivery_allowed": False,
    }
    certificate = _certificate_pdf(
        reviewer=reviewer,
        reviewer_role=reviewer_role,
        decision_reason=decision_reason,
        decided_at=decided_at,
        source_pdf_sha256=source_pdf_sha256,
        run_id=source_identity["run_id"],
        repository=source_identity["repository"],
        commit_sha=source_identity["commit_sha"],
        spanish=spanish,
    )
    from nico.comprehensive_report_content_render_v66 import _candidate_dispositions_completed

    dispositions_completed = _candidate_dispositions_completed(canonical)
    approved_pdf = _rewrite_pdf(
        source_pdf,
        certificate_pdf=certificate,
        spanish=spanish,
        candidate_dispositions_completed=dispositions_completed,
    )
    approved_pdf_sha256 = hashlib.sha256(approved_pdf).hexdigest()
    markdown = _replace_finality_text(_text(output.get("markdown")))
    rendered_html = _replace_finality_text(_text(output.get("html")))
    if dispositions_completed:
        markdown = _completed_briefing_text(markdown)
        rendered_html = _completed_briefing_text(rendered_html)

    for field in _MANIFEST_FAMILY_FIELDS:
        output.pop(field, None)
    filename = re.sub(
        (
            r"-(?:(?:AUTOMATED-)?DRAFT(?:-PENDING-APPROVAL)?|"
            r"APPROVED-FINAL|FINAL(?:-PENDING-APPROVAL)?)\.pdf$"
        ),
        "-APPROVED-FINAL.pdf",
        _text(output.get("pdf_filename")) or "nico-comprehensive-APPROVED-FINAL.pdf",
        flags=re.IGNORECASE,
    )
    if not filename.casefold().endswith("-approved-final.pdf"):
        stem = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE).strip()
        filename = f"{stem or 'nico-comprehensive'}-APPROVED-FINAL.pdf"
    page_count = len(PdfReader(io.BytesIO(approved_pdf)).pages)
    source_page_count = len(PdfReader(io.BytesIO(source_pdf)).pages)
    core_page_count = min(
        int(output.get("core_report_page_count") or source_page_count),
        source_page_count,
    )
    output.update(
        {
            "approved_report_version": VERSION,
            "source_review_artifact_identity": source_identity,
            "json": canonical,
            "canonical_truth_sha256": canonical_sha256(canonical),
            "markdown": markdown,
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "html": rendered_html,
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_base64": base64.b64encode(approved_pdf).decode("ascii"),
            "pdf_sha256": approved_pdf_sha256,
            "pdf_filename": filename,
            "pdf_page_count": page_count,
            "core_report_page_count": core_page_count,
            "final_package_page_count": page_count,
            "report_finality": "approved_final",
            "human_review_status": "approved",
            "human_review_completed": True,
            "approval_status": "approved_final",
            "delivery_status": "certificate_controlled",
            "client_delivery_status": "certificate_controlled",
            "human_review_required": True,
            "client_delivery_allowed": False,
            "analysis_regenerated_during_approval": False,
            "lifecycle_markers_finalized_during_approval": True,
        }
    )
    return output


__all__ = ["VERSION", "build_approved_report_package"]
