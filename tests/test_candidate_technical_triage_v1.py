from __future__ import annotations

from nico.candidate_technical_triage_v1 import (
    apply_candidate_technical_triage,
    load_default_technical_triage,
)


def _row_for_verdict(source: dict, verdict: str) -> list:
    codebook = source["q"]
    return next(
        row
        for row in source["x"]
        if codebook[row[1]][0] == verdict
    )


def test_default_technical_triage_is_complete_and_proposal_only() -> None:
    source = load_default_technical_triage()

    assert source["n"] == 662
    assert source["v"] == {"needs_review": 38, "not_actionable": 624}
    assert source["p"] == {
        "approved_or_nonblocking": 607,
        "excluded_test_only": 17,
        "review_required": 38,
    }
    assert source["c"] == "9c876ba4e3e9bb152de52567232038e52a6bbb3e"
    assert source["h"] == "pending"
    assert source["d"] is False
    assert source["runtime_validation_performed"] is False


def test_safe_lineage_imports_not_actionable_proposal_without_approving() -> None:
    source = load_default_technical_triage()
    candidate_id = _row_for_verdict(source, "not_actionable")[0]
    register = {
        "findings": [
            {
                "finding_id": "NICO-CURRENT",
                "prior_candidate_id": candidate_id,
                "lineage_status": "carried_forward_exact",
                "disposition": "review_required",
                "human_approval_status": "pending",
            }
        ],
        "totals": {"raw": 1},
    }

    result = apply_candidate_technical_triage(register, triage=source)
    finding = result["findings"][0]

    assert finding["technical_triage_status"] == "imported_proposal"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["technical_triage_proposed_disposition"] in {
        "approved_or_nonblocking",
        "excluded_test_only",
    }
    assert finding["technical_review_required"] is False
    assert finding["disposition"] == "review_required"
    assert finding["human_approval_status"] == "pending"
    assert finding["technical_triage_human_approval_carried_forward"] is False
    assert finding["technical_triage_client_delivery_allowed"] is False
    assert result["technical_triage"]["human_approval_status"] == "pending"
    assert result["technical_triage"]["client_delivery_allowed"] is False
    assert result["technical_triage"]["score_effect"] == (
        "none_canonical_dispositions_and_totals_unchanged"
    )


def test_needs_review_rank_is_retained_but_canonical_disposition_is_unchanged() -> None:
    source = load_default_technical_triage()
    candidate_id = _row_for_verdict(source, "needs_review")[0]
    register = {
        "findings": [
            {
                "finding_id": "NICO-CURRENT",
                "prior_candidate_id": candidate_id,
                "lineage_status": "carried_forward_location_changed",
                "disposition": "review_required",
            }
        ],
        "totals": {"raw": 1},
    }

    result = apply_candidate_technical_triage(register, triage=source)
    finding = result["findings"][0]

    assert finding["technical_triage_verdict"] == "needs_review"
    assert finding["technical_triage_exploitability_stack_rank"] is not None
    assert finding["technical_review_required"] is True
    assert finding["disposition"] == "review_required"


def test_changed_or_new_evidence_never_inherits_prior_technical_verdict() -> None:
    source = load_default_technical_triage()
    candidate_id = _row_for_verdict(source, "not_actionable")[0]
    register = {
        "findings": [
            {
                "finding_id": "NICO-CHANGED",
                "prior_candidate_id": candidate_id,
                "lineage_status": "carried_forward_evidence_changed",
                "disposition": "review_required",
            },
            {
                "finding_id": "NICO-NEW",
                "lineage_status": "newly_observed",
                "disposition": "review_required",
            },
        ],
        "totals": {"raw": 2},
    }

    result = apply_candidate_technical_triage(register, triage=source)

    assert result["technical_triage"]["imported_candidate_count"] == 0
    assert result["technical_triage"]["current_evidence_review_required"] == 2
    for finding in result["findings"]:
        assert finding["technical_triage_status"] == "current_evidence_review_required"
        assert "technical_triage_verdict" not in finding
        assert finding["disposition"] == "review_required"
        assert finding["technical_triage_human_approval_carried_forward"] is False
