from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate
from nico.scanner_artifact_integration import attach_scanner_artifacts_to_report


def _result_with_clean_scanner_artifact():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T23:55:00Z",
        "maturity_signal": {"level": "Senior", "score": 90},
        "maturity_semaphore": {},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review uses current scanner artifacts.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 86,
                "summary": "Static review uses current scanner artifacts.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "status": "green",
                "score": 90,
                "summary": "Secrets review uses current scanner artifacts.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Scanner-worker secret tools unavailable: gitleaks, trufflehog."],
            },
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "green", "score": 82, "summary": "Velocity.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "scanner_worker_artifact": {
            "generated_at": "2026-07-08T23:54:59Z",
            "repository": "BoneManTGRM/NICO",
            "checkout": {"commit_sha": "abc123", "history_depth": "full", "full_history_secret_scan_requested": True},
            "tools": {
                "pip-audit": {"tool": "pip-audit", "category": "dependency", "status": "completed", "returncode": 0, "findings": [], "command_intent": "pip-audit -r requirements.txt"},
                "npm-audit": {"tool": "npm-audit", "category": "dependency", "status": "completed", "returncode": 0, "findings": [], "command_intent": "npm audit --json"},
                "osv-scanner": {"tool": "osv-scanner", "category": "dependency", "status": "completed", "returncode": 0, "findings": [], "command_intent": "osv-scanner --format json ."},
                "bandit": {"tool": "bandit", "category": "static", "status": "completed", "returncode": 0, "findings": [], "command_intent": "bandit -r ."},
                "semgrep": {"tool": "semgrep", "category": "static", "status": "completed", "returncode": 0, "findings": [], "command_intent": "semgrep scan"},
                "eslint": {"tool": "eslint", "category": "static", "status": "completed", "returncode": 0, "findings": [], "command_intent": "npx eslint ."},
                "typescript": {"tool": "typescript", "category": "static", "status": "completed", "returncode": 0, "findings": [], "command_intent": "npx tsc --noEmit"},
                "gitleaks": {"tool": "gitleaks", "category": "secret", "status": "completed", "returncode": 0, "findings": [], "scans_git_history": True, "command_intent": "gitleaks detect"},
                "trufflehog": {"tool": "trufflehog", "category": "secret", "status": "completed", "returncode": 0, "findings": [], "scans_git_history": True, "command_intent": "trufflehog git"},
            },
            "secret_history_scan": {"completed_tools": ["gitleaks", "trufflehog"], "history_aware": True},
        },
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def _result_without_scanner_artifact():
    result = _result_with_clean_scanner_artifact()
    result.pop("scanner_worker_artifact")
    return result


def test_scanner_artifact_integration_replaces_stale_unavailable_notes():
    result = attach_scanner_artifacts_to_report(_result_with_clean_scanner_artifact())
    sections = {item["id"]: item for item in result["sections"]}

    assert result["report_quality_guards"]["scanner_artifact_integration"]["status"] == "attached"
    assert result["scanner_worker_artifact"]["verified_for_report_run"] is True
    assert result["scanner_worker_artifact"]["artifact_hash"]
    assert result["scanner_artifacts"]["report_run_id"] == result["report_run_id"]
    assert result["scanner_artifacts"]["commit_sha"] == "abc123"
    assert result["scanner_artifacts"]["tools"]["pip-audit"]["evidence_status"] == "completed_clean"
    assert result["scanner_artifacts"]["tools"]["pip-audit"]["verified_for_this_report"] is True
    assert result["scanner_artifacts"]["tools"]["pip-audit"]["artifact_hash"]
    assert sections["dependency_health"]["unavailable"] == []
    assert sections["static_analysis"]["unavailable"] == []
    assert sections["secrets_review"]["unavailable"] == []
    assert "Scanner-worker dependency tools completed: pip-audit, npm-audit, osv-scanner." in sections["dependency_health"]["evidence"]
    assert "Scanner-worker static tools completed: bandit, semgrep, eslint, typescript." in sections["static_analysis"]["evidence"]
    assert "Scanner-worker secret tools completed: gitleaks, trufflehog." in sections["secrets_review"]["evidence"]


def test_scanner_artifact_missing_remains_visible_not_verified():
    result = attach_scanner_artifacts_to_report(_result_without_scanner_artifact())

    assert result["report_quality_guards"]["scanner_artifact_integration"]["status"] == "missing"
    assert result["report_quality_guards"]["scanner_artifact_integration"]["artifact_attached"] is False


def test_hosted_gate_uses_current_run_scanner_artifact_before_trust_caps():
    result = apply_final_hosted_truth_gate(_result_with_clean_scanner_artifact())
    sections = {item["id"]: item for item in result["sections"] if isinstance(item, dict) and "id" in item}
    dependency_entries = [
        entry
        for entry in result["evidence_ledger"]["entries"]
        if entry.get("source") == "scanner_worker_artifact" and entry.get("tool_name") == "pip-audit"
    ]

    assert result["report_quality_guards"]["scanner_artifact_integration"]["status"] == "attached"
    assert result["evidence_ledger"]["coverage_by_section"]["dependency_health"]["complete"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["static_analysis"]["complete"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["secrets_review"]["complete"] is True
    assert dependency_entries
    assert dependency_entries[0]["status"] == "completed_clean"
    assert dependency_entries[0]["verified_for_this_report"] is True
    assert dependency_entries[0]["commit_sha"] == "abc123"
    assert dependency_entries[0]["artifact_id"].startswith(result["report_run_id"])
    assert sections["dependency_health"]["status"] == "green"
    assert sections["static_analysis"]["status"] == "green"
    assert result["export_truth_gate"]["status"] == "passed"
