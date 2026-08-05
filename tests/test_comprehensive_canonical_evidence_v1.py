from __future__ import annotations

from copy import deepcopy

import pytest

from nico.comprehensive_canonical_evidence_v1 import (
    DIGEST_KEY,
    MANIFEST_KEY,
    assert_canonical_evidence_manifest,
    attach_canonical_evidence_manifest,
    build_canonical_evidence_manifest,
    validate_canonical_evidence_manifest,
)


def _canonical() -> dict:
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "d" * 40,
            "run_id": "comprun_fixture",
            "evidence_ledger_id": "ledger_fixture",
        },
        "scanner_execution_records": [
            {
                "scanner_name": "bandit",
                "completed": True,
                "exact_commit_match": True,
                "artifact_hash": "a" * 64,
            }
        ],
        "review_candidate_summary": {
            "raw_total": 3,
            "review_required_total": 3,
            "confirmed_material_total": 0,
        },
        "canonical_findings": [
            {
                "finding_id": "NICO-FINDING-1",
                "location": "nico/example.py:10",
                "priority": "P1",
            }
        ],
        "assessment": {
            "technical_score": 93,
            "canonical_evidence_adjusted_score": 89,
            "score_contract": {
                "scoring_model_version": "fixture.v1",
                "candidate_volume_penalty": 4,
            },
            "score_reconciliation": {
                "technical_score": 93,
                "canonical_evidence_adjusted_score": 89,
            },
            "sections": [
                {"id": "code_audit", "presented_score": 96},
            ],
            "human_evidence_summary": {
                "functional_qa": {"status": "not_assessed"},
            },
        },
        "stage_summaries": [
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "status": "complete",
                "evidence": ["93 - 4 - 0 - 0 - 0 = 89"],
            }
        ],
        "ci_operational_context": {
            "workflow_runs_observed": 100,
            "successful_runs": 76,
            "deployments_observed": 10,
            "successful_deployments": 7,
        },
        "limitations": ["Human review required."],
        "lifecycle": {
            "automated_status": "automated_draft",
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
        "artifact_manifest": {
            "manifest_id": "manifest_fixture",
            "findings_csv_sha256": "b" * 64,
        },
    }


def test_manifest_binds_one_canonical_root_without_mutating_source() -> None:
    source = _canonical()
    original = deepcopy(source)

    attached = attach_canonical_evidence_manifest(source, require_complete=True)

    assert source == original
    assert attached[MANIFEST_KEY]["authoritative_object"] == "canonical_json"
    assert attached[MANIFEST_KEY]["manifest_supplies_no_alternative_truth_values"] is True
    assert attached[DIGEST_KEY] == attached[MANIFEST_KEY]["run_subject_sha256"]
    assert validate_canonical_evidence_manifest(
        attached,
        require_complete=True,
    )["status"] == "valid"


def test_manifest_is_deterministic_across_mapping_order() -> None:
    source = _canonical()
    reversed_source = dict(reversed(list(source.items())))

    first = build_canonical_evidence_manifest(source, require_complete=True)
    second = build_canonical_evidence_manifest(reversed_source, require_complete=True)

    assert first["run_subject_sha256"] == second["run_subject_sha256"]
    assert first["technical_subject_sha256"] == second["technical_subject_sha256"]
    assert first["bindings"] == second["bindings"]


def test_bound_truth_mutation_fails_with_field_level_diagnostics() -> None:
    attached = attach_canonical_evidence_manifest(_canonical(), require_complete=True)
    attached["assessment"]["technical_score"] = 92

    validation = validate_canonical_evidence_manifest(
        attached,
        require_complete=True,
    )

    assert validation["status"] == "invalid"
    assert "canonical_evidence_manifest.run_subject_sha256:mismatch" in validation[
        "validation_errors"
    ]
    assert (
        "canonical_evidence_manifest.bindings.scoring_evidence.sha256:mismatch"
        in validation["validation_errors"]
    )
    with pytest.raises(ValueError, match="canonical_evidence_invalid"):
        assert_canonical_evidence_manifest(attached, require_complete=True)


def test_rendered_payloads_do_not_change_evidence_subject() -> None:
    source = _canonical()
    source["markdown"] = "first presentation"
    source["html"] = "<p>first presentation</p>"
    source["pdf_base64"] = "Zmlyc3Q="
    first = build_canonical_evidence_manifest(source)

    source["markdown"] = "second presentation"
    source["html"] = "<p>second presentation</p>"
    source["pdf_base64"] = "c2Vjb25k"
    second = build_canonical_evidence_manifest(source)

    assert first["run_subject_sha256"] == second["run_subject_sha256"]
    assert first["technical_subject_sha256"] == second["technical_subject_sha256"]


def test_technical_digest_is_stable_across_run_and_operational_observation_changes() -> None:
    first_source = _canonical()
    second_source = deepcopy(first_source)
    second_source["identity"]["run_id"] = "comprun_second"
    second_source["identity"]["evidence_ledger_id"] = "ledger_second"
    second_source["ci_operational_context"]["successful_runs"] = 77

    first = build_canonical_evidence_manifest(first_source)
    second = build_canonical_evidence_manifest(second_source)

    assert first["run_subject_sha256"] != second["run_subject_sha256"]
    assert first["technical_subject_sha256"] == second["technical_subject_sha256"]
    assert (
        first["mutable_operational_subject_sha256"]
        != second["mutable_operational_subject_sha256"]
    )


def test_strict_validation_reports_missing_identity_and_binding_paths() -> None:
    manifest = build_canonical_evidence_manifest({}, require_complete=True)

    assert manifest["validation_status"] == "invalid"
    assert "identity.repository:required" in manifest["validation_errors"]
    assert "identity.commit_sha:required" in manifest["validation_errors"]
    assert "bindings.scanner_evidence:required" in manifest["validation_errors"]
    assert "bindings.scoring_evidence:required" in manifest["validation_errors"]


def test_invalid_commit_identity_is_rejected_even_in_non_strict_mode() -> None:
    source = _canonical()
    source["identity"]["commit_sha"] = "not-a-sha"
    attached = attach_canonical_evidence_manifest(source)

    validation = validate_canonical_evidence_manifest(attached)

    assert validation["status"] == "invalid"
    assert "identity.commit_sha:invalid_sha40" in validation["validation_errors"]
