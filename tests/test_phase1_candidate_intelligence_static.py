from __future__ import annotations

from tests.phase1_candidate_fixtures import candidate, lineage_then_triage


def test_static_high_severity_without_supported_boundary_stays_needs_review() -> None:
    current = candidate("STATIC-HIGH", category="static", severity="high", context={
        "executable_code": True, "scope": "production", "first_party_reachable": True, "mitigated": False,
    })
    finding = lineage_then_triage([current], [])["findings"][0]
    assert finding["technical_triage_verdict"] == "needs_review"
    assert "supported_security_boundary" in finding["proof_gaps"]
    assert "source_to_sink_proof" in finding["proof_gaps"]


def test_static_confirmed_requires_complete_security_proof_chain() -> None:
    current = candidate("STATIC-PROVEN", category="static", severity="medium", context={
        "executable_code": True, "scope": "production", "first_party_reachable": True, "mitigated": False,
        "source_to_sink_established": True, "security_boundary_crossed": True, "consequence_established": True,
        "realistic_exploitability": True,
    })
    finding = lineage_then_triage([current], [])["findings"][0]
    assert finding["technical_triage_verdict"] == "confirmed"
    assert finding["rationale_code"] == "static_complete_security_proof_chain"
    assert finding["review_routing_class"] == "HUMAN_TECHNICAL_REVIEW"


def test_homogeneous_low_risk_needs_review_cluster_uses_group_review_not_individual_reopen() -> None:
    values = [candidate(f"STATIC-{index}", category="static", path=f"nico/generated_{index}.py", line=index + 1, severity="medium", context={"executable_code": True, "scope": "production"}) for index in range(20)]
    result = lineage_then_triage(values, []); metrics = result["technical_triage"]["workload_metrics"]
    assert metrics["needs_review_count"] == 20
    assert metrics["candidates_eligible_for_grouped_review"] == 20
    assert metrics["grouped_review_cluster_count"] == 1
    assert metrics["candidates_requiring_individual_human_attention"] == 0
    assert all(item["review_routing_class"] == "HUMAN_TECHNICAL_REVIEW" for item in result["findings"])
    assert all(item["grouped_review_eligible"] is True for item in result["findings"])
