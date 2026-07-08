from nico.evidence_ledger import attach_evidence_ledger, build_evidence_ledger
from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate


def _result_with_evidence():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T23:20:00Z",
        "report_run_id": "run-123",
        "maturity_signal": {"level": "Senior", "score": 82},
        "maturity_semaphore": {},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "yellow",
                "score": 74,
                "summary": "Dependency review is review-limited.",
                "evidence": ["OSV API queried exact package versions and returned no vulnerability records."],
                "findings": ["Dependency evidence status: OSV API completed_with_findings requires pip-audit/npm audit/OSV Scanner artifacts."],
                "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "yellow",
                "score": 74,
                "summary": "Static analysis is review-limited.",
                "evidence": ["Built-in static risk-pattern hits: 0."],
                "findings": ["Parsed Bandit artifact reported 50 finding(s)."],
                "unavailable": ["Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "status": "yellow",
                "score": 74,
                "summary": "Secrets review is review-limited.",
                "evidence": ["Parsed credential-scan and gitleaks git-history artifacts reported zero credential findings."],
                "findings": [],
                "unavailable": ["Scanner-worker secret tools unavailable: gitleaks, trufflehog."],
            },
        ],
        "scanner_worker_artifact": {
            "tools": {
                "pip-audit": {"tool": "pip-audit", "category": "dependency", "status": "completed", "returncode": 0, "findings": [], "command_intent": "pip-audit -r requirements.txt"},
                "bandit": {"tool": "bandit", "category": "static", "status": "completed", "returncode": 1, "findings": [{"issue_text": "test"}], "command_intent": "bandit -r ."},
            }
        },
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_evidence_ledger_tracks_artifacts_and_unavailable_evidence():
    ledger = build_evidence_ledger(_result_with_evidence())

    assert ledger["version"] == "evidence-ledger-v1"
    assert ledger["report_run_id"] == "run-123"
    assert ledger["entry_count"] >= 8
    assert ledger["verified_entry_count"] >= 2
    assert ledger["unavailable_entry_count"] >= 3
    assert ledger["coverage_by_section"]["dependency_health"]["missing_required_tools"]
    assert any(entry["tool_name"] == "pip-audit" and entry["verified_for_this_report"] for entry in ledger["entries"])
    assert all(entry["content_hash"] for entry in ledger["entries"])
    assert ledger["ledger_hash"]


def test_attach_evidence_ledger_adds_report_guard_and_guidance():
    result = attach_evidence_ledger(_result_with_evidence())

    assert result["evidence_ledger"]["entry_count"] >= 8
    assert result["report_quality_guards"]["evidence_ledger"]["ledger_hash"] == result["evidence_ledger"]["ledger_hash"]
    assert any("Evidence ledger attached" in item for item in result["medium_term_plan"])


def test_final_hosted_gate_attaches_evidence_ledger_before_report_rebuild():
    result = apply_final_hosted_truth_gate(_result_with_evidence())

    assert result["evidence_ledger"]["ledger_hash"]
    assert result["report_quality_guards"]["evidence_ledger"]["ledger_hash"] == result["evidence_ledger"]["ledger_hash"]
    assert any("Evidence ledger attached" in item for item in result["medium_term_plan"])
    assert result["reports"]["markdown"]
