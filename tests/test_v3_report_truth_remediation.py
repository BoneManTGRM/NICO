from __future__ import annotations

import base64
import io

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.v3_report_truth_remediation import finalize_report_v3, repair_report_truth_v3


SHA = "a" * 40


def _sections() -> list[dict]:
    return [
        {"id": "code_audit", "label": "Code Audit", "score": 78, "presented_score": 78},
        {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 31, "presented_score": 31},
        {
            "id": "secrets_review",
            "label": "Secrets Exposure Review",
            "score": 72,
            "presented_score": 72,
            "presented_status": "REVIEW_LIMITED",
            "evidence": ["gitleaks: status=missing; exact_commit_match=True"],
            "unavailable": ["gitleaks exact-SHA evidence remains missing"],
        },
        {
            "id": "static_analysis",
            "label": "Static Analysis",
            "score": 83,
            "presented_score": 83,
            "presented_status": "REVIEW_LIMITED_NOT_SCORED",
            "evidence": [
                "bandit: status=failed; exact_commit_match=True",
                "eslint: status=missing; exact_commit_match=True",
            ],
            "unavailable": ["bandit exact-SHA evidence remains failed"],
        },
        {"id": "ci_cd", "label": "CI/CD Analysis", "score": 74, "presented_score": 74},
        {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 78, "presented_score": 78},
        {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 84, "presented_score": 84},
    ]


def _package() -> dict:
    return {
        "json": {
            "identity": {"repository": "BoneManTGRM/NICO", "commit_sha": SHA, "run_id": "comprun_v3"},
            "assessment": {
                "technical_score": 68,
                "canonical_evidence_adjusted_score": 68,
                "evidence_adjusted_score": 68,
                "maturity_signal": {"score": 68, "level": "Weak"},
                "sections": _sections(),
            },
            "scanner_execution_records": [
                {
                    "scanner_name": "bandit",
                    "commit_sha": SHA,
                    "state": "completed",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "b" * 64,
                    "output_capture_complete": True,
                    "category": "static",
                    "findings": [],
                },
                {
                    "scanner_name": "eslint",
                    "commit_sha": SHA,
                    "state": "completed_with_findings",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "c" * 64,
                    "output_capture_complete": True,
                    "category": "static",
                    "findings": [{"rule_id": "complexity"}],
                },
                {
                    "scanner_name": "semgrep",
                    "commit_sha": SHA,
                    "state": "completed",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "d" * 64,
                    "output_capture_complete": True,
                    "category": "static",
                    "findings": [],
                },
                {
                    "scanner_name": "typescript",
                    "commit_sha": SHA,
                    "state": "completed",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "e" * 64,
                    "output_capture_complete": True,
                    "category": "static",
                    "findings": [],
                },
                {
                    "scanner_name": "gitleaks",
                    "commit_sha": SHA,
                    "state": "completed",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "f" * 64,
                    "output_capture_complete": True,
                    "full_history_verified": True,
                    "scans_git_history": True,
                    "category": "secret",
                    "findings": [],
                },
                {
                    "scanner_name": "trufflehog",
                    "commit_sha": SHA,
                    "state": "completed",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "1" * 64,
                    "output_capture_complete": True,
                    "full_history_verified": True,
                    "scans_git_history": True,
                    "category": "secret",
                    "findings": [],
                },
            ],
            "canonical_findings": [
                {
                    "finding_id": "RISK-LEGACY-1",
                    "priority": "P1",
                    "category": "architecture",
                    "title": "High-complexity code hotspot",
                    "location": "apps/web/app/operations/page.tsx:177",
                    "acceptance_criteria": ["Complexity is <= 30. [method: metric_comparison; target commit: " + SHA + "]"],
                },
                {
                    "finding_id": "RISK-P1-CANONICAL",
                    "priority": "P1",
                    "category": "architecture",
                    "title": "High-complexity code hotspot",
                    "location": "apps/web/app/operations/page.tsx:177",
                    "business_impact": "Concentrated branch logic increases regression risk.",
                    "recommendation": "Split the component.",
                    "acceptance_criteria": [
                        "Complexity is <= 30. [method: metric_comparison; target commit: " + SHA + "]",
                        "Complexity is <= 30. [method: exact_sha_rerun; target commit: " + SHA + "]",
                    ],
                },
                {
                    "finding_id": "RISK-P1-TEST",
                    "priority": "P1",
                    "category": "code",
                    "title": "python_eval_exec — Dynamic code execution should be reviewed",
                    "location": "tests/test_express_safe_trace_diagnostics.py:12",
                },
                {
                    "finding_id": "RISK-P1-RULE",
                    "priority": "P1",
                    "category": "code",
                    "title": "TLS certificate verification disabled",
                    "location": "nico/scanner_evidence_pipeline_v1.py:478",
                },
            ],
            "stage_summaries": [
                {
                    "stage_id": "deep_scanner_triage",
                    "status": "complete",
                    "evidence": [],
                    "unavailable": [
                        "Full Git history and object store were materialized and verified for Gitleaks and TruffleHog."
                    ],
                },
                {
                    "stage_id": "decision_report_generation",
                    "status": "complete",
                    "report_contract_reason": "canonical_score_truth_mismatch",
                    "report_contract_status": "blocked",
                    "evidence": [
                        "technical_score: 68",
                        "evidence_adjusted_score: 70",
                    ],
                },
                {
                    "stage_id": "evidence_reconciliation_and_scoring",
                    "status": "complete",
                    "evidence": [
                        "technical_score: 68",
                        "canonical_evidence_adjusted_score: 70",
                        "technical_band: WEAK",
                    ],
                },
            ],
            "roadmap": [
                {
                    "window": "31-90 days",
                    "work_packages": [
                        {
                            "work_package_id": "WP-1",
                            "related_risks": [
                                "RISK-LEGACY-1",
                                "RISK-P1-CANONICAL",
                                "RISK-P1-CANONICAL",
                            ],
                            "acceptance_criteria": [
                                "Complexity is <= 30. [method: metric_comparison; target commit: " + SHA + "]",
                                "Complexity is <= 30. [method: exact_sha_rerun; target commit: " + SHA + "]",
                            ],
                            "expected_impact": "Reduces delivery uncertainty. Reduces delivery uncertainty.",
                            "residual_risk": "Future regressions remain possible.\ufffe Future regressions remain possible.",
                        }
                    ],
                }
            ],
        }
    }


def test_v3_truth_deduplicates_findings_and_preserves_non_production_observations() -> None:
    repaired = repair_report_truth_v3(_package())
    canonical = repaired["json"]

    assert len(canonical["canonical_findings"]) == 1
    finding = canonical["canonical_findings"][0]
    assert finding["finding_id"] == "RISK-P1-CANONICAL"
    assert finding["title"] == "Reduce complexity in operations/page.tsx"
    assert finding["acceptance_criteria"] == ["Complexity is <= 30."]
    assert set(finding["finding_aliases"]) >= {"RISK-LEGACY-1", "RISK-P1-CANONICAL"}
    assert len(canonical["non_production_observations"]) == 2
    assert all(item["technical_score_impact"] == "none" for item in canonical["non_production_observations"])


def test_v3_truth_synchronizes_scores_scanners_stages_and_roadmap() -> None:
    canonical = repair_report_truth_v3(_package())["json"]
    assessment = canonical["assessment"]

    assert assessment["technical_score"] == 70
    assert assessment["canonical_evidence_adjusted_score"] == 68
    assert assessment["technical_band"] == "MODERATE"
    assert assessment["comprehensive_score_truth"]["technical_score"] == 70
    assert assessment["comprehensive_score_truth"]["canonical_evidence_adjusted_score"] == 68

    static = next(item for item in assessment["sections"] if item["id"] == "static_analysis")
    secrets = next(item for item in assessment["sections"] if item["id"] == "secrets_review")
    assert static["assurance_label"] == "VERIFIED"
    assert static["presented_status"] == "MODERATE"
    assert "status=failed" not in " ".join(static["evidence"])
    assert secrets["assurance_label"] == "VERIFIED"
    assert secrets["unavailable"] == []

    deep = next(item for item in canonical["stage_summaries"] if item["stage_id"] == "deep_scanner_triage")
    decision = next(item for item in canonical["stage_summaries"] if item["stage_id"] == "decision_report_generation")
    scoring = next(item for item in canonical["stage_summaries"] if item["stage_id"] == "evidence_reconciliation_and_scoring")
    assert deep["unavailable"] == []
    assert "Full Git history" in deep["evidence"][0]
    assert decision["report_contract_status"] == "passed"
    assert decision["report_contract_reason"] == "canonical_score_truth_synchronized"
    assert "technical_score: 70" in decision["evidence"]
    assert "evidence_adjusted_score: 68" in decision["evidence"]
    assert "technical_score: 70" in scoring["evidence"]
    assert "canonical_evidence_adjusted_score: 68" in scoring["evidence"]
    assert "technical_band: MODERATE" in scoring["evidence"]

    work = canonical["roadmap"][0]["work_packages"][0]
    assert work["related_risks"] == ["RISK-P1-CANONICAL"]
    assert work["acceptance_criteria"] == ["Complexity is <= 30."]
    assert work["expected_impact"] == "Reduces delivery uncertainty."
    assert work["residual_risk"] == "Future regressions remain possible."


def test_v3_finalization_deduplicates_filename_and_rejects_no_truth() -> None:
    package = repair_report_truth_v3(_package())
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(72, 720, "FINAL REPORT · PENDING HUMAN APPROVAL")
    pdf.drawString(72, 700, "comprun_v3")
    pdf.drawString(72, 680, SHA)
    pdf.showPage()
    pdf.save()
    package.update(
        {
            "pdf_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "pdf_filename": "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
            "markdown": "FINAL REPORT\n",
            "html": "<html><body>FINAL REPORT</body></html>",
        }
    )

    final = finalize_report_v3(package)
    assert final["pdf_filename"] == "nico-report-FINAL-PENDING-APPROVAL.pdf"
    assert final["premium_report_renderer"]["semantic_duplicate_validation"] is True
    assert final["premium_report_renderer"]["forbidden_noncharacter_validation"] is True
