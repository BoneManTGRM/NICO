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


def _export_review_result():
    result = _verified_result()
    result["maturity_signal"] = {"level": "Senior", "score": 89}
    result["export_truth_gate"] = {
        "status": "review_required",
        "draft_only": True,
        "export_allowed": True,
        "violations": [
            {
                "type": "export_green_contradiction",
                "section": "Velocity / Complexity",
                "reason": "Rendered evidence requires review.",
            }
        ],
    }
    return result


def test_trust_report_display_marks_review_limited_as_pending_and_adds_path():
    result = attach_trust_report_display(_base_result())
    section = result["sections"][0]

    assert result["trust_report_display"]["trust_level"] == "Review-limited"
    assert result["trust_report_display"]["workflow_state"] == "review_required"
    assert result["trust_report_display"]["status_semantics"] == "review_workflow_state"
    assert result["client_delivery_status"] == "Human Review Required"
    assert section["id"] == "trust_readiness"
    assert section["label"] == "Trust & Client Readiness"
    assert section["status"] == "pending"
    assert section["score"] == 82
    assert section["scoring_weight"] == 0
    assert section["score_basis"] == "final_maturity_signal_display_only"
    assert section["workflow_state"] == "review_required"
    assert section["status_semantics"] == "review_workflow_state"
    assert section["summary"].startswith("Review State: Human review required. Technical Score: 82/100.")
    assert any("Badge state is PENDING" in item for item in section["evidence"])
    assert any("pip-audit" in item for item in result["trust_report_display"]["why_not_higher"])
    assert any("Attach current-run clean pip-audit" in item for item in result["quick_wins"])
    assert section["unavailable"] == [
        "Client delivery remains blocked until the listed evidence or export findings are reviewed and resolved or formally accepted by an authorized human reviewer."
    ]


def test_export_truth_review_remains_pending_and_keeps_real_reason_visible():
    result = attach_trust_report_display(_export_review_result())
    section = result["sections"][0]

    assert result["trust_report_display"]["trust_level"] == "Review-limited"
    assert result["trust_report_display"]["workflow_state"] == "review_required"
    assert section["status"] == "pending"
    assert section["score"] == 89
    assert any("Export Truth Gate marked exports draft-only" in item for item in section["findings"])
    assert not any("approval has not been recorded" in item.lower() for item in section["unavailable"])
    guard = result["report_quality_guards"]["trust_report_display"]
    assert guard["workflow_state"] == "review_required"
    assert guard["score_changed"] is False
    assert guard["human_review_changed"] is False
    assert guard["delivery_authority_changed"] is False
    assert "Findings remain authoritative" in guard["guardrail"]


def test_trust_report_display_marks_verified_when_critical_proof_is_complete():
    result = attach_trust_report_display(_verified_result())

    assert result["trust_report_display"]["trust_level"] == "Verified"
    assert result["trust_report_display"]["workflow_state"] == "verified_evidence"
    assert result["client_delivery_status"] == "Client-ready after human approval"
    assert result["sections"][0]["status"] == "green"
    assert result["sections"][0]["score"] == 92
    assert result["sections"][0]["findings"] == ["No trust display blockers found."]
    assert result["sections"][0]["unavailable"] == []


def test_hosted_gate_exports_trust_readiness_section():
    result = apply_final_hosted_truth_gate(_base_result())

    assert result["trust_report_display"]["trust_level"] == "Review-limited"
    assert result["sections"][0]["id"] == "trust_readiness"
    assert result["sections"][0]["status"] == "pending"
    assert result["sections"][0]["score"] == result["maturity_signal"]["score"]
    assert result["sections"][0]["scoring_weight"] == 0
    assert "Trust & Client Readiness" in result["reports"]["markdown"]
    assert "Review State:" in result["reports"]["markdown"]
