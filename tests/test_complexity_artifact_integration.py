from nico.complexity_artifact_integration import attach_complexity_artifact_to_report
from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate


def _tool(name, category):
    return {
        "tool": name,
        "category": category,
        "status": "completed",
        "returncode": 0,
        "findings": [],
        "findings_count": 0,
        "verified_for_this_report": True,
        "command_intent": name,
    }


def _complexity_profile():
    return {
        "source_file_count": 210,
        "analyzed_file_count": 210,
        "total_loc": 18420,
        "total_functions": 980,
        "call_graph_edge_count": 1450,
        "max_file_cyclomatic_complexity": 28,
        "average_cyclomatic_per_file": 8.2,
        "manifest_dependency_count": 64,
        "external_import_count": 41,
        "top_external_imports": [("fastapi", 12)],
        "hotspots": [
            {
                "path": "nico/api/main.py",
                "hotspot_score": 44.2,
                "loc": 500,
                "cyclomatic_complexity": 28,
                "churn": 100,
                "primary_owner": "dev@example.com",
                "owner_concentration": 0.7,
            }
        ],
        "churn": {"files_with_churn": 80, "top_churn_files": [("nico/api/main.py", 100)]},
        "ownership": {"files_with_owner_signal": 75, "high_concentration_files": []},
        "complexity_score": 88,
        "architecture_score": 90,
        "velocity_score": 88,
        "risk_level": "low",
        "evidence": [
            "Complexity engine analyzed 210 source file(s), 18420 source LOC, and 980 function-like units.",
            "Estimated call graph edges: 1450; max file cyclomatic complexity: 28.",
            "Git churn data available for 80 file(s).",
            "Ownership signal available for 75 file(s).",
        ],
        "findings": [],
        "unavailable": [],
        "human_review_required": True,
    }


def _base_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T12:00:00Z",
        "maturity_signal": {"level": "Senior", "score": 82},
        "maturity_semaphore": {},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "yellow", "score": 74, "summary": "Dependency.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "yellow", "score": 74, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static Analysis", "status": "yellow", "score": 74, "summary": "Static.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 74, "summary": "Velocity review-limited.", "evidence": [], "findings": ["Release-readiness lift not applied because final-clean evidence is incomplete."], "unavailable": ["Source-file footprint requires deeper complexity analysis."]},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "scanner_worker_artifact": {
            "generated_at": "2026-07-09T11:59:59Z",
            "repository": "BoneManTGRM/NICO",
            "checkout": {"commit_sha": "abc123", "history_depth": "full", "full_history_secret_scan_requested": True},
            "secret_history_scan": {"completed_tools": ["gitleaks", "trufflehog"], "history_aware": True},
            "complexity_engine": _complexity_profile(),
            "tools": {
                "pip-audit": _tool("pip-audit", "dependency"),
                "npm-audit": _tool("npm-audit", "dependency"),
                "osv-scanner": _tool("osv-scanner", "dependency"),
                "bandit": _tool("bandit", "static"),
                "semgrep": _tool("semgrep", "static"),
                "eslint": _tool("eslint", "static"),
                "typescript": _tool("typescript", "static"),
                "gitleaks": _tool("gitleaks", "secret"),
                "trufflehog": _tool("trufflehog", "secret"),
            },
        },
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_complexity_artifact_attaches_to_velocity_and_architecture_sections():
    result = attach_complexity_artifact_to_report(_base_result())
    sections = {section["id"]: section for section in result["sections"]}

    assert result["complexity_artifact"]["verified_for_this_report"] is True
    assert result["complexity_artifact"]["commit_sha"] == "abc123"
    assert result["complexity_artifact"]["artifact_hash"]
    assert result["report_quality_guards"]["complexity_artifact"]["status"] == "completed"
    assert sections["velocity_complexity"]["unavailable"] == []
    assert any("Complexity engine current-run artifact completed" in line for line in sections["velocity_complexity"]["evidence"])
    assert any("Architecture complexity support" in line for line in sections["architecture_debt"]["evidence"])


def test_final_gate_uses_complexity_artifact_for_velocity_lift_and_ledger_coverage():
    result = apply_final_hosted_truth_gate(_base_result())
    sections = {section["id"]: section for section in result["sections"] if isinstance(section, dict) and section.get("id")}
    velocity_entries = [
        entry
        for entry in result["evidence_ledger"]["entries"]
        if entry.get("source") == "complexity_artifact" and entry.get("linked_section") == "velocity_complexity"
    ]

    assert result["report_quality_guards"]["complexity_artifact"]["verified_for_this_report"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["velocity_complexity"]["complete"] is True
    assert velocity_entries
    assert velocity_entries[0]["tool_name"] == "complexity engine"
    assert velocity_entries[0]["verified_for_this_report"] is True
    assert sections["velocity_complexity"]["status"] == "green"
    assert sections["velocity_complexity"]["score"] >= 88
    assert result["export_truth_gate"]["status"] == "passed"
