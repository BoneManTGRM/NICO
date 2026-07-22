import io

from pypdf import PdfReader

from nico.comprehensive_express_quality_v7 import (
    comprehensive_pdf_with_final_count,
    reconcile_comprehensive_assessment,
)


def _accepted_assessment():
    return {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 78, "presented_score": 78},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 86, "presented_score": 86, "score_value": 86, "assurance_status": "verified", "assurance_label": "VERIFIED", "findings": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 86, "presented_score": 86, "score_value": 86, "assurance_status": "review_limited", "assurance_label": "REVIEW LIMITED", "findings": ["Two npm-audit candidates require human triage."]},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 88, "presented_score": 88, "score_value": 88, "assurance_status": "review_limited", "assurance_label": "REVIEW LIMITED", "findings": ["One TruffleHog candidate requires human triage."]},
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 28,
                "presented_score": 28,
                "score_value": 28,
                "assurance_status": "blocked",
                "assurance_label": "BLOCKED",
                "evidence": [
                    "Exact-snapshot semgrep status=completed; findings=8.",
                    "Exact-snapshot typescript status=completed; findings=0.",
                    "Bandit triage artifact attached: blocking=0, needs_review=4, approved=0, candidate_false_positive=3.",
                ],
                "findings": ["Failed static analyzers: bandit.", "4 candidate(s) require human triage."],
                "unavailable": ["bandit ended with status failed."],
            },
            {"id": "ci_cd", "label": "CI/CD Analysis", "score": 92, "presented_score": 92, "score_value": 92, "assurance_status": "verified", "assurance_label": "VERIFIED", "findings": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 87, "presented_score": 87, "score_value": 87, "assurance_status": "verified", "assurance_label": "VERIFIED", "findings": []},
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 73,
                "presented_score": 73,
                "score_value": 73,
                "assurance_status": "review_limited",
                "assurance_label": "REVIEW LIMITED",
                "evidence": [
                    "Commit cadence: 100 commits over 26 weeks (3.85 / week).",
                    "Pull request traceability ratio: 88 merged / 88 mapped = 1.0.",
                    "Complexity engine current-run artifact completed for the immutable snapshot.",
                ],
                "findings": [],
                "unavailable": ["Longitudinal trend history remains unavailable."],
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": None,
                "presented_score": None,
                "score_value": None,
                "assurance_status": "supplemental",
                "assurance_label": "SUPPLEMENTAL",
                "evidence": [
                    "Scanner-worker dependency tools completed: pip-audit, npm-audit, osv-scanner.",
                    "Exact-snapshot trufflehog status=completed; findings=1.",
                    "Exact-snapshot semgrep status=completed; findings=8.",
                    "Exact-snapshot typescript status=completed; findings=0.",
                ],
                "findings": ["gitleaks ended with status timeout.", "bandit ended with status failed."],
            },
        ],
        "findings_register": [],
    }


def test_comprehensive_reuses_shared_truth_and_handles_sentence_punctuation():
    result = reconcile_comprehensive_assessment(_accepted_assessment())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")
    scanner = next(item for item in result["sections"] if item["id"] == "scanner_worker_evidence")

    assert static["score_value"] == 82
    assert static["assurance_label"] == "REVIEW LIMITED"
    assert velocity["score_value"] >= 85
    assert scanner["score_kind"] == "execution_coverage"
    assert scanner["exclude_from_maturity"] is True
    assert result["technical_score"] >= 85
    assert result["comprehensive_express_quality"]["shared_control_truth_reconciled"] is True


def test_comprehensive_pdf_has_express_quality_front_matter_and_exact_page_count():
    identity = {
        "run_id": "comprun_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "evidence_ledger_id": "ledger_test",
        "customer_id": "customer_test",
        "project_id": "project_test",
    }
    assessment = {
        "technical_score": 87,
        "evidence_adjusted_score": 85,
        "maturity_signal": {"score": 87, "presented_score": 87, "score_band_label": "STRONG"},
        "executive_summary": "NICO completed an authorized Comprehensive Technical Assessment with deeper evidence, execution planning, and an immutable delivery gate.",
        "sections": [],
        "scoring_weights": [],
        "findings_register": [],
        "executive_risk_register": [
            {"title": "Consolidate the runtime compatibility surface"},
            {"title": "Classify historical CI failures"},
            {"title": "Complete exact-snapshot analyzer acceptance"},
        ],
    }
    stages = [
        {
            "title": "Repository analysis",
            "stage_id": "repository",
            "status": "complete",
            "summary": "Repository evidence retained.",
            "evidence": ["Immutable snapshot verified."],
            "findings": [],
            "unavailable": [],
        }
    ]
    limitations = {
        "stages_with_limitations": 1,
        "individual_limitation_records": 2,
        "score_affecting_records": 1,
        "informational_records": 1,
    }

    pdf_bytes, page_count = comprehensive_pdf_with_final_count(
        identity,
        assessment,
        stages,
        [],
        [],
        limitations,
        "2026-07-22T20:00:00Z",
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    front_text = " ".join((reader.pages[index].extract_text() or "") for index in range(2))

    assert len(reader.pages) == page_count
    assert page_count >= 25
    assert "NICO COMPREHENSIVE" in front_text
    assert "TECHNICAL MATURITY" in front_text
    assert "Why this is broader than Express" in front_text
    assert f"Final PDF pages: {page_count}" in front_text
