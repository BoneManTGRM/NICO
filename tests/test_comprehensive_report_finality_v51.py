from __future__ import annotations

import base64

from nico.comprehensive_report_scanner_detection_v51 import (
    _extract_report_language,
    _scanner_truth,
)
from nico.comprehensive_report_scanner_scoring_v51 import _normalize_assessment
from nico.comprehensive_report_spanish_artifacts_v51 import (
    _localize_package,
    _spanish_html,
    _spanish_pdf,
)
from nico.comprehensive_report_spanish_text_v51 import _spanish_markdown


def _stages() -> dict:
    return {
        "authorization_and_scope": {"evidence": {"report_language": "es-MX"}},
        "deep_scanner_triage": {
            "tools_run": [
                "pip-audit",
                "npm-audit",
                "osv-scanner",
                "semgrep",
                "typescript",
                "trufflehog",
            ],
            "failed_tools": ["bandit"],
            "unavailable_tools": ["gitleaks"],
            "evidence": [
                "Completed static tools: semgrep, typescript",
                "Dedicated secret tools completed: trufflehog",
                "verified_material=0",
            ],
            "findings": [
                "OSV dependency scan did not produce a complete result",
                "bandit evidence unavailable",
                "No ESLint configuration exists; ESLint is not applicable",
            ],
        },
    }


def _assessment() -> dict:
    return {
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 92, "score_value": 92, "evidence": ["retained"]},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 92, "score_value": 92, "evidence": ["retained"], "findings": ["candidate"]},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 85, "score_value": 85, "evidence": ["retained"], "findings": ["candidate"]},
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": None,
                "score_value": None,
                "exclude_from_maturity": True,
                "evidence": ["Completed static tools: semgrep, typescript", "verified_material=0"],
                "findings": ["285 candidates require human triage"],
            },
            {"id": "ci_cd", "label": "CI/CD Analysis", "score": 86, "score_value": 86, "evidence": ["retained"]},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 78, "score_value": 78, "evidence": ["retained"]},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 84, "score_value": 84, "evidence": ["retained"]},
        ],
        "maturity_signal": {},
        "scope_boundaries": [],
    }


def _canonical(assessment: dict) -> dict:
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "run_id": "comprun_test",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_test",
        },
        "assessment": assessment,
        "findings_register": [],
        "stage_summaries": [],
        "roadmap": [],
        "staffing_plan": [],
    }


def test_scanner_truth_retains_current_run_completion_and_limitations() -> None:
    stages = _stages()
    truth = _scanner_truth(stages)

    assert _extract_report_language({}, stages) == "es-MX"
    assert truth["semgrep"]["status"] == "complete"
    assert truth["typescript"]["status"] == "complete"
    assert truth["trufflehog"]["status"] == "complete"
    assert truth["bandit"]["status"] == "failed"
    assert truth["osv-scanner"]["status"] == "partial"
    assert truth["gitleaks"]["status"] == "partial"
    assert truth["eslint"]["status"] == "not_applicable"
    assert truth["eslint"]["required"] is False


def test_assessment_completion_is_separate_from_assurance_and_static_is_scored() -> None:
    normalized = _normalize_assessment(_assessment(), _scanner_truth(_stages()))
    sections = {item["id"]: item for item in normalized["sections"]}

    assert sections["code_audit"]["execution_status"] == "complete"
    assert sections["code_audit"]["assurance_label"] == "VERIFIED"
    assert sections["dependency_health"]["assurance_label"] == "REVIEW LIMITED"
    assert sections["secrets_review"]["assurance_label"] == "REVIEW LIMITED"
    assert sections["static_analysis"]["score_value"] == 82
    assert sections["static_analysis"]["exclude_from_maturity"] is False
    assert sections["static_analysis"]["assurance_label"] == "REVIEW LIMITED"
    assert normalized["technical_score"] == 86
    assert normalized["evidence_adjusted_score"] == 84
    assert normalized["canonical_evidence_adjusted_score"] == 84
    assert normalized["assessment_completion"]["assessment_execution"] == "complete"
    assert normalized["assessment_completion"]["scanner_execution"] == "partial"
    assert normalized["completion_status"] == "complete_with_disclosed_evidence_limitations"
    assert normalized["evidence_health_summary"]["structured_execution_records_present"] is True


def test_spanish_client_artifacts_are_generated_from_the_same_truth() -> None:
    canonical = _canonical(_normalize_assessment(_assessment(), _scanner_truth(_stages())))
    markdown = _spanish_markdown(canonical)
    rendered_html = _spanish_html(markdown, "Evaluación Técnica Integral NICO")
    pdf, page_count = _spanish_pdf(canonical)

    assert markdown.startswith("# Evaluación Técnica Integral NICO")
    assert "## Cuadro de puntuación técnica" in markdown
    assert "ENTREGA AL CLIENTE BLOQUEADA" in markdown
    assert "CLIENT DELIVERY BLOCKED · PENDING HUMAN APPROVAL" in markdown
    assert "<html lang='es-MX'>" in rendered_html
    assert pdf.startswith(b"%PDF")
    assert page_count >= 1

    result = {
        "report_package": {
            "json": canonical,
            "report_quality_contract": {},
        }
    }
    localized = _localize_package(result)
    package = localized["report_package"]
    assert localized["report_language"] == "es-MX"
    assert package["report_language"] == "es-MX"
    assert package["pdf_filename"].endswith("-es-MX-BORRADOR.pdf")
    assert base64.b64decode(package["pdf_base64"]).startswith(b"%PDF")
    assert package["report_quality_contract"]["spanish_markdown_complete"] is True
    assert package["report_quality_contract"]["structured_scanner_completion_records_present"] is True
