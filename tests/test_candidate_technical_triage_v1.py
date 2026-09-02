from __future__ import annotations

from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage, load_default_technical_triage


def _row_for_verdict(source: dict, verdict: str) -> list:
    codebook = source["q"]
    return next(row for row in source["x"] if codebook[row[1]][0] == verdict)


def _synthetic_source(verdict: str) -> tuple[dict, str]:
    candidate_id = f"OLD-{verdict}"
    proposal = "approved_or_nonblocking" if verdict == "not_actionable" else "review_required"
    rank = None if verdict == "not_actionable" else 1
    source = {
        "s": "nico.candidate-technical-triage.v1",
        "c": "prior-sha",
        "n": 1,
        "q": {"code": [verdict, "high", proposal, "retained", "rationale", "boundary", "next", [], "rank"]},
        "x": [[candidate_id, "code", rank]],
    }
    return source, candidate_id


def test_default_technical_triage_is_complete_and_proposal_only() -> None:
    source = load_default_technical_triage()
    assert source["n"] == 662
    assert source["v"] == {"needs_review": 38, "not_actionable": 624}
    assert source["p"] == {"approved_or_nonblocking": 607, "excluded_test_only": 17, "review_required": 38}
    assert source["c"] == "9c876ba4e3e9bb152de52567232038e52a6bbb3e"
    assert source["h"] == "pending"
    assert source["d"] is False
    assert source["runtime_validation_performed"] is False


def test_safe_lineage_imports_not_actionable_proposal_without_approving() -> None:
    source, candidate_id = _synthetic_source("not_actionable")
    register = {"findings": [{"finding_id": "NICO-CURRENT", "prior_candidate_id": candidate_id, "lineage_status": "carried_forward_exact", "disposition": "review_required", "human_approval_status": "pending"}], "totals": {"raw": 1}}
    result = apply_candidate_technical_triage(register, triage=source)
    finding = result["findings"][0]
    assert finding["technical_triage_status"] == "imported_proposal"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["technical_triage_proposed_disposition"] in {"approved_or_nonblocking", "excluded_test_only"}
    assert finding["technical_review_required"] is False
    assert finding["disposition"] == "review_required"
    assert finding["human_approval_status"] == "pending"
    assert finding["technical_triage_human_approval_carried_forward"] is False
    assert finding["technical_triage_client_delivery_allowed"] is False
    assert result["technical_triage"]["human_approval_status"] == "pending"
    assert result["technical_triage"]["client_delivery_allowed"] is False
    assert result["technical_triage"]["score_effect"] == "none_canonical_dispositions_and_totals_unchanged"


def test_needs_review_rank_is_retained_but_canonical_disposition_is_unchanged() -> None:
    source, candidate_id = _synthetic_source("needs_review")
    register = {"findings": [{"finding_id": "NICO-CURRENT", "prior_candidate_id": candidate_id, "lineage_status": "carried_forward_location_changed", "disposition": "review_required"}], "totals": {"raw": 1}}
    result = apply_candidate_technical_triage(register, triage=source)
    finding = result["findings"][0]
    assert finding["technical_triage_verdict"] == "needs_review"
    assert finding["technical_triage_exploitability_stack_rank"] is not None
    assert finding["technical_review_required"] is True
    assert finding["disposition"] == "review_required"


def test_changed_or_new_evidence_gets_fresh_triage_without_inheriting_prior_verdict() -> None:
    source, candidate_id = _synthetic_source("not_actionable")
    register = {"findings": [
        {"finding_id": "NICO-CHANGED", "prior_candidate_id": candidate_id, "lineage_status": "carried_forward_evidence_changed", "category": "static", "scanner": "semgrep", "rule_id": "x", "disposition": "review_required"},
        {"finding_id": "NICO-NEW", "lineage_status": "newly_observed", "category": "static", "scanner": "semgrep", "rule_id": "y", "disposition": "review_required"},
    ], "totals": {"raw": 2}}
    result = apply_candidate_technical_triage(register, triage=source)
    assert result["technical_triage"]["imported_candidate_count"] == 0
    assert result["technical_triage"]["fresh_technical_triage_completed"] == 2
    assert result["technical_triage"]["technical_triage_pending"] == 0
    for finding in result["findings"]:
        assert finding["technical_triage_status"] == "fresh_proposal"
        assert finding["technical_triage_verdict"] == "needs_review"
        assert finding["technical_triage_source"] == "fresh_deterministic_contextual_analysis"
        assert finding["disposition"] == "review_required"
        assert finding["technical_triage_human_approval_carried_forward"] is False


def test_low_severity_bandit_assert_in_acceptance_harness_routes_to_quality_control() -> None:
    source, _candidate_id = _synthetic_source("needs_review")
    register = {
        "findings": [
            {
                "finding_id": "NICO-B101-ACCEPTANCE",
                "lineage_status": "carried_forward_evidence_changed",
                "category": "static",
                "scanner": "bandit",
                "rule_id": "B101",
                "source_path": "scripts/mobile_restart_live_acceptance_v1.py",
                "line": 236,
                "severity": "low",
                "evidence_quality": "exact_source",
                "disposition": "review_required",
                "human_approval_status": "pending",
            }
        ],
        "totals": {"raw": 1},
    }

    result = apply_candidate_technical_triage(register, triage=source)
    finding = result["findings"][0]

    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["technical_triage_confidence"] == "high"
    assert finding["technical_triage_rationale_code"] == "assert_nonproduction_validation_harness"
    assert finding["production_test_development_scope"] == "test"
    assert finding["technical_review_required"] is False
    assert finding["review_routing_class"] == "QUALITY_CONTROL_ELIGIBLE"
    assert finding["disposition"] == "review_required"
    assert finding["human_approval_status"] == "pending"
    assert finding["technical_triage_client_delivery_allowed"] is False


def test_bandit_assert_in_production_or_generic_script_stays_fail_closed() -> None:
    source, _candidate_id = _synthetic_source("needs_review")
    register = {
        "findings": [
            {
                "finding_id": "NICO-B101-PRODUCTION",
                "lineage_status": "carried_forward_evidence_changed",
                "category": "static",
                "scanner": "bandit",
                "rule_id": "B101",
                "source_path": "nico/comprehensive_api_routes.py",
                "line": 236,
                "severity": "low",
                "evidence_quality": "exact_source",
                "disposition": "review_required",
            },
            {
                "finding_id": "NICO-B101-GENERIC-SCRIPT",
                "lineage_status": "carried_forward_evidence_changed",
                "category": "static",
                "scanner": "bandit",
                "rule_id": "B101",
                "source_path": "scripts/deploy.py",
                "line": 12,
                "severity": "low",
                "evidence_quality": "exact_source",
                "disposition": "review_required",
            },
            {
                "finding_id": "NICO-B101-EXPLICIT-PRODUCTION",
                "lineage_status": "newly_observed",
                "category": "static",
                "scanner": "bandit",
                "rule_id": "B101",
                "source_path": "scripts/production_acceptance.py",
                "line": 20,
                "severity": "low",
                "scope": "production",
                "evidence_quality": "exact_source",
                "disposition": "review_required",
            },
            {
                "finding_id": "NICO-B101-MEDIUM-SEVERITY",
                "lineage_status": "newly_observed",
                "category": "static",
                "scanner": "bandit",
                "rule_id": "B101",
                "source_path": "scripts/live_acceptance.py",
                "line": 30,
                "severity": "medium",
                "evidence_quality": "exact_source",
                "disposition": "review_required",
            },
        ],
        "totals": {"raw": 4},
    }

    result = apply_candidate_technical_triage(register, triage=source)

    for finding in result["findings"]:
        assert finding["technical_triage_verdict"] == "needs_review"
        assert finding["technical_review_required"] is True
        assert finding["review_routing_class"] == "HUMAN_TECHNICAL_REVIEW"
        assert finding["disposition"] == "review_required"
