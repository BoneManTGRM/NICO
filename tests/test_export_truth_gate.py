from nico.export_truth_gate import apply_export_truth_gate
from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate


def _green_json_contradiction():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T23:35:00Z",
        "maturity_signal": {"level": "Senior", "score": 89},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency is green but scanner proof is not verified.",
                "evidence": ["OSV returned 11 vulnerability record(s)."],
                "findings": ["Dependency evidence status: OSV API completed_with_findings."],
                "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."],
            }
        ],
        "reports": {
            "markdown": "# NICO\n\nSCORE 89/100\n\nDependency / Library Ecosystem — GREEN (90/100)\nScanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner.",
            "html": "<h1>NICO</h1><p>SCORE 89/100</p><h2>Dependency / Library Ecosystem — GREEN (90/100)</h2><p>Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner.</p>",
            "pdf_base64": "abc",
        },
    }


def _hosted_contradictory_input():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T23:35:00Z",
        "client_name": "",
        "project_name": "NICO",
        "assessment_mode": "express",
        "maturity_signal": {"level": "Senior", "score": 89},
        "maturity_semaphore": {},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code audit.", "evidence": [], "findings": [], "unavailable": []},
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is green from OSV evidence, but final scanner-clean dependency status is not claimed.",
                "evidence": ["OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0."],
                "findings": ["Dependency evidence status: OSV API completed_with_findings."],
                "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 86,
                "summary": "Static green score is not final scanner-clean claim.",
                "evidence": ["Built-in static risk-pattern hits: 0."],
                "findings": ["Parsed Bandit artifact reported 50 finding(s).", "Bandit triage summary: review_required_count=50; score impact=needs_human_review."],
                "unavailable": ["Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript."],
            },
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "green", "score": 90, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "green", "score": 82, "summary": "Velocity.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_export_truth_gate_blocks_green_export_contradictions():
    result = apply_export_truth_gate(_green_json_contradiction())

    assert result["export_truth_gate"]["status"] == "failed"
    assert result["export_truth_gate"]["export_allowed"] is False
    assert result["client_ready"] is False
    assert result["reports"]["pdf_base64"] == ""
    assert "NICO Export Blocked" in result["reports"]["markdown"]
    assert any(item["type"] == "json_green_contradiction" for item in result["export_truth_gate"]["violations"])


def test_final_hosted_gate_repairs_before_export_truth_gate():
    result = apply_final_hosted_truth_gate(_hosted_contradictory_input())

    assert result["export_truth_gate"]["status"] == "passed"
    assert result["export_truth_gate"]["export_allowed"] is True
    assert result["trust_engine"]["trust_level"] == "Review-limited"
    assert "NICO Export Blocked" not in result["reports"]["markdown"]
    sections = {item["id"]: item for item in result["sections"] if isinstance(item, dict) and "id" in item}
    assert sections["dependency_health"]["status"] == "yellow"
    assert sections["static_analysis"]["status"] == "yellow"
