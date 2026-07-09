from nico.hosted_full_evidence_runtime import ensure_hosted_runtime_evidence
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


def _artifact():
    return {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "completed",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T13:20:00Z",
        "checkout": {
            "commit_sha": "abc123",
            "history_depth": "full",
            "full_history_secret_scan_requested": True,
            "commit_count": 100,
        },
        "secret_history_scan": {"completed_tools": ["gitleaks", "trufflehog"], "history_aware": True},
        "complexity_engine": {
            "source_file_count": 279,
            "analyzed_file_count": 279,
            "total_loc": 20000,
            "total_functions": 1100,
            "call_graph_edge_count": 1400,
            "max_file_cyclomatic_complexity": 28,
            "velocity_score": 88,
            "complexity_score": 88,
            "risk_level": "low",
            "evidence": ["Complexity engine analyzed 279 source file(s)."],
            "findings": [],
            "unavailable": [],
        },
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
    }


def _yellow_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T13:19:59Z",
        "maturity_signal": {"level": "Senior", "score": 82},
        "maturity_semaphore": {},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "yellow", "score": 74, "summary": "Dependency review-limited.", "evidence": [], "findings": [], "unavailable": ["Scanner-worker dependency tools unavailable: npm-audit, osv-scanner."]},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "yellow", "score": 74, "summary": "Secrets review-limited.", "evidence": [], "findings": [], "unavailable": ["Scanner-worker secret tools unavailable: trufflehog."]},
            {"id": "static_analysis", "label": "Static Analysis", "status": "yellow", "score": 74, "summary": "Static review-limited.", "evidence": [], "findings": [], "unavailable": ["Scanner-worker static tools unavailable: semgrep, eslint, typescript."]},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 74, "summary": "Velocity review-limited.", "evidence": [], "findings": [], "unavailable": ["Release-readiness lift not applied because required final-clean evidence is incomplete: static_analysis_no_review_findings"]},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_runtime_refresh_attaches_raw_scanner_artifact(monkeypatch):
    monkeypatch.setattr("nico.hosted_full_evidence_runtime.run_hosted_scanner_worker", lambda payload: _artifact())

    result = ensure_hosted_runtime_evidence(_yellow_result())

    assert result["scanner_worker_artifact"]["tools"]["npm-audit"]["findings"] == []
    assert result["scanner_worker_artifact_normalized"]["dependency_evidence_complete"] is True
    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["missing_dependency_tools"] == []


def test_final_gate_can_turn_yellow_sections_green_from_runtime_evidence(monkeypatch):
    monkeypatch.setattr("nico.hosted_full_evidence_runtime.run_hosted_scanner_worker", lambda payload: _artifact())

    result = apply_final_hosted_truth_gate(_yellow_result())
    sections = {section["id"]: section for section in result["sections"] if isinstance(section, dict) and section.get("id")}

    assert result["report_quality_guards"]["hosted_full_evidence_runtime"]["status"] == "completed"
    assert result["evidence_ledger"]["coverage_by_section"]["dependency_health"]["complete"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["static_analysis"]["complete"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["secrets_review"]["complete"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["velocity_complexity"]["complete"] is True
    assert sections["dependency_health"]["status"] == "green"
    assert sections["secrets_review"]["status"] == "green"
    assert sections["static_analysis"]["status"] == "green"
    assert sections["velocity_complexity"]["status"] == "green"
