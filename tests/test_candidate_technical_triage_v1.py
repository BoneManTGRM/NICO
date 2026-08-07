from __future__ import annotations

from pathlib import Path

from nico.candidate_technical_triage_v1 import (
    SOURCE_CANDIDATE_COUNT,
    SOURCE_CATEGORY_VERDICT_COUNTS,
    SOURCE_COMMIT_SHA,
    SOURCE_REGISTER_SHA256,
    SOURCE_VERDICT_COUNTS,
    apply_candidate_technical_triage,
)


def _record(
    *,
    finding_id: str,
    category: str,
    rule_id: str,
    prior_candidate_id: str | None,
) -> dict:
    record = {
        "finding_id": finding_id,
        "category": category,
        "rule_id": rule_id,
        "disposition": "review_required",
        "human_review_required": True,
        "occurrence_count": 1,
    }
    if prior_candidate_id:
        record["prior_candidate_id"] = prior_candidate_id
        record["prior_target_commit_sha"] = SOURCE_COMMIT_SHA
    return record


def test_retained_technical_triage_contract_matches_completed_662_review() -> None:
    assert SOURCE_COMMIT_SHA == "9c876ba4e3e9bb152de52567232038e52a6bbb3e"
    assert SOURCE_REGISTER_SHA256 == "93f35cf18dd808e8c5a2c1a4fbe5fa430971550a08b419b6cc2445ca08c8d8be"
    assert SOURCE_CANDIDATE_COUNT == 662
    assert SOURCE_VERDICT_COUNTS == {"not_actionable": 624, "needs_review": 38}
    assert SOURCE_CATEGORY_VERDICT_COUNTS == {
        "static": {"not_actionable": 586},
        "secret": {"not_actionable": 17},
        "dependency": {"not_actionable": 21, "needs_review": 38},
    }


def test_technical_triage_overlays_proposals_without_mutating_canonical_dispositions() -> None:
    register = {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": "complete",
        "exact_commit_sha": "b" * 40,
        "summary_by_category": {
            "static": {"raw": 1, "review_required": 1},
            "secret": {"raw": 1, "review_required": 1},
            "dependency": {"raw": 2, "review_required": 2},
        },
        "totals": {"raw": 5, "review_required": 5},
        "findings": [
            _record(
                finding_id="STATIC",
                category="static",
                rule_id="B101",
                prior_candidate_id="NICO-STATIC-OLD",
            ),
            _record(
                finding_id="SECRET",
                category="secret",
                rule_id="secret",
                prior_candidate_id="NICO-SECRET-OLD",
            ),
            _record(
                finding_id="DEP-BUILD",
                category="dependency",
                rule_id="PYSEC-2026-196",
                prior_candidate_id="NICO-DEPENDENCY-OLD-1",
            ),
            _record(
                finding_id="DEP-REVIEW",
                category="dependency",
                rule_id="PYSEC-2026-3494",
                prior_candidate_id="NICO-DEPENDENCY-OLD-2",
            ),
            _record(
                finding_id="CURRENT-ONLY",
                category="static",
                rule_id="B101",
                prior_candidate_id=None,
            ),
        ],
    }

    result = apply_candidate_technical_triage(register)
    static, secret, dependency_build, dependency_review, current_only = result["findings"]

    assert static["technical_triage_verdict"] == "not_actionable"
    assert static["technical_triage_proposed_system_disposition"] == "approved_or_nonblocking"
    assert static["disposition"] == "review_required"
    assert static["human_review_required"] is True

    assert secret["technical_triage_verdict"] == "not_actionable"
    assert secret["technical_triage_proposed_system_disposition"] == "excluded_test_only"
    assert secret["disposition"] == "review_required"

    assert dependency_build["technical_triage_verdict"] == "not_actionable"
    assert dependency_build["technical_triage_rationale_code"] == "build_tool_version_not_product_runtime_dependency"
    assert dependency_build["disposition"] == "review_required"

    assert dependency_review["technical_triage_verdict"] == "needs_review"
    assert dependency_review["technical_triage_proposed_system_disposition"] == "review_required"
    assert dependency_review["disposition"] == "review_required"

    assert current_only["technical_triage_status"] == "pending_current_only"
    assert "technical_triage_verdict" not in current_only

    summary = result["technical_candidate_triage"]
    assert summary["matched_current_candidate_records"] == 4
    assert summary["imported_not_actionable_records"] == 3
    assert summary["imported_needs_review_records"] == 1
    assert summary["current_only_candidate_records"] == 1
    assert summary["unmapped_prior_candidate_records"] == 0
    assert summary["canonical_dispositions_mutated"] is False
    assert summary["score_effect"] == "none_from_import_alone"
    assert summary["human_approval_status"] == "pending"
    assert summary["client_delivery_allowed"] is False
    assert result["summary_by_category"] == register["summary_by_category"]


def test_unknown_prior_rule_fails_closed_instead_of_inventing_a_verdict() -> None:
    register = {
        "findings": [
            _record(
                finding_id="UNKNOWN-PRIOR",
                category="static",
                rule_id="B999",
                prior_candidate_id="NICO-UNKNOWN-OLD",
            )
        ]
    }

    result = apply_candidate_technical_triage(register)
    finding = result["findings"][0]
    summary = result["technical_candidate_triage"]

    assert finding["technical_triage_status"] == "pending_unmapped_prior"
    assert "technical_triage_verdict" not in finding
    assert summary["unmapped_prior_candidate_records"] == 1
    assert summary["canonical_dispositions_mutated"] is False


def test_runtime_patch_imports_lineage_before_technical_triage() -> None:
    source = Path("nico/candidate_lineage_runtime_patch_v1.py").read_text(encoding="utf-8")

    lineage = source.index("lineage_register = apply_candidate_lineage(current_builder(scan, commit_sha))")
    technical = source.index("return apply_candidate_technical_triage(lineage_register)")
    assert lineage < technical
    assert '"technical_triage_mutates_canonical_disposition": False' in source
    assert '"human_approval_may_carry_forward": False' in source
    assert '"client_delivery_allowed": False' in source


def test_dependency_candidates_have_explicit_current_remediation_pins() -> None:
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()

    assert "pillow==12.3.0" in requirements
    assert "idna==3.18" in requirements
