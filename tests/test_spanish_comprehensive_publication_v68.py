from __future__ import annotations

import base64
import io
from copy import deepcopy
from pathlib import Path

from pypdf import PdfReader

from nico.comprehensive_report_semantic_content_gate_v66 import (
    validate_retained_decision_content,
)
from nico.comprehensive_spanish_authoritative_publication_v68 import (
    finalize_spanish_authoritative_package,
)

ROOT = Path(__file__).resolve().parents[1]


def _canonical() -> dict:
    finding = {
        "finding_id": "RISK-P1-ES-001",
        "priority": "P1",
        "category": "security",
        "status": "open",
        "title": "TLS verification disabled",
        "location": "src/client.py:17",
        "path": "src/client.py",
        "line": 17,
        "symbol": "fetch_remote",
        "rule_id": "B501",
        "finding_family": "tls_verify_disabled",
        "evidence_source": "Bandit",
        "evidence_quality": "verified",
        "exact_commit_match": True,
        "problematic_code": "requests.get(url, verify=False)",
        "source_excerpt": "response = requests.get(url, verify=False)",
        "observed_evidence": "Bandit B501 retained at the exact source location.",
        "interpretation": "The client disables certificate verification.",
        "business_impact": "A network attacker could intercept trusted traffic.",
        "recommended_correction": "Remove verify=False and use the approved trust store.",
        "owner_role": "Platform Engineer",
        "effort": "1-2 days",
        "verification": ["Run Bandit against the same immutable revision."],
        "rollback": "Restore the prior client configuration if compatibility fails.",
        "exit_criteria": ["B501 is absent from the exact-SHA scanner output."],
        "production_scope": True,
        "client_actionable": True,
        "record_source": "canonical_finding",
    }
    register = {
        "version": "test-register",
        "exact_commit_sha": "abc123def456",
        "code_findings": [deepcopy(finding)],
        "operational_findings": [],
        "excluded_non_production_findings": [],
        "summary": {
            "raw_observation_count": 4,
            "normalized_candidate_count": 3,
            "decision_finding_count": 1,
            "canonical_finding_count": 1,
            "finding_register_count": 1,
            "exact_source_code_finding_count": 1,
            "operational_or_context_finding_count": 0,
            "human_disposition_required": True,
            "client_delivery_allowed": False,
        },
    }
    canonical_finding = {
        "finding_id": finding["finding_id"],
        "priority": finding["priority"],
        "category": finding["category"],
        "status": finding["status"],
        "title": finding["title"],
        "location": finding["location"],
        "path": finding["path"],
        "line": finding["line"],
        "symbol": finding["symbol"],
        "rule_id": finding["rule_id"],
        "finding_family": finding["finding_family"],
        "fact": finding["observed_evidence"],
        "interpretation": finding["interpretation"],
        "business_impact": finding["business_impact"],
        "recommendation": finding["recommended_correction"],
        "acceptance_criteria": deepcopy(finding["verification"]),
        "exit_criteria": deepcopy(finding["exit_criteria"]),
        "owner_role": finding["owner_role"],
        "effort": finding["effort"],
        "evidence_quality": finding["evidence_quality"],
        "exact_commit_match": True,
        "production_scope": True,
        "human_disposition_required": True,
    }
    return {
        "report_language": "es-MX",
        "locale": "es-MX",
        "identity": {
            "repository": "owner/repository",
            "run_id": "comprun_spanish_test",
            "commit_sha": "abc123def456",
            "evidence_ledger_id": "ledger-es-1",
            "report_language": "es-MX",
            "locale": "es-MX",
        },
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 93,
            "executive_summary": "La evaluación técnica terminó con revisión humana pendiente.",
            "sections": [],
            "scanner_execution_records": [
                {
                    "scanner_name": "Bandit",
                    "status": "complete",
                    "required": True,
                    "score_controls_affected": ["security"],
                }
            ],
            "review_candidate_summary": {
                "review_required_total": 3,
                "verified_material_total": 1,
            },
            "ci_operational_context": {
                "successful_workflow_runs": 83,
                "non_successful_workflow_runs": 12,
                "observed_job_success_rate": 1.0,
            },
            "scope_boundaries": [],
            "report_language": "es-MX",
            "locale": "es-MX",
        },
        "canonical_findings": [canonical_finding],
        "findings_register": [deepcopy(canonical_finding)],
        "client_finding_remediation_register": register,
        "review_candidate_summary": {
            "review_required_total": 3,
            "verified_material_total": 1,
        },
        "ci_operational_context": {
            "successful_workflow_runs": 83,
            "non_successful_workflow_runs": 12,
            "observed_job_success_rate": 1.0,
        },
        "stage_summaries": [],
        "roadmap": [],
        "staffing_plan": [],
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_spanish_authoritative_register_is_complete_in_all_client_formats() -> None:
    canonical = _canonical()
    scanner_records = deepcopy(canonical["assessment"]["scanner_execution_records"])
    result = finalize_spanish_authoritative_package(
        {
            "report_language": "es-MX",
            "locale": "es-MX",
            "delivery_status": "blocked_pending_human_approval",
            "client_delivery_allowed": False,
            "report_package": {
                "json": canonical,
                "delivery_status": "blocked_pending_human_approval",
                "client_delivery_allowed": False,
                "report_quality_contract": {},
            },
        }
    )
    package = result["report_package"]
    published = package["json"]
    markdown = package["markdown"]
    rendered_html = package["html"]
    pdf = base64.b64decode(package["pdf_base64"])
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert result["report_language"] == "es-MX"
    assert package["report_language"] == "es-MX"
    assert published["report_language"] == "es-MX"
    assert published["identity"]["report_language"] == "es-MX"
    assert published["assessment"]["report_language"] == "es-MX"
    assert "## Registro de hallazgos y remediación" in markdown
    assert "## Registro detallado de hallazgos" not in markdown
    assert "RISK-P1-ES-001" in markdown
    assert "src/client.py:17" in markdown
    assert "Bandit" in markdown
    assert "B501" in markdown
    assert "Registro de hallazgos y remediación" in rendered_html
    assert "lang='es-MX'" in rendered_html
    assert "Registro de hallazgos y remediación" in pdf_text
    assert "RISK-P1-ES-001" in pdf_text
    assert "B501" in pdf_text
    assert package["markdown_filename"].endswith("-es-MX-BORRADOR.md")
    assert package["html_filename"].endswith("-es-MX-BORRADOR.html")
    assert package["pdf_filename"].endswith("-es-MX-BORRADOR.pdf")
    assert published["assessment"]["technical_score"] == 93
    assert published["assessment"]["canonical_evidence_adjusted_score"] == 93
    assert published["assessment"]["scanner_execution_records"] == scanner_records
    assert published["review_candidate_summary"]["review_required_total"] == 3
    assert published["review_candidate_summary"]["verified_material_total"] == 1
    assert package["delivery_status"] == "blocked_pending_human_approval"
    assert package["client_delivery_allowed"] is False
    assert validate_retained_decision_content(package)[
        "authoritative_finding_register_present"
    ] is True


def test_mobile_fixed_panels_are_localized_non_destructive_and_non_overlapping() -> None:
    current_panel = (ROOT / "apps/web/app/AssessmentActiveRunReset.tsx").read_text()
    recovery_panel = (ROOT / "apps/web/app/ComprehensiveStuckRunRecovery.tsx").read_text()
    overlay_css = (ROOT / "apps/web/styles/assessment-recovery-overlay.css").read_text()
    layout = (ROOT / "apps/web/app/layout.tsx").read_text()

    for text in (
        "Evaluación actual",
        "Mostrar",
        "Ocultar",
        "Ejecución",
        "Borrar la ejecución actual e iniciar una evaluación nueva",
    ):
        assert text in current_panel
    for text in (
        "Recuperación de evaluación disponible",
        "Reintentar la ejecución exacta",
        "Borrar la ejecución atascada e iniciar una nueva",
        "Seguir esperando",
    ):
        assert text in recovery_panel
    assert 'path === "/es"' in current_panel
    assert 'path === "/es-mx"' in current_panel
    assert "window.confirm(copy.confirmClear)" in current_panel
    assert "window.confirm(copy.confirmClear)" in recovery_panel
    assert "data-comprehensive-stuck-run-recovery-visible" in current_panel
    assert "data-comprehensive-stuck-run-recovery-visible" in recovery_panel
    assert "--nico-stuck-run-recovery-clearance" in recovery_panel
    assert "padding-bottom" in overlay_css
    assert '[data-assessment-active-run-reset="true"]' in overlay_css
    assert "assessment-recovery-overlay.css" in layout
