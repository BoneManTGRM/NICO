from nico.complexity_artifact_integration import attach_complexity_artifact_to_report
from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate
from nico.scanner_artifact_integration import attach_scanner_artifacts_to_report
from nico.scanner_score_lifts import apply_verified_scanner_score_lifts


def _tool(name, category, status="completed_clean", findings=None, history=False):
    findings = findings or []
    return {
        "tool": name,
        "category": category,
        "status": "completed" if status.startswith("completed") else status,
        "evidence_status": status,
        "returncode": 1 if findings else 0,
        "findings": findings,
        "findings_count": len(findings),
        "verified_for_this_report": status.startswith("completed"),
        "scans_git_history": history,
        "command_intent": name,
    }


def _base_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T10:40:00Z",
        "maturity_signal": {"level": "Senior", "score": 82},
        "maturity_semaphore": {},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "yellow", "score": 74, "summary": "Dependency review-limited.", "evidence": [], "findings": ["Strict trust engine: Dependency cannot be GREEN while missing dependency scanner artifacts remain."], "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."]},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "yellow", "score": 74, "summary": "Secrets review-limited.", "evidence": [], "findings": ["Strict trust engine: Secrets cannot be GREEN while full-history secret coverage is unavailable or unverified."], "unavailable": ["Scanner-worker secret tools unavailable: gitleaks, trufflehog."]},
            {"id": "static_analysis", "label": "Static Analysis", "status": "yellow", "score": 74, "summary": "Static review-limited.", "evidence": [], "findings": ["Strict trust engine: Static Analysis cannot be GREEN while scanner-worker artifacts are missing."], "unavailable": ["Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript."]},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 74, "summary": "Velocity review-limited.", "evidence": [], "findings": ["Strict trust engine: Velocity / Complexity cannot be GREEN while release-readiness blockers remain."], "unavailable": ["Source-file footprint requires deeper complexity analysis."]},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "scanner_worker_artifact": {
            "generated_at": "2026-07-09T10:39:59Z",
            "repository": "BoneManTGRM/NICO",
            "checkout": {"commit_sha": "abc123", "history_depth": "full", "full_history_secret_scan_requested": True},
            "secret_history_scan": {"completed_tools": ["gitleaks", "trufflehog"], "history_aware": True},
            "complexity_engine": {
                "risk_level": "low",
                "source_file_count": 200,
                "analyzed_file_count": 200,
                "total_loc": 18000,
                "total_functions": 900,
                "call_graph_edge_count": 1200,
                "max_file_cyclomatic_complexity": 28,
                "velocity_score": 88,
                "complexity_score": 88,
                "evidence": ["Complexity engine analyzed 200 source file(s)."],
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
                "gitleaks": _tool("gitleaks", "secret", history=True),
                "trufflehog": _tool("trufflehog", "secret", history=True),
            },
        },
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def _bind_scanner_and_complexity(result):
    result = attach_scanner_artifacts_to_report(result)
    return attach_complexity_artifact_to_report(result)


def test_verified_clean_scanner_artifacts_lift_yellow_sections():
    result = _bind_scanner_and_complexity(_base_result())
    result = apply_verified_scanner_score_lifts(result)
    sections = {section["id"]: section for section in result["sections"]}

    assert sections["dependency_health"]["status"] == "green"
    assert sections["dependency_health"]["score"] >= 90
    assert sections["secrets_review"]["status"] == "green"
    assert sections["secrets_review"]["score"] >= 92
    assert sections["static_analysis"]["status"] == "green"
    assert sections["static_analysis"]["score"] >= 90
    assert sections["velocity_complexity"]["status"] == "green"
    assert sections["velocity_complexity"]["score"] >= 88
    assert result["report_quality_guards"]["verified_scanner_score_lifts"]["status"] == "applied"
    assert result["maturity_signal"]["score"] >= 90


def test_verified_score_lifts_do_not_lift_tools_with_findings_without_triage():
    result = _base_result()
    result["scanner_worker_artifact"]["tools"]["osv-scanner"] = _tool(
        "osv-scanner",
        "dependency",
        status="completed_with_findings",
        findings=[{"id": "OSV-1"}],
    )
    result = _bind_scanner_and_complexity(result)
    result = apply_verified_scanner_score_lifts(result)
    sections = {section["id"]: section for section in result["sections"]}

    assert sections["dependency_health"]["score"] == 74
    assert sections["dependency_health"]["status"] == "yellow"
    assert "dependency_health" not in result["report_quality_guards"]["verified_scanner_score_lifts"]["lifts"]


def test_final_gate_preserves_green_lifts_when_artifacts_are_clean():
    result = apply_final_hosted_truth_gate(_base_result())
    sections = {section["id"]: section for section in result["sections"] if isinstance(section, dict) and section.get("id")}

    assert result["report_quality_guards"]["verified_scanner_score_lifts"]["status"] == "applied"
    assert result["evidence_ledger"]["coverage_by_section"]["dependency_health"]["complete"] is True
    assert result["evidence_ledger"]["coverage_by_section"]["velocity_complexity"]["complete"] is True
    assert sections["dependency_health"]["status"] == "green"
    assert sections["secrets_review"]["status"] == "green"
    assert sections["static_analysis"]["status"] == "green"
    assert sections["velocity_complexity"]["status"] == "green"
    assert result["export_truth_gate"]["status"] == "passed"


def test_final_evidence_summary_shapes_drive_lifts_without_legacy_artifacts():
    result = _base_result()
    result.pop("complexity_artifact", None)
    result["scanner_worker_artifact"].pop("complexity_engine", None)
    result["scanner_worker_artifact"].pop("secret_history_scan", None)
    result["secret_history_scan"] = {"completed_tools": ["gitleaks", "trufflehog"], "full_history_verified": True}
    result["complexity_engine_summary"] = {
        "status": "completed",
        "verified_for_this_report": True,
        "source_file_count": 200,
        "total_loc": 18000,
        "total_functions": 900,
        "call_graph_edge_count": 1200,
        "max_file_cyclomatic_complexity": 28,
        "complexity_score": 88,
        "velocity_score": 88,
        "risk_level": "low",
        "artifact_hash": "abc123",
    }
    result["bandit_triage_summary"] = {
        "total_findings": 1,
        "approved_count": 1,
        "blocking_count": 0,
        "needs_review_count": 0,
        "unresolved_high_confidence_count": 0,
        "score_lift_allowed": True,
    }
    result["scanner_worker_artifact"]["tools"]["bandit"] = _tool(
        "bandit",
        "static",
        status="completed_with_findings",
        findings=[{"id": "B602"}],
    )

    result = apply_verified_scanner_score_lifts(result)
    sections = {section["id"]: section for section in result["sections"]}

    assert sections["dependency_health"]["status"] == "green"
    assert sections["secrets_review"]["status"] == "green"
    assert sections["static_analysis"]["score"] >= 88
    assert sections["velocity_complexity"]["score"] >= 88
    assert result["final_evidence_score_bridge"]["secret_clean_full_history"] is True
    assert result["final_evidence_score_bridge"]["complexity_profile_attached"] is True
    assert result["final_evidence_score_bridge"]["static_triaged_without_blockers"] is True
