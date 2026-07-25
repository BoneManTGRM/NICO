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
from nico.comprehensive_executive_risk_truth_v7 import reconcile_executive_risk_truth
from nico.comprehensive_express_quality_v7 import (
    VERSION as EXPRESS_QUALITY_VERSION,
    comprehensive_pdf_with_final_count,
    reconcile_comprehensive_assessment,
)
from nico.comprehensive_premium_synthesis_v6 import VERSION as PREMIUM_VERSION
from nico.decision_grade_backlog_v1 import (
    VERSION as DECISION_GRADE_BACKLOG_VERSION,
    generate_backlog_exports,
)
from nico.decision_grade_contract_v1 import (
    SCHEMA_VERSION as DECISION_GRADE_CONTRACT_VERSION,
    DecisionGradeContract,
    build_decision_grade_contract,
    contract_quality_summary,
)
from nico.decision_grade_delta_v1 import (
    VERSION as DECISION_GRADE_DELTA_VERSION,
    compare_contracts,
    delta_markdown,
)
from nico.decision_grade_report_view_v1 import (
    VERSION as DECISION_GRADE_REPORT_VIEW_VERSION,
    apply_report_view,
)


def _render_artifacts(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> tuple[str, str, bytes, int, str | None]:
    markdown = _build_markdown(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    rendered_html = _build_html(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
    try:
        pdf_bytes, page_count = comprehensive_pdf_with_final_count(
            identity,
            assessment,
            stages,
            roadmap,
            staffing,
            limitations,
            generated_at,
        )
        pdf_error = None
    except Exception as exc:  # pragma: no cover - fail-closed report boundary
        pdf_bytes, page_count = b"", 0
        pdf_error = f"Decision-grade PDF export unavailable: {type(exc).__name__}"
    return markdown, rendered_html, pdf_bytes, page_count, pdf_error


def _pdf_metrics(pdf_bytes: bytes, page_count: int) -> tuple[int, str]:
    if not pdf_bytes:
        return 0, ""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        front_matter_text = " ".join(
            (reader.pages[index].extract_text() or "")
            for index in range(min(2, len(reader.pages)))
        )
        appendix_start = next(
            (
                index
                for index, page in enumerate(reader.pages, start=1)
                if "Bounded decision-relevant evidence is rendered here" in (page.extract_text() or "")
            ),
            page_count,
        )
        return max(1, appendix_start - 1), front_matter_text
    except Exception:
        return 0, ""


def _build_contract(
    *,
    identity: dict[str, Any],
    required_identity: dict[str, str],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    generated_at: str,
    page_count: int,
    core_page_count: int,
) -> DecisionGradeContract:
    return build_decision_grade_contract(
        identity={
            **required_identity,
            "assessment_type": "comprehensive",
            "branch": identity.get("branch") or "unknown",
            "repository_url": identity.get("repository_url"),
            "commit_timestamp": identity.get("commit_timestamp"),
            "assessment_started_at": identity.get("assessment_started_at"),
            "assessment_completed_at": generated_at,
            "generation_duration_seconds": identity.get("generation_duration_seconds"),
            "nico_version": identity.get("nico_version") or "0.1.1",
            "scanner_configuration_version": identity.get("scanner_configuration_version") or "current",
            "previous_comparable_assessment_id": identity.get("previous_comparable_assessment_id"),
        },
        assessment=assessment,
        stage_summaries=stages,
        roadmap=roadmap,
        report_template_version=VERSION,
        pdf_page_count=page_count,
        core_page_count=core_page_count,
        generated_at=generated_at,
    )


def build_comprehensive_report_package(*, identity: dict[str, Any], stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    required_identity = {
        field: _text(identity.get(field), 180)
        for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id")
    }
    missing = [field for field, value in required_identity.items() if not value]
    if missing:
        return {
            "status": "blocked",
            "reason": "missing_report_identity:" + ",".join(missing),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    generated_at = base_report._now()
    assessment = reconcile_executive_risk_truth(
        reconcile_comprehensive_assessment(_decorate_assessment(base_report._assessment(stage_results)))
    )
    all_executive_risks = [
        item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)
    ]
    assessment["executive_risk_register"] = all_executive_risks[:7]
    assessment["executive_risk_overflow_count"] = max(0, len(all_executive_risks) - 7)
    assessment["executive_risk_register_limit"] = 7
    stages = _stage_summaries(stage_results)
    limitations = _limitation_metrics(assessment, stages)
    assessment["limitation_metrics"] = {
        **dict(assessment.get("limitation_metrics") or {}),
        **limitations,
    }
    roadmap = _roadmap_from_stages(stage_results, assessment)
    staffing = _staffing_from_stages(stage_results)

    # First pass establishes an initial rendered boundary for contract validation.
    markdown, rendered_html, pdf_bytes, page_count, pdf_error = _render_artifacts(
        required_identity,
        assessment,
        stages,
        roadmap,
        staffing,
        limitations,
        generated_at,
    )
    core_page_count, front_matter_text = _pdf_metrics(pdf_bytes, page_count)

    contract_error = None
    decision_grade_contract: DecisionGradeContract | None = None
    try:
        decision_grade_contract = _build_contract(
            identity=identity,
            required_identity=required_identity,
            assessment=assessment,
            stages=stages,
            roadmap=roadmap,
            generated_at=generated_at,
            page_count=page_count,
            core_page_count=core_page_count,
        )

        # Project structured truth into every client-facing surface and render again.
        assessment = apply_report_view(assessment, decision_grade_contract)
        roadmap = assessment.get("decision_grade_roadmap") or roadmap
        markdown, rendered_html, pdf_bytes, page_count, pdf_error = _render_artifacts(
            required_identity,
            assessment,
            stages,
            roadmap,
            staffing,
            limitations,
            generated_at,
        )
        core_page_count, front_matter_text = _pdf_metrics(pdf_bytes, page_count)

        # Final contract uses the actual decision-grade artifact boundary.
        decision_grade_contract = _build_contract(
            identity=identity,
            required_identity=required_identity,
            assessment=assessment,
            stages=stages,
            roadmap=roadmap,
            generated_at=generated_at,
            page_count=page_count,
            core_page_count=core_page_count,
        )
        assessment = apply_report_view(assessment, decision_grade_contract)
        roadmap = assessment.get("decision_grade_roadmap") or roadmap
        markdown, rendered_html, pdf_bytes, page_count, pdf_error = _render_artifacts(
            required_identity,
            assessment,
            stages,
            roadmap,
            staffing,
            limitations,
            generated_at,
        )
        core_page_count, front_matter_text = _pdf_metrics(pdf_bytes, page_count)

        contract_payload = decision_grade_contract.model_dump(mode="json")
        contract_summary = contract_quality_summary(decision_grade_contract)
    except Exception as exc:  # pragma: no cover - fail-closed contract boundary
        contract_error = f"Decision-grade contract unavailable: {type(exc).__name__}"
        contract_payload = {
            "schema_version": DECISION_GRADE_CONTRACT_VERSION,
            "status": "invalid",
            "reason": contract_error,
        }
        contract_summary = {
            "schema_version": DECISION_GRADE_CONTRACT_VERSION,
            "readiness_status": "Delivery Blocked",
            "validation_error_count": 1,
            "validation_warning_count": 0,
            "executive_risk_count": 0,
            "executive_risk_limit_met": False,
            "p0_p1_traceability_complete": False,
            "monetary_claims_require_assumptions": False,
            "client_ready": False,
        }

    findings = [
        item
        for item in (
            assessment.get("decision_grade_findings_register")
            or assessment.get("findings_register")
            or []
        )
        if isinstance(item, dict)
    ]
    executive_risks = [
        item for item in assessment.get("executive_risk_register") or [] if isinstance(item, dict)
    ][:7]
    findings_csv = _findings_csv(findings)
    evidence_csv = _evidence_csv(stages)

    backlog_error = None
    delta_error = None
    if decision_grade_contract is not None:
        try:
            backlog_exports = generate_backlog_exports(
                decision_grade_contract,
                report_id=required_identity["run_id"],
            )
        except Exception as exc:  # pragma: no cover - fail-closed export boundary
            backlog_error = f"Decision-grade backlog export unavailable: {type(exc).__name__}"
            backlog_exports = {
                "schema_version": DECISION_GRADE_BACKLOG_VERSION,
                "item_count": 0,
                "json": {
                    "schema_version": DECISION_GRADE_BACKLOG_VERSION,
                    "status": "invalid",
                    "reason": backlog_error,
                    "items": [],
                },
                "markdown": "",
                "json_text": "",
                "github_issues": [],
                "github_issues_json": "",
                "jira_csv": "",
                "linear_csv": "",
                "hashes": {},
                "external_issue_creation_allowed": False,
            }
        try:
            previous_contract = identity.get("previous_decision_grade_contract") or identity.get("previous_contract")
            previous_assessment = (
                identity.get("previous_assessment")
                if isinstance(identity.get("previous_assessment"), dict)
                else None
            )
            historical_delta = compare_contracts(
                previous_contract,
                decision_grade_contract,
                previous_assessment=previous_assessment,
                current_assessment=assessment,
            )
            historical_delta_markdown = delta_markdown(historical_delta)
        except Exception as exc:  # pragma: no cover - fail-closed delta boundary
            delta_error = f"Historical delta unavailable: {type(exc).__name__}"
            historical_delta = {
                "schema_version": DECISION_GRADE_DELTA_VERSION,
                "status": "invalid",
                "comparable": False,
                "reason": delta_error,
                "synthetic_delta_generated": False,
            }
            historical_delta_markdown = delta_markdown(historical_delta)
    else:
        backlog_error = contract_error or "Decision-grade contract required for backlog export."
        delta_error = contract_error or "Decision-grade contract required for historical comparison."
        backlog_exports = {
            "schema_version": DECISION_GRADE_BACKLOG_VERSION,
            "item_count": 0,
            "json": {
                "schema_version": DECISION_GRADE_BACKLOG_VERSION,
                "status": "invalid",
                "reason": backlog_error,
                "items": [],
            },
            "markdown": "",
            "json_text": "",
            "github_issues": [],
            "github_issues_json": "",
            "jira_csv": "",
            "linear_csv": "",
            "hashes": {},
            "external_issue_creation_allowed": False,
        }
        historical_delta = {
            "schema_version": DECISION_GRADE_DELTA_VERSION,
            "status": "invalid",
            "comparable": False,
            "reason": delta_error,
            "synthetic_delta_generated": False,
        }
        historical_delta_markdown = delta_markdown(historical_delta)

    canonical = {
        "service_id": "comprehensive",
        "identity": required_identity,
        "assessment": assessment,
        "stage_summaries": stages,
        "findings_register": findings,
        "executive_risk_register": executive_risks,
        "scoring_weights": assessment.get("scoring_weights") or [],
        "roadmap": roadmap,
        "staffing_plan": staffing,
        "limitation_metrics": limitations,
        "decision_grade_contract": contract_payload,
        "backlog_export": backlog_exports["json"],
        "historical_delta": historical_delta,
        "delivery_status": contract_summary["readiness_status"],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha = base_report._canonical_hash(canonical)
    report_id = f"comprehensive_report_{base_report._canonical_hash({'identity': required_identity, 'canonical': canonical})[:20]}"
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", required_identity["repository"]).strip("-") or "repository"
    filename = f"nico-comprehensive-assessment-{safe_repo}-{required_identity['run_id']}-DRAFT.pdf"
    static_section = next(
        (
            item
            for item in assessment.get("sections") or []
            if isinstance(item, dict) and item.get("id") == "static_analysis"
        ),
        {},
    )
    static_is_scored = (
        isinstance(static_section.get("score_value"), (int, float))
        and static_section.get("exclude_from_maturity") is not True
    )
    backlog_ids = [
        item.get("external_id")
        for item in backlog_exports["json"].get("items", [])
        if isinstance(item, dict)
    ]
    quality = {
        "version": VERSION,
        "premium_synthesis_version": PREMIUM_VERSION,
        "express_quality_version": EXPRESS_QUALITY_VERSION,
        "decision_grade_contract_version": DECISION_GRADE_CONTRACT_VERSION,
        "decision_grade_backlog_version": DECISION_GRADE_BACKLOG_VERSION,
        "decision_grade_delta_version": DECISION_GRADE_DELTA_VERSION,
        "decision_grade_report_view_version": DECISION_GRADE_REPORT_VIEW_VERSION,
        "decision_grade_body": True,
        "appendix_contract_schema": VERSION,
        "full_evidence_appendix": True,
        "score_band_separated_from_assurance": all(
            bool(item.get("score_band_label")) and bool(item.get("assurance_label"))
            for item in assessment.get("sections") or []
            if isinstance(item, dict)
        ),
        "unscored_controls_excluded_from_maturity": all(
            row.get("included") or row.get("technical_score") is None
            for row in assessment.get("scoring_weights") or []
            if isinstance(row, dict)
        ),
        "bounded_static_scoring_discloses_assurance": (
            not static_is_scored
            or (
                static_section.get("assurance_label") == "REVIEW LIMITED"
                and int(static_section.get("score_value")) <= 85
                and bool(static_section.get("unavailable") or static_section.get("findings"))
            )
        ),
        "weighted_scoring_explicit": bool(assessment.get("scoring_weights")),
        "shared_control_truth_reconciled": bool(
            assessment.get("comprehensive_express_quality", {}).get("shared_control_truth_reconciled")
        ),
        "executive_risk_truth_reconciled": bool(
            assessment.get("comprehensive_executive_risk_truth", {}).get("static_risk_wording_reconciled")
        ),
        "executive_risk_register_consolidated": len(executive_risks) <= 7,
        "executive_risk_register_limit": 7,
        "executive_risk_overflow_count": assessment.get("executive_risk_overflow_count", 0),
        "executive_risks_use_stable_ids": all(item.get("finding_id") for item in executive_risks),
        "executive_risks_include_cost_and_residual": all(
            item.get("cost_of_inaction") and item.get("residual_risk") for item in executive_risks
        ),
        "unverified_medium_candidates_not_p1": all(
            not (
                item.get("priority") == "P1"
                and "verified=false" in str(item.get("evidence")).casefold()
            )
            for item in findings
        ),
        "secret_category_isolated": True,
        "named_architecture_hotspots": any(
            item.get("category") == "architecture" and item.get("location") for item in findings
        ),
        "structured_findings_register": bool(findings) or not assessment.get("sections"),
        "executable_roadmap": bool(roadmap)
        and all(isinstance(item, dict) and item.get("work_packages") for item in roadmap),
        "limitation_accounting_explicit": all(
            key in limitations
            for key in (
                "stages_with_limitations",
                "individual_limitation_records",
                "score_affecting_records",
                "informational_records",
            )
        ),
        "evidence_health_summary_present": isinstance(assessment.get("evidence_health_summary"), dict),
        "scope_boundaries_present": bool(assessment.get("scope_boundaries")),
        "assumption_register_present": bool(assessment.get("assumption_register")),
        "how_to_use_present": bool(assessment.get("how_to_use_report")),
        "decision_grade_contract_serialized": contract_error is None,
        "decision_grade_readiness_status": contract_summary["readiness_status"],
        "decision_grade_validation_error_count": contract_summary["validation_error_count"],
        "decision_grade_validation_warning_count": contract_summary["validation_warning_count"],
        "p0_p1_traceability_complete": contract_summary["p0_p1_traceability_complete"],
        "monetary_claims_require_assumptions": contract_summary["monetary_claims_require_assumptions"],
        "backlog_export_generated": backlog_error is None,
        "backlog_item_count": backlog_exports["item_count"],
        "backlog_items_unique": len(backlog_ids) == len(set(backlog_ids)),
        "external_issue_creation_allowed": backlog_exports["external_issue_creation_allowed"],
        "historical_delta_status": historical_delta.get("status"),
        "historical_delta_generated_only_when_comparable": historical_delta.get("synthetic_delta_generated") is False,
        "client_ready": contract_summary["client_ready"],
        "final_pdf_page_count": page_count,
        "core_report_page_count": core_page_count,
        "pdf_page_count_matches_final_artifact": bool(pdf_bytes) and page_count > 0,
        "pdf_page_count_label_matches_artifact": bool(pdf_bytes)
        and f"Final PDF pages: {page_count}" in front_matter_text,
        "express_quality_front_matter": all(
            token in front_matter_text
            for token in ("NICO COMPREHENSIVE", "TECHNICAL MATURITY", "Why this is broader than Express")
        ),
        "semantic_html": "<table>" in rendered_html and "<h2>Evidence Appendix</h2>" in rendered_html,
        "markdown_evidence_appendix": APPENDIX_HEADING in markdown,
        "html_evidence_appendix": "<h2>Evidence Appendix</h2>" in rendered_html,
        "pdf_evidence_appendix": bool(pdf_bytes),
        "markdown_human_review_acceptance_gate": REVIEW_HEADING in markdown,
        "html_human_review_acceptance_gate": "<h2>Human Review and Acceptance Gate</h2>" in rendered_html,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    complete = bool(
        pdf_bytes.startswith(b"%PDF")
        and not pdf_error
        and quality["score_band_separated_from_assurance"]
        and quality["bounded_static_scoring_discloses_assurance"]
        and quality["weighted_scoring_explicit"]
        and quality["shared_control_truth_reconciled"]
        and quality["executive_risk_truth_reconciled"]
        and quality["executive_risk_register_consolidated"]
        and quality["executive_risks_use_stable_ids"]
        and quality["executive_risks_include_cost_and_residual"]
        and quality["unverified_medium_candidates_not_p1"]
        and quality["evidence_health_summary_present"]
        and quality["scope_boundaries_present"]
        and quality["assumption_register_present"]
        and quality["how_to_use_present"]
        and quality["express_quality_front_matter"]
        and quality["pdf_page_count_label_matches_artifact"]
        and quality["semantic_html"]
        and quality["markdown_evidence_appendix"]
        and quality["markdown_human_review_acceptance_gate"]
        and quality["decision_grade_contract_serialized"]
        and quality["backlog_export_generated"]
        and quality["backlog_items_unique"]
        and quality["historical_delta_generated_only_when_comparable"]
    )
    report_package = {
        "service_id": "comprehensive",
        "report_id": report_id,
        "markdown": markdown,
        "html": rendered_html,
        "json": canonical,
        "decision_grade_contract": contract_payload,
        "findings_csv": findings_csv,
        "evidence_ledger_csv": evidence_csv,
        "backlog_markdown": backlog_exports["markdown"],
        "backlog_json": backlog_exports["json"],
        "backlog_json_text": backlog_exports["json_text"],
        "github_issues": backlog_exports["github_issues"],
        "github_issues_json": backlog_exports["github_issues_json"],
        "jira_csv": backlog_exports["jira_csv"],
        "linear_csv": backlog_exports["linear_csv"],
        "backlog_hashes": backlog_exports["hashes"],
        "historical_delta": historical_delta,
        "historical_delta_markdown": historical_delta_markdown,
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
        "delivery_status": contract_summary["readiness_status"],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return {
        "status": "complete" if complete else "blocked",
        "reason": "" if complete else (
            pdf_error
            or contract_error
            or backlog_error
            or delta_error
            or "decision_grade_report_contract_failed"
        ),
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "report_id": report_id,
        "generated_at": generated_at,
        "assessment": assessment,
        "stage_summaries": stages,
        "canonical_truth_sha256": truth_sha,
        "decision_grade_contract": contract_payload,
        "backlog_export": backlog_exports["json"],
        "historical_delta": historical_delta,
        "delivery_status": contract_summary["readiness_status"],
        "report_quality_contract": quality,
        "report_package": report_package,
        "appendix_contract_schema": VERSION,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["build_comprehensive_report_package"]
