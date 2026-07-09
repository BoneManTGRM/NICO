from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate
from nico.trust_report_display import attach_trust_report_display


def _base_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T00:05:00Z",
        "maturity_signal": {"level": "Senior", "score": 82},
        "maturity_semaphore": {},
        "sections": [
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "yellow", "score": 74, "summary": "Dependency review-limited.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static Analysis", "status": "yellow", "score": 74, "summary": "Static review-limited.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "green", "score": 90, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "evidence_ledger": {
            "status": "partial",
            "coverage_by_section": {
                "dependency_health": {"missing_required_tools": ["pip-audit", "npm-audit", "osv-scanner"]},
                "static_analysis": {"missing_required_tools": ["bandit", "semgrep", "eslint", "typescript"]},
                "secrets_review": {"missing_required_tools": []},
            },
        },
        "trust_engine": {"violations": [{"section": "Dependency", "reason": "missing proof"}]},
        "report_quality_guards": {"scanner_artifact_integration": {"status": "missing"}},
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def _verified_result():
    result = _base_result()
    result["maturity_signal"] = {"level": "Senior", "score": 92}
    for section in result["sections"]:
        section["status"] = "green"
        section["score"] = 90
    result["evidence_ledger"] = {
        "status": "available",
        "coverage_by_section": {
            "dependency_health": {"missing_required_tools": []},
            "static_analysis": {"missing_required_tools": []},
            "secrets_review": {"missing_required_tools": []},
        },
    }
    result["trust_engine"] = {"violations": []}
    result["report_quality_guards"] = {"scanner_artifact_integration": {"status": "attached"}}
    return result


def test_trust_report_display_marks_review_limited_and_adds_path():
    result = attach_trust_report_display(_base_result())

    assert result["trust_report_display"]["trust_level"] == "Review-limited"
    assert result["client_delivery_status"] == "Human Review Required"
    assert result["sections"][0]["id"] == "trust_readiness"
    assert result["sections"][0]["label"] == "Trust & Client Readiness"
    assert any("pip-audit" in item for item in result["trust_report_display"]["why_not_higher"])
    assert any("Attach current-run clean pip-audit" in item for item in result["quick_wins"])


def test_trust_report_display_marks_verified_when_critical_proof_is_complete():
    result = attach_trust_report_display(_verified_result())

    assert result["trust_report_display"]["trust_level"] == "Verified"
    assert result["client_delivery_status"] == "Client-ready after human approval"
    assert result["sections"][0]["status"] == "green"
    assert result["sections"][0]["findings"] == ["No trust display blockers found."]


def test_hosted_gate_exports_trust_readiness_section():
    result = apply_final_hosted_truth_gate(_base_result())

    assert result["trust_report_display"]["trust_level"] == "Review-limited"
    assert result["sections"][0]["id"] == "trust_readiness"
    assert "Trust & Client Readiness" in result["reports"]["markdown"]
    assert "Trust Level:" in result["reports"]["markdown"]
