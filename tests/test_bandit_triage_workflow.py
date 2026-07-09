from nico.bandit_triage import approval_template_for_triage, build_bandit_triage
from nico.bandit_triage_workflow import attach_bandit_triage_to_report
from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate


BANDIT_FINDING = {
    "test_id": "B101",
    "test_name": "assert_used",
    "filename": "tests/test_example.py",
    "line_number": 12,
    "issue_severity": "LOW",
    "issue_confidence": "HIGH",
    "issue_text": "Use of assert detected.",
}


def _tool(name, category, *, findings=None, history=False):
    findings = findings or []
    return {
        "tool": name,
        "category": category,
        "status": "completed",
        "returncode": 1 if findings else 0,
        "findings": findings,
        "findings_count": len(findings),
        "verified_for_this_report": True,
        "scans_git_history": history,
        "command_intent": name,
    }


def _scanner_artifact():
    return {
        "generated_at": "2026-07-09T11:40:00Z",
        "repository": "BoneManTGRM/NICO",
        "checkout": {"commit_sha": "abc123", "history_depth": "full", "full_history_secret_scan_requested": True},
        "secret_history_scan": {"completed_tools": ["gitleaks", "trufflehog"], "history_aware": True},
        "complexity_engine": {"velocity_score": 88, "complexity_score": 88, "findings": [], "evidence": ["Complexity current-run evidence attached."]},
        "tools": {
            "pip-audit": _tool("pip-audit", "dependency"),
            "npm-audit": _tool("npm-audit", "dependency"),
            "osv-scanner": _tool("osv-scanner", "dependency"),
            "bandit": _tool("bandit", "static", findings=[BANDIT_FINDING]),
            "semgrep": _tool("semgrep", "static"),
            "eslint": _tool("eslint", "static"),
            "typescript": _tool("typescript", "static"),
            "gitleaks": _tool("gitleaks", "secret", history=True),
            "trufflehog": _tool("trufflehog", "secret", history=True),
        },
    }


def _base_result(*, approval=None):
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T11:40:01Z",
        "maturity_signal": {"level": "Senior", "score": 82},
        "maturity_semaphore": {},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "yellow", "score": 74, "summary": "Dependency.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "yellow", "score": 74, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static Analysis", "status": "yellow", "score": 74, "summary": "Static review-limited.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 74, "summary": "Velocity.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "scanner_worker_artifact": _scanner_artifact(),
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }
    if approval:
        result["bandit_triage_approval"] = approval
    return result


def _approval_for_finding():
    triage = build_bandit_triage(_scanner_artifact())
    key = triage["top_findings"][0]["finding_key"]
    return {
        "artifact_schema": "nico.bandit_triage_approval.v1",
        "decisions": [
            {
                "finding_key": key,
                "rule_id": "B101",
                "location": "tests/test_example.py:12",
                "decision": "false_positive",
                "reviewer": "security-reviewer",
                "justification": "Assert usage is confined to test code and is not reachable in production runtime.",
            }
        ],
    }


def test_bandit_triage_creates_stable_keys_and_template():
    triage = build_bandit_triage(_scanner_artifact())
    template = approval_template_for_triage(triage)

    assert triage["status"] == "needs_human_review"
    assert triage["finding_count"] == 1
    assert triage["review_required_count"] == 1
    assert triage["top_findings"][0]["finding_key"].startswith("bandit_")
    assert template["decisions"][0]["finding_key"] == triage["top_findings"][0]["finding_key"]


def test_signed_bandit_approval_clears_review_required_count():
    triage = build_bandit_triage(_scanner_artifact(), approval_artifact=_approval_for_finding())

    assert triage["status"] == "approved_no_blockers"
    assert triage["blocking_count"] == 0
    assert triage["review_required_count"] == 0
    assert triage["approved_count"] == 1
    assert triage["human_review_required"] is False


def test_bandit_triage_attaches_to_static_section_and_preserves_template_when_unapproved():
    result = attach_bandit_triage_to_report(_base_result())
    section = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert result["bandit_triage"]["status"] == "needs_human_review"
    assert result["report_quality_guards"]["bandit_triage"]["review_required_count"] == 1
    assert result["bandit_triage_approval_template"]["decisions"][0]["finding_key"].startswith("bandit_")
    assert any("Bandit triage classified 1 finding" in line for line in section["evidence"])
    assert any("finding_key=bandit_" in line for line in section["findings"])


def test_final_gate_lifts_static_after_signed_bandit_triage_approval():
    result = apply_final_hosted_truth_gate(_base_result(approval=_approval_for_finding()))
    sections = {section["id"]: section for section in result["sections"] if isinstance(section, dict) and section.get("id")}

    assert result["bandit_triage"]["status"] == "approved_no_blockers"
    assert result["bandit_triage"]["review_required_count"] == 0
    assert result["report_quality_guards"]["bandit_triage"]["approval_artifact_attached"] is True
    assert sections["static_analysis"]["status"] == "green"
    assert sections["static_analysis"]["score"] >= 88
    assert result["report_quality_guards"]["verified_scanner_score_lifts"]["status"] == "applied"
    assert result["export_truth_gate"]["status"] == "passed"
