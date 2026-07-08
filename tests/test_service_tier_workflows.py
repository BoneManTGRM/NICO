from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate
from nico.service_tier_workflows import attach_service_tier_workflows, build_service_tier_workflows


def _minimal_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T22:40:00Z",
        "client_name": "",
        "project_name": "NICO",
        "assessment_mode": "express",
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "executive_summary": "NICO completed an authorized hosted Express Technical Health Assessment.",
        "maturity_signal": {"level": "Senior", "score": 86},
        "maturity_semaphore": {},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "green", "score": 90, "summary": "Dependency.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "green", "score": 90, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static Analysis", "status": "green", "score": 86, "summary": "Static.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 73, "summary": "Velocity.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_service_tier_workflows_define_express_mid_and_retainer():
    workflows = build_service_tier_workflows()

    assert workflows["status"] == "available"
    assert workflows["upgrade_path"] == ["express", "mid", "retainer"]
    assert workflows["tiers"]["express"]["duration"] == "2 weeks"
    assert workflows["tiers"]["mid"]["duration"] == "6 weeks"
    assert workflows["tiers"]["retainer"]["duration"] == "Monthly"
    assert "QA and functional testing review." in workflows["tiers"]["mid"]["scope"]


def test_attach_service_tier_workflows_adds_next_tier_guidance():
    result = attach_service_tier_workflows(_minimal_result())

    assert result["service_tier_workflows"]["recommended_next_tier"] == "mid"
    assert any("Make the next service tier as easy as Express" in item for item in result["quick_wins"])
    assert any("One-click Mid Technical Health Assessment workflow" in item for item in result["medium_term_plan"])


def test_final_hosted_gate_exports_service_tier_guidance():
    result = apply_final_hosted_truth_gate(_minimal_result())

    assert result["service_tier_workflows"]["recommended_next_tier"] == "mid"
    markdown = result["reports"]["markdown"]
    assert "Make the next service tier as easy as Express" in markdown
    assert "One-click Mid Technical Health Assessment workflow" in markdown
