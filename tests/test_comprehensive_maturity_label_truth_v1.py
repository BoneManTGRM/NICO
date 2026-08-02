from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_canonical_report_source_v1 import (
    build_canonical_report_source,
)
from nico.comprehensive_maturity_label_truth_v1 import (
    derive_canonical_maturity_label,
    synchronize_maturity_label_truth,
)

SHA = "a" * 40


def _stages() -> dict:
    return {
        "authorization_and_scope": {
            "status": "complete",
            "evidence": {
                "authorized": True,
                "reviewer_seniority_level": "Senior",
            },
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "assessment": {
                "technical_score": 93,
                "canonical_evidence_adjusted_score": 91,
                "maturity_level": "Senior",
                "maturity_signal": {
                    "level": "Senior",
                    "label": "Senior",
                    "score": 93,
                    "technical_score": 93,
                    "canonical_evidence_adjusted_score": 91,
                },
                "sections": [],
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "client_readiness_contract": {
                "maturity_label": "Exceptional",
                "analyzer_execution_coverage": 100,
                "coverage_denominator": 9,
            },
            "evidence": {
                "legacy_alias": "maturity_level: Senior",
                "legacy_label": "maturity label = Senior",
                "unrelated": "Senior engineering reviewer required",
            },
        },
        "decision_report_generation": {
            "status": "complete",
            "evidence": {
                "flattened": [
                    "assessment.maturity_level: Senior",
                    "reviewer_seniority_level: Senior",
                ]
            },
        },
    }


def _context() -> dict:
    return {
        "run_id": "comprun_maturity_truth",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": SHA,
        "evidence_ledger_id": "ledger_maturity_truth",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": _stages(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_client_readiness_contract_is_authoritative_maturity_taxonomy() -> None:
    label, source = derive_canonical_maturity_label(_stages())
    assert label == "Exceptional"
    assert source == "scoring.client_readiness_contract.maturity_label"


def test_explicit_stale_maturity_aliases_are_replaced_before_flattening() -> None:
    source = _stages()
    original = deepcopy(source)
    synchronized, manifest = synchronize_maturity_label_truth(source)

    assessment = synchronized["evidence_reconciliation_and_scoring"]["assessment"]
    evidence = synchronized["evidence_reconciliation_and_scoring"]["evidence"]
    flattened = synchronized["decision_report_generation"]["evidence"]["flattened"]

    assert assessment["maturity_level"] == "Exceptional"
    assert assessment["maturity_signal"]["level"] == "Exceptional"
    assert assessment["maturity_signal"]["label"] == "Exceptional"
    assert evidence["legacy_alias"] == "maturity_level: Exceptional"
    assert evidence["legacy_label"] == "maturity label = Exceptional"
    assert flattened[0] == "assessment.maturity_level: Exceptional"
    assert "maturity_level: Senior" not in repr(synchronized)
    assert manifest["canonical_label"] == "Exceptional"
    assert manifest["replacement_count"] >= 6
    assert manifest["scores_changed"] is False
    assert source == original


def test_unrelated_seniority_and_free_text_are_preserved() -> None:
    synchronized, manifest = synchronize_maturity_label_truth(_stages())
    authorization = synchronized["authorization_and_scope"]["evidence"]
    scoring_evidence = synchronized["evidence_reconciliation_and_scoring"]["evidence"]
    flattened = synchronized["decision_report_generation"]["evidence"]["flattened"]

    assert authorization["reviewer_seniority_level"] == "Senior"
    assert scoring_evidence["unrelated"] == "Senior engineering reviewer required"
    assert flattened[1] == "reviewer_seniority_level: Senior"
    assert manifest["unrelated_seniority_preserved"] is True


def test_canonical_report_source_contains_no_conflicting_maturity_label() -> None:
    source = build_canonical_report_source(_context())

    assert source["status"] == "complete"
    assert source["maturity_label_truth"]["canonical_label"] == "Exceptional"
    assert source["report_package"]["maturity_label_truth"]["canonical_label"] == "Exceptional"
    assert source["canonical_report"]["maturity_label_truth"]["canonical_label"] == "Exceptional"
    combined = repr(
        {
            "assessment": source["assessment"],
            "stage_summaries": source["stage_summaries"],
            "canonical": source["canonical_report"],
        }
    )
    assert "maturity_level: Senior" not in combined
    assert "maturity_level: Exceptional" in combined
    assert source["human_review_required"] is True
    assert source["client_delivery_allowed"] is False


def test_missing_canonical_maturity_label_remains_fail_closed_and_unchanged() -> None:
    stages = {"authorization_and_scope": {"status": "complete", "evidence": {"authorized": True}}}
    synchronized, manifest = synchronize_maturity_label_truth(stages)

    assert synchronized == stages
    assert manifest["status"] == "not_applied"
    assert manifest["reason"] == "canonical_maturity_label_unavailable"
    assert manifest["human_review_required"] is True
    assert manifest["client_delivery_allowed"] is False
