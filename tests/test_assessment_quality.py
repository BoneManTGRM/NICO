import base64

import pytest

from nico.assessment_quality import polish_express_result


def test_limited_metadata_is_cleaned_and_regraded():
    result = {
        "status": "complete",
        "repository": "owner/repo",
        "generated_at": "2026-07-06T00:00:00Z",
        "client_name": "Client",
        "project_name": "Project",
        "executive_summary": "Assessment complete.",
        "maturity_signal": {"level": "Mid", "score": 62},
        "maturity_semaphore": {},
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 36, "status": "red", "summary": "Code audit.", "evidence": ["No recent pull-request evidence was found; direct-to-main work may reduce review traceability."], "findings": ["No recent pull-request evidence was found; direct-to-main work may reduce review traceability."], "unavailable": ["Commit activity unavailable: GitHub returned 403: rate limit exceeded"]},
            {"id": "ci_cd", "label": "CI/CD Analysis", "score": 20, "status": "red", "summary": "CI/CD.", "evidence": ["No GitHub Actions workflow files were available for analysis."], "findings": ["No CI/CD workflow files were found through GitHub contents access."], "unavailable": ["Workflow run history unavailable: GitHub returned 429: rate limit"]},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 76, "status": "green", "summary": "Arch.", "evidence": ["Repository root contains .github/."], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 51, "status": "yellow", "summary": "Velocity.", "evidence": ["Commit velocity: 0 commits over 180 days (0.0/week)."], "findings": [], "unavailable": []},
        ],
    }
    polished = polish_express_result(result)
    sections = {item["id"]: item for item in polished["sections"]}
    assert polished["assessment_quality"] == "degraded_metadata"
    assert polished["client_delivery_verdict"]["status"] == "human_review_required"
    assert sections["code_audit"]["score"] >= 80
    assert sections["ci_cd"]["score"] >= 50
    assert sections["velocity_complexity"]["score"] >= 55
    assert not any("GitHub returned" in note for note in sections["code_audit"]["unavailable"])


def test_dependency_range_warnings_and_backend_token_references_are_not_red_flags():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T00:00:00Z",
        "client_name": "NICO",
        "project_name": "NICO",
        "executive_summary": "Assessment complete.",
        "maturity_signal": {"level": "Mid", "score": 76},
        "maturity_semaphore": {},
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "score": 80, "status": "green", "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 46, "status": "yellow", "summary": "Deps.", "evidence": ["OSV returned 4 vulnerability record(s) for PyPI:uvicorn@[standard]>=0.30: GHSA-33c7."], "findings": ["package.json exists but no JavaScript lockfile was found in the checked paths.", "OSV returned 4 vulnerability record(s) for PyPI:uvicorn@[standard]>=0.30: GHSA-33c7."], "unavailable": ["pip-audit, npm audit, and OSV Scanner CLI execution are not yet run inside a sandboxed worker."]},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 51, "status": "yellow", "summary": "Secrets.", "evidence": ["Secret-pattern hits found in fetched text files: 6.", "nico/api/main.py:191: potential generic_secret_assignment evidence toke...oken", "nico/api/main.py:207: potential generic_secret_assignment evidence toke...oken", "nico/api/main.py:212: potential generic_secret_assignment evidence toke...oken"], "findings": ["Potential secret exposure requires immediate human review and credential rotation if confirmed."], "unavailable": ["Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog."]},
            {"id": "static_analysis", "label": "Static Analysis", "score": 86, "status": "green", "summary": "Static.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "score": 95, "status": "green", "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 94, "status": "green", "summary": "Arch.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 83, "status": "green", "summary": "Velocity.", "evidence": [], "findings": [], "unavailable": []},
        ],
    }
    polished = polish_express_result(result)
    sections = {item["id"]: item for item in polished["sections"]}
    assert sections["dependency_health"]["score"] >= 72
    assert sections["dependency_health"]["status"] == "yellow"
    assert not any("uvicorn@[standard]>=0.30" in note for note in sections["dependency_health"]["findings"])
    assert sections["secrets_review"]["score"] >= 74
    assert sections["secrets_review"]["status"] == "yellow"
    assert sections["secrets_review"]["findings"] == []
    assert polished["maturity_signal"]["score"] >= 83


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
        "sections": [{"id": "code_audit", "label": "Code Audit", "score": 67, "status": "yellow", "summary": "Useful evidence.", "evidence": ["Evidence item."], "findings": ["Finding item."], "unavailable": ["Unavailable item."]}],
        "quick_wins": ["Quick win."],
        "medium_term_plan": ["Medium plan."],
        "resourcing_recommendation": ["Review."],
        "risk_register": ["Risk."],
        "verification_checklist": ["Verify."],
        "reports": {"pdf_base64": "old"},
    }
    polished = polish_express_result(result)
    pdf_base64 = polished["reports"]["pdf_base64"]
    pdf_bytes = base64.b64decode(pdf_base64)
    assert polished["reports"]["pdf_style"] == "professional_report_v12_decision_ready"
    assert polished["reports"]["pdf_filename"] == "nico-express-owner-repo.pdf"
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 3000
