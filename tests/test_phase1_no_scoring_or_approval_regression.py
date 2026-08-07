from __future__ import annotations

from copy import deepcopy

from tests.phase1_candidate_fixtures import candidate, register
from nico.candidate_phase1_triage_v1 import apply_phase1_technical_triage


def test_phase1_triage_does_not_change_canonical_counts_or_dispositions() -> None:
    findings = [
        candidate("A", category="static", context={}),
        candidate("B", category="secret", scanner="trufflehog", rule="token", severity="high", context={"verified": True}),
    ]
    source = register(findings)
    source["totals"].update({"material": 0, "review_required": 2})
    before_totals = deepcopy(source["totals"])
    before_dispositions = [item["disposition"] for item in source["findings"]]

    result = apply_phase1_technical_triage(source, triage={"s": "nico.candidate-technical-triage.v1", "c": "prior", "n": 0, "q": {}, "x": []})

    assert result["totals"] == before_totals
    assert [item["disposition"] for item in result["findings"]] == before_dispositions
    assert result["technical_triage"]["score_effect"] == "none"
    assert result["technical_triage"]["confirmed_count"] == 1
    assert result["technical_triage"]["needs_review_count"] == 1


def test_phase1_routes_are_workload_metadata_not_human_decisions() -> None:
    finding = candidate("A", category="static", context={"executable_code": False, "comment_or_string": True, "scope": "test"})
    source = register([finding])
    result = apply_phase1_technical_triage(source, triage={"s": "nico.candidate-technical-triage.v1", "c": "prior", "n": 0, "q": {}, "x": []})
    record = result["findings"][0]

    assert record["review_routing_is_human_decision"] is False
    assert record["human_disposition"] == "pending"
    assert record["human_approval_status"] == "pending"
    assert record["technical_triage_human_approval_status"] == "pending"
    assert record["technical_triage_human_approval_carried_forward"] is False
    assert record["technical_triage_client_delivery_allowed"] is False
    assert result["technical_triage"]["human_disposition_created"] is False
    assert result["technical_triage"]["reviewer_identity_created"] is False
    assert result["technical_triage"]["risk_acceptance_created"] is False
    assert result["technical_triage"]["client_delivery_allowed"] is False
