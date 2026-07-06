import base64

import pytest

from nico.assessment_quality import polish_express_result


def test_metadata_limited_sections_are_degraded_not_red():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/autonomous-betting-assistant",
        "generated_at": "2026-07-06T00:00:00Z",
        "client_name": "ABA Signal Pro",
        "project_name": "ABA Signal Pro",
        "executive_summary": "Assessment complete.",
        "maturity_signal": {"level": "Mid", "score": 62},
        "maturity_semaphore": {"dependency": "red", "ci_cd": "degraded"},
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "quick_wins": ["Review dependency pins."],
        "medium_term_plan": ["Improve CI metadata access."],
        "resourcing_recommendation": ["Human review required."],
        "risk_register": ["Metadata unavailable."],
        "verification_checklist": ["Rerun with authenticated GitHub metadata."],
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 36,
                "status": "red",
                "summary": "Code audit uses metadata and source review.",
                "evidence": ["No recent pull-request evidence was found; direct-to-main work may reduce review traceability."],
                "findings": ["No recent pull-request evidence was found; direct-to-main work may reduce review traceability."],
                "unavailable": ["Commit activity unavailable: GitHub returned 403: API rate limit exceeded"],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 20,
                "status": "red",
                "summary": "CI/CD maturity is based on workflow evidence.",
                "evidence": ["No GitHub Actions workflow files were available for analysis."],
                "findings": ["No CI/CD workflow files were found through GitHub contents access."],
                "unavailable": ["Workflow run history unavailable: GitHub returned 403: API rate limit exceeded"],
            },
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 76,
                "status": "green",
                "summary": "Repository layout supports architecture review.",
                "evidence": ["Repository root contains .github/."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 51,
                "status": "yellow",
                "summary": "Velocity is estimated from metadata.",
                "evidence": ["Commit velocity: 0 commits over 180 days (0.0/week).", "Pull request traceability ratio: 0 PRs / 0 commits = 0."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 30,
                "status": "red",
                "summary": "Dependency manifests were inspected.",
                "evidence": ["OSV returned 2 records for streamlit.", "OSV returned 2 records for streamlit."],
                "findings": ["OSV returned 2 records for streamlit.", "OSV returned 2 records for streamlit."],
                "unavailable": [],
            },
        ],
    }

    polished = polish_express_result(result)
    code = next(item for item in polished["sections"] if item["id"] == "code_audit")
    ci = next(item for item in polished["sections"] if item["id"] == "ci_cd")
    velocity = next(item for item in polished["sections"] if item["id"] == "velocity_complexity")
    deps = next(item for item in polished["sections"] if item["id"] == "dependency_health")

    assert polished["assessment_quality"] == "degraded_metadata"
    assert code["status"] == "yellow"
    assert code["score"] >= 55
    assert not any("No recent pull-request evidence" in note for note in code["findings"])
    assert ci["status"] == "yellow"
    assert ci["score"] >= 50
    assert not any("No CI/CD workflow files" in note for note in ci["findings"])
    assert velocity["score"] >= 55
    assert not any("0 commits over" in note for note in velocity["evidence"])
    assert deps["evidence"].count("OSV returned 2 records for streamlit.") == 1


def test_polished_pdf_is_generated_for_complete_assessment():
    pytest.importorskip("reportlab")
    result = {
        "status": "complete",
        "repository": "owner/repo",
        "generated_at": "2026-07-06T00:00:00Z",
        "client_name": "Client",
        "project_name": "Project",
        "executive_summary": "Evidence-bound assessment summary.",
        "maturity_signal": {"level": "Mid", "score": 67},
        "maturity_semaphore": {"code": "yellow"},
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 67, "status": "yellow", "summary": "Useful evidence.", "evidence": ["Evidence item."], "findings": ["Finding item."], "unavailable": ["Unavailable item."]}
        ],
        "quick_wins": ["Quick win."],
        "medium_term_plan": ["Medium plan."],
        "resourcing_recommendation": ["Review."],
        "risk_register": ["Risk."],
        "verification_checklist": ["Verify."],
        "reports": {"pdf_base64": "old"},
    }
    polished = polish_express_result(result)
    pdf_base64 = polished["reports"]["pdf_base64"]
    assert polished["reports"]["pdf_style"] == "client_ready_polished"
    assert polished["reports"]["pdf_filename"] == "nico-express-owner-repo.pdf"
    assert base64.b64decode(pdf_base64).startswith(b"%PDF")
    assert len(base64.b64decode(pdf_base64)) > 2500
