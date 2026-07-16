from __future__ import annotations

from nico.mid_score_intelligence import (
    MID_SCORE_INTELLIGENCE_VERSION,
    attach_mid_score_intelligence,
    build_mid_score_intelligence,
)


def _section(section_id: str, label: str, score: int, status: str = "yellow") -> dict:
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": status,
        "summary": f"Bounded evidence summary for {label}.",
        "evidence": [f"Evidence for {label}."],
        "findings": [f"Finding for {label}."] if score < 80 else [],
        "unavailable": [f"Limitation for {label}."] if score < 75 else [],
    }


def _result() -> dict:
    sections = [
        _section("code_audit", "Code Audit", 60),
        _section("dependency_health", "Dependency / Library Ecosystem", 72),
        _section("secrets_review", "Secrets Exposure Review", 80, "green"),
        _section("static_analysis", "Static Analysis", 39, "red"),
        _section("ci_cd", "CI/CD Analysis", 95, "green"),
        _section("architecture_debt", "Architecture & Technical Debt", 85, "green"),
        _section("velocity_complexity", "Velocity / Complexity", 76),
        _section("business_roadmap", "Business-Aligned Roadmap", 0, "gray"),
    ]
    return {
        "status": "complete",
        "assessment_type": "mid",
        "service_tier": "mid",
        "mode": "mid",
        "report_generation_status": "complete",
        "approval_request_status": "pending",
        "approval_request": {"approval_id": "approval_mid_score", "status": "pending"},
        "reports": {"markdown": "# Mid draft", "pdf_base64": "JVBERi0xLjQ="},
        "assessment": {
            "status": "draft",
            "maturity_signal": {"score": 71, "level": "Mid", "evidence_readiness_score": 74},
            "sections": sections,
        },
    }


def test_mid_score_intelligence_explains_exact_weighted_score_without_blending_express() -> None:
    intelligence = build_mid_score_intelligence(_result())

    assert intelligence["version"] == MID_SCORE_INTELLIGENCE_VERSION
    assert intelligence["status"] == "complete"
    assert intelligence["score_contract"]["name"] == "Mid seven-section evidence-weighted technical score"
    assert intelligence["score_contract"]["reported_score"] == 71
    assert intelligence["score_contract"]["calculated_score"] == 71
    assert intelligence["score_contract"]["calculation_matches_reported_score"] is True
    assert intelligence["score_contract"]["express_directly_comparable"] is False
    assert intelligence["score_contract"]["gray_sections_excluded"] is True
    assert intelligence["score_contract"]["score_forced_upward"] is False

    rows = {row["section_id"]: row for row in intelligence["weighted_sections"]}
    assert set(rows) == {
        "code_audit",
        "dependency_health",
        "secrets_review",
        "static_analysis",
        "ci_cd",
        "architecture_debt",
        "velocity_complexity",
    }
    assert rows["code_audit"]["weight"] == 20
    assert rows["code_audit"]["weighted_points"] == 12.0
    assert rows["static_analysis"]["weighted_points"] == 5.85
    assert rows["ci_cd"]["weighted_points"] == 14.25
    assert "business_roadmap" not in rows


def test_mid_score_intelligence_prioritizes_real_constraints_and_bounds_projection() -> None:
    intelligence = build_mid_score_intelligence(_result())

    constraints = intelligence["top_constraints"]
    assert constraints[0]["section_id"] == "static_analysis"
    assert constraints[1]["section_id"] == "code_audit"
    scenario = intelligence["bounded_improvement_scenario"]
    assert scenario["current_score"] == 71
    assert scenario["projected_lift"] == 11.75
    assert scenario["projected_score"] == 83
    assert scenario["guaranteed"] is False
    assert scenario["requires_verified_reassessment"] is True
    assert scenario["new_findings_could_reduce_projection"] is True


def test_mid_score_intelligence_reports_artifact_and_review_lifecycle_separately() -> None:
    intelligence = build_mid_score_intelligence(_result())
    lifecycle = intelligence["report_lifecycle"]

    assert lifecycle["draft_generation_status"] == "complete"
    assert lifecycle["markdown_available"] is True
    assert lifecycle["pdf_available"] is True
    assert lifecycle["human_review_status"] == "pending"
    assert lifecycle["human_review_required"] is True
    assert lifecycle["client_delivery_allowed"] is False
    assert lifecycle["approved_final_report_available"] is False


def test_attach_mid_score_intelligence_copies_same_truth_into_assessment() -> None:
    attached = attach_mid_score_intelligence(_result())

    assert attached["mid_score_intelligence"]["score_contract"]["calculated_score"] == 71
    assert attached["assessment"]["score_intelligence"] == attached["mid_score_intelligence"]
    assert attached["assessment"]["maturity_signal"]["score"] == 71
