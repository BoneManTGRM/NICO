from __future__ import annotations

import base64
import csv
import hashlib
import html
import io
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from nico.comprehensive_review_work_v2 import review_work_projection

VERSION = "nico.comprehensive_review_report_truth.v1"
_MARKDOWN_START = "<!-- NICO_PHASE2_REVIEW_TRUTH_START -->"
_MARKDOWN_END = "<!-- NICO_PHASE2_REVIEW_TRUTH_END -->"
_HTML_START = "<!-- NICO_PHASE2_REVIEW_TRUTH_START -->"
_HTML_END = "<!-- NICO_PHASE2_REVIEW_TRUTH_END -->"
_REPORT_STAGE_IDS = (
    "final_comprehensive_report_generation",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
    "report_generation",
    "reports",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _triage_counts(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    verdicts = [
        _text(candidate.get("technical_triage_verdict")).casefold()
        for candidate in candidates
    ]
    completed = sum(bool(value) for value in verdicts)
    total = len(candidates)
    return {
        "raw_scanner_candidates": total,
        "technical_triage_completed": completed,
        "technical_triage_pending": total - completed,
        "technical_triage_coverage_pct": round((completed / total) * 100.0, 1) if total else 100.0,
        "not_actionable": sum(value == "not_actionable" for value in verdicts),
        "needs_review": sum(value == "needs_review" for value in verdicts),
        "confirmed": sum(value == "confirmed" for value in verdicts),
    }


def build_review_truth(record: Mapping[str, Any]) -> dict[str, Any]:
    projection = review_work_projection(record)
    candidates = [
        dict(candidate)
        for candidate in projection.get("candidates") or []
        if isinstance(candidate, Mapping)
    ]
    triage = _triage_counts(candidates)
    confirmed_material = 0
    candidate_review: list[dict[str, Any]] = []
    for candidate in candidates:
        disposition = candidate.get("human_disposition")
        disposition = dict(disposition) if isinstance(disposition, Mapping) else {}
        human_value = _text(disposition.get("disposition")).casefold()
        severity = _text(candidate.get("severity")).casefold()
        material = human_value == "confirmed" and severity in {"critical", "high", "material"}
        if material:
            confirmed_material += 1
        candidate_review.append(
            {
                "candidate_id": _text(candidate.get("candidate_id")),
                "cluster_id": _text(candidate.get("cluster_id")),
                "category": _text(candidate.get("category")),
                "scanner": _text(candidate.get("scanner")),
                "rule": _text(candidate.get("rule") or candidate.get("rule_id")),
                "advisory": _text(candidate.get("advisory") or candidate.get("advisory_id")),
                "severity": _text(candidate.get("severity")),
                "package": _text(candidate.get("package") or candidate.get("package_name")),
                "version": _text(candidate.get("version") or candidate.get("package_version")),
                "ecosystem": _text(candidate.get("ecosystem")),
                "manifest": _text(candidate.get("manifest") or candidate.get("manifest_path")),
                "path": _text(candidate.get("path") or candidate.get("file_path")),
                "line": candidate.get("line") or candidate.get("line_number"),
                "technical_triage_verdict": _text(candidate.get("technical_triage_verdict")),
                "technical_triage_confidence": candidate.get("technical_triage_confidence"),
                "primary_review_queue": _text(candidate.get("primary_review_queue")),
                "human_disposition_state": _text(candidate.get("human_disposition_state")),
                "human_disposition": human_value,
                "human_reviewer": _text(disposition.get("reviewer")),
                "human_reviewer_role": _text(disposition.get("reviewer_role")),
                "human_reviewed_at": _text(disposition.get("decided_at")),
                "human_rationale": _text(disposition.get("rationale")),
                "residual_risk": _text(disposition.get("residual_risk")),
                "residual_risk_owner": _text(disposition.get("residual_risk_owner")),
                "confirmed_material_finding": material,
                "quality_control_sample": candidate.get("quality_control_sample") is True,
                "evidence_change_state": _text(candidate.get("evidence_change_state")),
            }
        )

    pending = int(projection.get("remaining_candidate_count") or 0)
    completed = int(projection.get("dispositioned_candidate_count") or 0)
    return {
        "artifact_schema": VERSION,
        "concept_boundaries": {
            "raw_scanner_observation": "scanner evidence only; not a human finding",
            "nico_automated_technical_triage": "automated recommendation only; not a human disposition",
            "authorized_human_disposition": "explicit authorized reviewer decision",
            "confirmed_material_finding": "material finding after authorized human disposition",
            "final_human_approval": "separate package-level approval gate",
            "client_delivery_authorization": "separate post-approval delivery gate",
        },
        **triage,
        "authorized_human_disposition_pending": pending,
        "authorized_human_disposition_completed": completed,
        "confirmed_material_findings": confirmed_material,
        "final_human_approval_status": "pending",
        "client_delivery_authorization_status": "blocked",
        "technical_triage_is_not_human_disposition": True,
        "human_disposition_is_not_final_approval": True,
        "final_approval_is_not_implicit_client_delivery": True,
        "review_ready_for_final_approval": projection.get("ready_for_final_approval") is True,
        "quality_control_sampling": deepcopy(projection.get("quality_control_sampling") or {}),
        "workload_metrics": deepcopy(projection.get("workload_metrics") or {}),
        "queue_counts": deepcopy(projection.get("queue_counts") or {}),
        "review_source_sha256": _text(projection.get("review_source_sha256")),
        "scope_binding": deepcopy(projection.get("scope_binding") or {}),
        "candidate_review": candidate_review,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _markdown_section(truth: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            _MARKDOWN_START,
            "## Human Review and Approval Truth",
            "",
            "This section keeps scanner observations, NICO technical triage, authorized human disposition, confirmed material findings, final human approval, and client-delivery authorization separate.",
            "",
            f"- Raw scanner candidates: {truth['raw_scanner_candidates']}",
            f"- Automated technical triage completed: {truth['technical_triage_completed']}",
            f"- Technical triage pending: {truth['technical_triage_pending']}",
            f"- Technical triage coverage: {truth['technical_triage_coverage_pct']}%",
            f"- Automated `not_actionable`: {truth['not_actionable']}",
            f"- Automated `needs_review`: {truth['needs_review']}",
            f"- Automated `confirmed`: {truth['confirmed']}",
            f"- Authorized human disposition pending: {truth['authorized_human_disposition_pending']}",
            f"- Authorized human disposition completed: {truth['authorized_human_disposition_completed']}",
            f"- Confirmed material findings: {truth['confirmed_material_findings']}",
            f"- Final human approval: {truth['final_human_approval_status'].upper()}",
            f"- Client-delivery authorization: {truth['client_delivery_authorization_status'].upper()}",
            "",
            "Automated technical triage does not create human assurance. Human disposition does not itself approve the final package. Client delivery remains blocked until the separate protected approval and delivery gates succeed.",
            _MARKDOWN_END,
        ]
    )


def _replace_marked_text(text: str, section: str, start: str, end: str) -> str:
    start_index = text.find(start)
    end_index = text.find(end)
    if start_index >= 0 and end_index >= start_index:
        end_index += len(end)
        return text[:start_index].rstrip() + "\n\n" + section + "\n" + text[end_index:].lstrip()
    return text.rstrip() + "\n\n" + section + "\n"


def _html_section(truth: Mapping[str, Any]) -> str:
    rows = [
        ("Raw scanner candidates", truth["raw_scanner_candidates"]),
        ("Automated technical triage completed", truth["technical_triage_completed"]),
        ("Technical triage pending", truth["technical_triage_pending"]),
        ("Technical triage coverage", f"{truth['technical_triage_coverage_pct']}%"),
        ("Automated not_actionable", truth["not_actionable"]),
        ("Automated needs_review", truth["needs_review"]),
        ("Automated confirmed", truth["confirmed"]),
        ("Authorized human disposition pending", truth["authorized_human_disposition_pending"]),
        ("Authorized human disposition completed", truth["authorized_human_disposition_completed"]),
        ("Confirmed material findings", truth["confirmed_material_findings"]),
        ("Final human approval", str(truth["final_human_approval_status"]).upper()),
        ("Client-delivery authorization", str(truth["client_delivery_authorization_status"]).upper()),
    ]
    items = "".join(
        f"<li><strong>{html.escape(str(label))}:</strong> {html.escape(str(value))}</li>"
        for label, value in rows
    )
    return (
        f"{_HTML_START}<section id=\"nico-phase2-review-truth\"><h2>Human Review and Approval Truth</h2>"
        "<p>Scanner observations, NICO technical triage, authorized human disposition, confirmed material findings, final human approval, and client-delivery authorization are separate states.</p>"
        f"<ul>{items}</ul>"
        "<p>Automated technical triage does not create human assurance. Human disposition does not itself approve the final package. Client delivery remains blocked until the separate protected gates succeed.</p>"
        f"</section>{_HTML_END}"
    )


def _replace_html(text: str, section: str) -> str:
    start_index = text.find(_HTML_START)
    end_index = text.find(_HTML_END)
    if start_index >= 0 and end_index >= start_index:
        end_index += len(_HTML_END)
        return text[:start_index] + section + text[end_index:]
    for marker in ("</article>", "</main>", "</body>"):
        index = text.rfind(marker)
        if index >= 0:
            return text[:index] + section + text[index:]
    return text + section


def _review_pdf_page(truth: Mapping[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.lib import colors

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title="NICO Human Review and Approval Truth", invariant=1)
    rows = [
        ["Raw scanner candidates", str(truth["raw_scanner_candidates"])],
        ["Automated technical triage completed", str(truth["technical_triage_completed"])],
        ["Technical triage pending", str(truth["technical_triage_pending"])],
        ["Technical triage coverage", f"{truth['technical_triage_coverage_pct']}%"],
        ["Automated not_actionable", str(truth["not_actionable"])],
        ["Automated needs_review", str(truth["needs_review"])],
        ["Automated confirmed", str(truth["confirmed"])],
        ["Authorized human disposition pending", str(truth["authorized_human_disposition_pending"])],
        ["Authorized human disposition completed", str(truth["authorized_human_disposition_completed"])],
        ["Confirmed material findings", str(truth["confirmed_material_findings"])],
        ["Final human approval", str(truth["final_human_approval_status"]).upper()],
        ["Client-delivery authorization", str(truth["client_delivery_authorization_status"]).upper()],
    ]
    table = Table(rows, colWidths=[310, 150])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story = [
        Paragraph("Human Review and Approval Truth", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "Scanner observations, NICO automated technical triage, authorized human disposition, confirmed material findings, final human approval, and client-delivery authorization are separate states.",
            styles["BodyText"],
        ),
        Spacer(1, 12),
        table,
        Spacer(1, 12),
        Paragraph(
            "Automated technical triage does not create human assurance. Human disposition does not itself approve the final package. Client delivery remains blocked until the separate protected approval and delivery gates succeed.",
            styles["BodyText"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()


def _synchronize_pdf(package: dict[str, Any], truth: Mapping[str, Any]) -> None:
    from pypdf import PdfReader, PdfWriter

    try:
        current = base64.b64decode(_text(package.get("pdf_base64")), validate=True)
    except Exception as exc:
        raise ValueError("phase2_review_truth_pdf_invalid") from exc
    if not current.startswith(b"%PDF"):
        raise ValueError("phase2_review_truth_pdf_invalid")
    reader = PdfReader(io.BytesIO(current))
    base_count = int(package.get("phase2_review_base_pdf_page_count") or len(reader.pages))
    if base_count < 1 or base_count > len(reader.pages):
        raise ValueError("phase2_review_truth_pdf_base_page_count_invalid")
    appendix = PdfReader(io.BytesIO(_review_pdf_page(truth)))
    writer = PdfWriter()
    for index in range(base_count):
        writer.add_page(reader.pages[index])
    for page in appendix.pages:
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "NICO Comprehensive Technical Assessment",
            "/Author": "NICO",
            "/Producer": "NICO Phase 2 review-truth synchronizer",
        }
    )
    output = io.BytesIO()
    writer.write(output)
    pdf = output.getvalue()
    package["phase2_review_base_pdf_page_count"] = base_count
    package["pdf_base64"] = base64.b64encode(pdf).decode("ascii")
    package["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
    package["pdf_size_bytes"] = len(pdf)
    package["pdf_page_count"] = base_count + len(appendix.pages)


def _candidate_csv(truth: Mapping[str, Any]) -> str:
    fields = (
        "candidate_id",
        "cluster_id",
        "category",
        "scanner",
        "rule",
        "advisory",
        "severity",
        "package",
        "version",
        "ecosystem",
        "manifest",
        "path",
        "line",
        "technical_triage_verdict",
        "technical_triage_confidence",
        "primary_review_queue",
        "human_disposition_state",
        "human_disposition",
        "human_reviewer",
        "human_reviewer_role",
        "human_reviewed_at",
        "human_rationale",
        "residual_risk",
        "residual_risk_owner",
        "confirmed_material_finding",
        "quality_control_sample",
        "evidence_change_state",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in truth.get("candidate_review") or []:
        if isinstance(row, Mapping):
            writer.writerow({field: row.get(field, "") for field in fields})
    return buffer.getvalue()


def _augment_csv(value: Any, truth: Mapping[str, Any]) -> str:
    text = str(value or "")
    if not text.strip():
        return text
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return text
    added = [
        "human_dispositions_pending",
        "human_dispositions_completed",
        "final_human_approval_status",
        "client_delivery_authorization_status",
    ]
    fields = [*reader.fieldnames, *(field for field in added if field not in reader.fieldnames)]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in reader:
        row.update(
            {
                "human_dispositions_pending": truth["authorized_human_disposition_pending"],
                "human_dispositions_completed": truth["authorized_human_disposition_completed"],
                "final_human_approval_status": truth["final_human_approval_status"],
                "client_delivery_authorization_status": truth["client_delivery_authorization_status"],
            }
        )
        writer.writerow(row)
    return output.getvalue()


def _synchronize_package(package: dict[str, Any], truth: Mapping[str, Any]) -> None:
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    canonical = deepcopy(dict(canonical))
    canonical["human_review_truth"] = deepcopy(dict(truth))
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    assessment = deepcopy(dict(assessment))
    assessment["human_review_truth"] = deepcopy(dict(truth))
    assessment["human_review_required"] = True
    assessment["client_delivery_allowed"] = False
    canonical["assessment"] = assessment
    for key in (
        "executive_brief",
        "client_evidence_summary",
        "scoring_explanation",
        "human_review_section",
        "approval_package",
    ):
        existing = canonical.get(key) if isinstance(canonical.get(key), Mapping) else {}
        section = deepcopy(dict(existing))
        section["human_review_truth"] = deepcopy(dict(truth))
        canonical[key] = section
    canonical["authorized_human_review_candidate_register"] = deepcopy(truth.get("candidate_review") or [])
    canonical["human_review_required"] = True
    canonical["client_delivery_allowed"] = False
    package["json"] = canonical
    package["human_review_truth"] = deepcopy(dict(truth))
    package["candidate_register_csv"] = _candidate_csv(truth)
    for key in ("findings_csv", "evidence_csv", "jira_csv", "linear_csv"):
        if key in package:
            package[key] = _augment_csv(package.get(key), truth)

    markdown = str(package.get("markdown") or "")
    if markdown:
        package["markdown"] = _replace_marked_text(
            markdown,
            _markdown_section(truth),
            _MARKDOWN_START,
            _MARKDOWN_END,
        )
    rendered_html = str(package.get("html") or "")
    if rendered_html:
        package["html"] = _replace_html(rendered_html, _html_section(truth))
    if package.get("pdf_base64"):
        _synchronize_pdf(package, truth)

    truth_sha = _canonical_hash(canonical)
    package["canonical_truth_sha256"] = truth_sha
    package["phase2_review_truth_sha256"] = _canonical_hash(truth)
    if package.get("markdown"):
        package["markdown_sha256"] = _sha256_text(str(package["markdown"]))
    if package.get("html"):
        package["html_sha256"] = _sha256_text(str(package["html"]))
    package["json_sha256"] = _canonical_hash(canonical)
    integrity = package.get("content_integrity")
    if isinstance(integrity, Mapping):
        updated_integrity = deepcopy(dict(integrity))
        updated_integrity.update(
            {
                "markdown_sha256": package.get("markdown_sha256", ""),
                "html_sha256": package.get("html_sha256", ""),
                "pdf_sha256": package.get("pdf_sha256", ""),
                "json_sha256": package.get("json_sha256", ""),
            }
        )
        package["content_integrity"] = updated_integrity


def synchronize_review_truth(record: Mapping[str, Any]) -> dict[str, Any]:
    """Synchronize current pre-approval human-review truth into the one report package.

    Approved editions are immutable and are never rewritten here. Approval and delivery
    truth after acceptance is carried by the existing accepted-edition and delivery
    certificates, which remain separate from the report artifact itself.
    """

    updated = deepcopy(dict(record))
    if updated.get("human_review_completed") is True or isinstance(updated.get("accepted_edition"), Mapping):
        return updated
    truth = build_review_truth(updated)
    stage_results = updated.get("stage_results")
    if isinstance(stage_results, Mapping):
        stages = deepcopy(dict(stage_results))
        for stage_id in _REPORT_STAGE_IDS:
            stage = stages.get(stage_id)
            if not isinstance(stage, Mapping):
                continue
            stage_copy = deepcopy(dict(stage))
            for key in ("report_package", "reports"):
                package = stage_copy.get(key)
                if isinstance(package, Mapping) and (
                    package.get("json") or package.get("markdown") or package.get("pdf_base64")
                ):
                    package_copy = deepcopy(dict(package))
                    _synchronize_package(package_copy, truth)
                    stage_copy[key] = package_copy
            stages[stage_id] = stage_copy
        updated["stage_results"] = stages
    top = updated.get("reports")
    if isinstance(top, Mapping) and (top.get("json") or top.get("markdown") or top.get("pdf_base64")):
        top_copy = deepcopy(dict(top))
        _synchronize_package(top_copy, truth)
        updated["reports"] = top_copy

    from nico.comprehensive_run_record import _record_hash

    updated["integrity_sha256"] = _record_hash(updated)
    return updated


__all__ = ["VERSION", "build_review_truth", "synchronize_review_truth"]
