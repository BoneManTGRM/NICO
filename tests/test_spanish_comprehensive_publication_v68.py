from __future__ import annotations

import base64
import io
import re
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
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code Audit",
                    "score": 93,
                    "presented_score": 93,
                    "status": "green",
                    "presented_status": "green",
                    "summary": "Exact-commit sampled code signals and repository structure were reviewed.",
                    "evidence": ["Risk pattern hits: 0."],
                    "findings": [],
                    "unavailable": [],
                },
                {
                    "id": "architecture_debt",
                    "label": "Architecture & Technical Debt",
                    "score": 72,
                    "presented_score": 72,
                    "status": "yellow",
                    "presented_status": "yellow",
                    "summary": "Snapshot-bound source footprint and measured complexity evidence were evaluated.",
                    "evidence": ["Complexity risk: observed."],
                    "findings": [],
                    "unavailable": [],
                },
            ],
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
    assert '<html lang="es-MX">' in rendered_html
    assert "Registro de hallazgos y remediación" in pdf_text
    assert "RISK-P1-ES-001" in pdf_text
    assert "B501" in pdf_text
    for visible in (markdown, rendered_html, pdf_text):
        for forbidden in (
            "Run Bandit against",
            "Run Bandit contra",
            "B501 is absent",
            "It is intentionally separate",
            "Exact-source code findings",
            "Problematic code or signature",
            "Specific correction",
            "Owner / effort",
        ):
            assert forbidden not in visible
    assert "Ejecutar Bandit contra la misma revisión inmutable." in markdown
    assert "B501 no aparece en la salida del analizador para el SHA exacto." in markdown
    assert " · DRAFT" not in pdf_text
    assert re.search(r"\bPage\s+\d+\b", pdf_text) is None
    for visible in (markdown, rendered_html, pdf_text):
        assert "GREEN" not in visible
        assert "YELLOW" not in visible
        assert "VERDE" in visible
        assert "AMARILLO" in visible
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


def test_semantic_gate_accepts_current_compact_spanish_register_heading() -> None:
    canonical = _canonical()
    markdown = "\n".join(
        [
            "# Evaluación Técnica Integral NICO",
            "## Registro compacto de hallazgos y remediación",
            "RISK-P1-ES-001 · src/client.py:17",
            "## Registro de candidatos que requieren revisión",
            "Candidatos que requieren revisión: 3",
            "Hallazgos materiales confirmados: 1",
            "Efecto en puntuación: solo aseguramiento mientras la disposición humana siga pendiente; el triaje técnico de NICO está completo.",
            "## Preparación operativa y salud histórica de CI/CD",
        ]
    )
    package = {
        "report_language": "es-MX",
        "json": canonical,
        "markdown": markdown,
        "html": f"<html lang='es-MX'><body>{markdown}</body></html>",
    }

    validation = validate_retained_decision_content(package)

    assert validation["authoritative_finding_register_present"] is True
    assert validation["finding_register_marker"] == "registro compacto de hallazgos y remediación"
    assert validation["review_candidate_truth_present"] is True
    assert validation["ci_operational_context_rendered"] is True


def test_dynamic_spanish_localization_is_mounted_and_keeps_technical_code_untouched() -> None:
    page = (ROOT / "apps/web/app/assessment/AssessmentPage.tsx").read_text()
    localization = (
        ROOT / "apps/web/app/assessment/AssessmentDynamicSpanishLocalization.tsx"
    ).read_text()

    assert 'import AssessmentDynamicSpanishLocalization from "./AssessmentDynamicSpanishLocalization";' in page
    assert "<AssessmentDynamicSpanishLocalization />" in page
    assert '["comprehensive run", "Ejecución integral"]' in localization
    assert '["final comprehensive report generation", "Generación del informe final de evaluación"]' in localization
    assert '["blocked", "Bloqueado"]' in localization
    assert "new MutationObserver" in localization
    assert "characterData: true" in localization
    assert "childList: true" in localization
    assert "subtree: true" in localization
    assert "script, style, code, pre, textarea, [data-no-localize='true']" in localization


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
