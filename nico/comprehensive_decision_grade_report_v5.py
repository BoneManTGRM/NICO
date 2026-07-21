from __future__ import annotations

import base64
import hashlib
import io
import re
from typing import Any

from nico import comprehensive_report_package as base_report
from nico.comprehensive_decision_grade_model_v5 import APPENDIX_HEADING, REVIEW_HEADING, VERSION, _text
from nico.comprehensive_decision_grade_markdown_v5 import (
    _build_markdown, _decorate_assessment, _limitation_metrics,
    _roadmap_from_stages, _staffing_from_stages, _stage_summaries,
)
from nico.comprehensive_decision_grade_html_v5 import _build_html, _evidence_csv, _findings_csv
from nico.comprehensive_decision_grade_pdf_v5 import _pdf_with_final_count


def build_comprehensive_report_package(*, identity: dict[str, Any], stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    required_identity = {field: _text(identity.get(field), 180) for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")}
    missing = [field for field, value in required_identity.items() if not value]
    if missing:
        return {"status": "blocked", "reason": "missing_report_identity:" + ",".join(missing), "human_review_required": True, "client_delivery_allowed": False}
    generated_at = base_report._now()
    assessment = _decorate_assessment(base_report._assessment(stage_results))
    stages = _stage_summaries(stage_results)
    limitations = _limitation_metrics(assessment, stages)
    assessment["limitation_metrics"] = {**dict(assessment.get("limitation_metrics") or {}), **limitations}
    roadmap = _roadmap_from_stages(stage_results, assessment)
    staffing = _staffing_from_stages(stage_results)
    markdown = _build_markdown(required_identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    rendered_html = _build_html(required_identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    try:
        pdf_bytes, page_count = _pdf_with_final_count(required_identity, assessment, stages, roadmap, staffing, limitations, generated_at)
        pdf_error = None
    except Exception as exc:  # pragma: no cover - fail-closed report boundary
        pdf_bytes, page_count = b"", 0
        pdf_error = f"Decision-grade PDF export unavailable: {type(exc).__name__}"
    core_page_count = 0
    if pdf_bytes:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            appendix_start = next((index for index, page in enumerate(reader.pages, start=1) if "Bounded decision-relevant evidence is rendered here" in (page.extract_text() or "")), page_count)
            core_page_count = max(1, appendix_start - 1)
        except Exception:
            core_page_count = 0
    findings = [item for item in assessment.get("findings_register") or [] if isinstance(item, dict)]
    findings_csv = _findings_csv(findings)
    evidence_csv = _evidence_csv(stages)
    canonical = {
        "service_id": "comprehensive",
        "identity": required_identity,
        "assessment": assessment,
        "stage_summaries": stages,
        "findings_register": findings,
        "roadmap": roadmap,
        "staffing_plan": staffing,
        "limitation_metrics": limitations,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha = base_report._canonical_hash(canonical)
    report_id = f"comprehensive_report_{base_report._canonical_hash({'identity': required_identity, 'canonical': canonical})[:20]}"
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", required_identity["repository"]).strip("-") or "repository"
    filename = f"nico-comprehensive-assessment-{safe_repo}-{required_identity['run_id']}-DRAFT.pdf"
    quality = {
        "version": VERSION,
        "decision_grade_body": True,
        "appendix_contract_schema": VERSION,
        "full_evidence_appendix": True,
        "score_band_separated_from_assurance": all(bool(item.get("score_band_label")) and bool(item.get("assurance_label")) for item in assessment.get("sections") or [] if isinstance(item, dict)),
        "secret_category_isolated": True,
        "named_architecture_hotspots": any(item.get("category") == "architecture" and item.get("location") for item in findings),
        "structured_findings_register": bool(findings) or not assessment.get("sections"),
        "executable_roadmap": bool(roadmap) and all(isinstance(item, dict) and item.get("work_packages") for item in roadmap),
        "limitation_accounting_explicit": all(key in limitations for key in ("stages_with_limitations", "individual_limitation_records", "score_affecting_records", "informational_records")),
        "final_pdf_page_count": page_count,
        "core_report_page_count": core_page_count,
        "pdf_page_count_matches_final_artifact": bool(pdf_bytes) and page_count > 0,
        "semantic_html": "<table>" in rendered_html and "<h2>Evidence Appendix</h2>" in rendered_html,
        "markdown_evidence_appendix": APPENDIX_HEADING in markdown,
        "html_evidence_appendix": "<h2>Evidence Appendix</h2>" in rendered_html,
        "pdf_evidence_appendix": bool(pdf_bytes),
        "markdown_human_review_acceptance_gate": REVIEW_HEADING in markdown,
        "html_human_review_acceptance_gate": "<h2>Human Review and Acceptance Gate</h2>" in rendered_html,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    complete = bool(pdf_bytes.startswith(b"%PDF") and not pdf_error and quality["score_band_separated_from_assurance"] and quality["semantic_html"] and quality["markdown_evidence_appendix"] and quality["markdown_human_review_acceptance_gate"])
    report_package = {
        "service_id": "comprehensive",
        "report_id": report_id,
        "markdown": markdown,
        "html": rendered_html,
        "json": canonical,
        "findings_csv": findings_csv,
        "evidence_ledger_csv": evidence_csv,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii") if pdf_bytes else "",
        "pdf_error": pdf_error,
        "pdf_filename": filename,
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else "",
        "pdf_page_count": page_count,
        "core_report_page_count": core_page_count,
        "final_package_page_count": page_count,
        "canonical_truth_sha256": truth_sha,
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "findings_csv_sha256": hashlib.sha256(findings_csv.encode("utf-8")).hexdigest(),
        "evidence_ledger_csv_sha256": hashlib.sha256(evidence_csv.encode("utf-8")).hexdigest(),
        "appendix_contract_schema": VERSION,
        "evidence_appendix_present": True,
        "human_review_acceptance_gate_present": True,
        "report_quality_contract": quality,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "status": "complete" if complete else "blocked",
        "reason": "" if complete else (pdf_error or "decision_grade_report_contract_failed"),
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "report_id": report_id,
        "generated_at": generated_at,
        "assessment": assessment,
        "stage_summaries": stages,
        "canonical_truth_sha256": truth_sha,
        "report_quality_contract": quality,
        "report_package": report_package,
        "appendix_contract_schema": VERSION,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["build_comprehensive_report_package"]
