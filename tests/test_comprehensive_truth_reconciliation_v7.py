from __future__ import annotations

from pathlib import Path

from nico import comprehensive_native_providers_v5 as providers
from nico.comprehensive_truth_reconciliation_v7 import (
    DISPOSITION_MODEL,
    SCORING_MODEL,
    WORKFLOW_MODEL,
    _augment_provider_result,
    complete_ci_operational_health,
    install_comprehensive_truth_reconciliation_v7,
    reconciled_summary_by_tool,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
COMMIT = "3c4352ae1873c547dd01406da833d2faedb5039b"


def _scan() -> dict:
    return {
        "finding_summary": {
            "by_tool": {
                "osv-scanner": {
                    "raw": 59,
                    "material": 0,
                    "review_required": 59,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                },
                "gitleaks": {
                    "raw": 17,
                    "material": 0,
                    "review_required": 17,
                    "approved_or_nonblocking": 1,
                    "excluded_test_only": 0,
                },
                "semgrep": {
                    "raw": 581,
                    "material": 0,
                    "review_required": 581,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                },
            }
        },
        "scanner_results": [
            {
                "scanner_name": "osv-scanner",
                "category": "dependency",
                "findings": [],
            },
            {
                "scanner_name": "gitleaks",
                "category": "secret",
                "findings": [],
            },
            {
                "scanner_name": "semgrep",
                "category": "static",
                "findings": [],
            },
        ],
    }


def test_overlapping_secret_summary_is_reconciled_to_mutually_exclusive_counts() -> None:
    summary = reconciled_summary_by_tool(_scan())

    assert summary["gitleaks"] == {
        "raw": 17,
        "material": 0,
        "review_required": 16,
        "approved_or_nonblocking": 1,
        "excluded_test_only": 0,
    }
    assert sum(
        summary["gitleaks"][key]
        for key in (
            "material",
            "review_required",
            "approved_or_nonblocking",
            "excluded_test_only",
        )
    ) == summary["gitleaks"]["raw"]


def test_canonical_register_preserves_657_raw_candidates_without_double_counting() -> None:
    install_comprehensive_truth_reconciliation_v7()

    register = providers.build_canonical_scanner_finding_register(_scan(), COMMIT)

    assert register["status"] == "complete"
    assert register["totals"]["raw"] == 657
    assert register["totals"]["review_required"] == 656
    assert register["totals"]["approved_or_nonblocking"] == 1
    assert register["totals"]["material"] == 0
    assert register["totals"]["excluded_test_only"] == 0
    assert register["disposition_sum"] == 657
    assert register["disposition_sum_matches_raw"] is True
    assert register["mutually_exclusive_dispositions_verified"] is True
    assert register["candidate_disposition_model"] == DISPOSITION_MODEL
    assert register["source_summary_adjustment_count"] == 1
    assert register["source_summary_reconciliation"]["gitleaks"][
        "source_review_required"
    ] == 17
    assert register["source_summary_reconciliation"]["gitleaks"][
        "reconciled_review_required"
    ] == 16

    for candidate in register["findings"]:
        assert candidate["candidate_id"] == candidate["finding_id"]
        assert candidate["normalized_rule_family"]
        assert candidate["duplicate_group_id"].startswith("NICO-DUPE-")
        assert candidate["batch_disposition_key"].startswith("NICO-BATCH-")
        assert len(candidate["evidence_digest_sha256"]) == 64
        assert candidate["raw_payload_retention_state"] == "count_only"
        assert candidate["reviewer_identity"] is None
        assert candidate["review_timestamp"] is None


def test_workflow_outcomes_account_for_all_100_runs() -> None:
    operational = complete_ci_operational_health(
        {
            "workflow_run_count": 100,
            "workflow_evidence": {
                "workflow_run_count": 100,
                "successful_runs": 85,
                "non_success_runs": 11,
            },
        }
    )

    assert operational["workflow_run_count"] == 100
    assert operational["successful_runs"] == 85
    assert operational["non_success_runs"] == 15
    assert operational["outcome_taxonomy"] == {
        "success": 85,
        "failure": 11,
        "cancelled": 0,
        "skipped": 0,
        "neutral": 0,
        "timed_out": 0,
        "action_required": 0,
        "queued_or_in_progress": 0,
        "unknown": 4,
    }
    assert sum(operational["outcome_taxonomy"].values()) == 100
    assert operational["unclassified_outcome_count"] == 4
    assert operational["outcome_count_parity_verified"] is True
    assert operational["outcome_taxonomy_model"] == WORKFLOW_MODEL
    assert operational["technical_configuration_score_affected"] is False


def test_score_contract_renders_zero_penalties_and_explicit_formula() -> None:
    result = _augment_provider_result(
        {
            "assessment": {
                "technical_score": 93,
                "score_contract": {
                    "technical_score": 93,
                    "candidate_volume_penalty": 4,
                    "missing_raw_payload_penalty": 0,
                    "incomplete_analyzer_penalty": 0,
                },
                "stage_summaries": [
                    {"stage_id": "functional_qa", "status": "unavailable"},
                    {"stage_id": "platform_parity", "status": "limited"},
                ],
                "canonical_scanner_finding_register": {
                    "disposition_sum_matches_raw": True,
                    "totals": {
                        "raw": 657,
                        "material": 0,
                        "review_required": 656,
                        "approved_or_nonblocking": 1,
                        "excluded_test_only": 0,
                        "count_only": 0,
                    },
                },
            }
        }
    )
    assessment = result["assessment"]
    contract = assessment["score_contract"]

    assert assessment["technical_score"] == 93
    assert assessment["evidence_adjusted_score"] == 89
    assert assessment["unavailable_note_count"] == 2
    assert assessment["source_loc"] == "not_available"
    assert contract["candidate_volume_penalty"] == 4
    assert contract["missing_raw_payload_penalty"] == 0
    assert contract["incomplete_analyzer_penalty"] == 0
    assert contract["other_assurance_penalty_total"] == 0
    assert contract["score_formula"] == "93 - 4 - 0 - 0 - 0 = 89"
    assert contract["scoring_model_version"] == SCORING_MODEL
    assert assessment["candidate_disposition"] == {
        "total_raw": 657,
        "confirmed_material": 0,
        "review_required": 656,
        "approved_nonblocking": 1,
        "excluded_nonproduction": 0,
        "count_only": 0,
        "mutually_exclusive": True,
        "model_version": DISPOSITION_MODEL,
    }


def test_runtime_keeps_truth_reconciliation_before_assurance_scoring() -> None:
    source = RUNTIME_BINDING.read_text(encoding="utf-8")

    reconciliation = source.index("install_comprehensive_truth_reconciliation_v7()")
    assurance = source.index("install_candidate_volume_assurance_v2()")
    assert reconciliation < assurance
    assert "RUNTIME_REVISION =" in source
    assert '"candidate_dispositions_mutually_exclusive": True' in source
    assert '"workflow_outcome_taxonomy_complete": True' in source
    assert '"blank_numeric_score_inputs_allowed": False' in source
