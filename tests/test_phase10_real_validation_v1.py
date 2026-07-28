from __future__ import annotations

from copy import deepcopy

import pytest

from nico.phase10_real_validation_v1 import (
    VERSION,
    Phase10ValidationError,
    aggregate_human_comparison,
    validate_phase10_bundle,
    validate_target,
)


SHA = "a" * 40
DIGEST = "b" * 64


def _artifact(name: str) -> dict:
    return {"path": f"artifacts/{name}", "sha256": DIGEST, "bytes": 100}


def _target(repository: str, run_id: str, bandit_status: str = "completed") -> dict:
    bandit = {
        "scanner": "bandit",
        "status": bandit_status,
        "commit_sha": SHA,
        "exit_code": 1,
        "finding_count": 2,
        "command": "bandit -r . -f json",
        "version": "1.7.9",
        "output_sha256": DIGEST,
        "json_parseable": True,
    }
    if bandit_status == "not_applicable":
        bandit = {"scanner": "bandit", "status": "not_applicable"}
    findings = [
        {
            "finding_id": f"{run_id}-F1",
            "title": "Authentication route permits broad exception handling",
            "location": "src/auth.py:10",
            "category": "reliability",
            "decision_meaning": "broad exceptions obscure authentication failures",
            "acceptance_criteria": ["Catch explicit authentication exceptions", "Add regression coverage"],
        }
    ]
    return {
        "repository": repository,
        "commit_sha": SHA,
        "run_id": run_id,
        "started_at": "2026-07-28T00:00:00Z",
        "completed_at": "2026-07-28T00:10:00Z",
        "artifacts": {
            "canonical_json": _artifact("report.json"),
            "findings_csv": _artifact("findings.csv"),
            "english_pdf": _artifact("report-en.pdf"),
            "spanish_pdf": _artifact("report-es.pdf"),
            "release_gate": _artifact("gate.json"),
            "package_manifest": _artifact("manifest.json"),
        },
        "filenames": {
            "english_pdf": f"nico-{run_id}-draft.pdf",
            "spanish_pdf": f"nico-{run_id}-borrador.pdf",
        },
        "findings": findings,
        "surface_finding_counts": {
            "executive": 1,
            "detailed": 1,
            "roadmap": 1,
            "backlog": 1,
            "remediation": 1,
            "json": 1,
            "csv": 1,
            "english_pdf": 1,
            "spanish_pdf": 1,
        },
        "scanner_records": [bandit],
        "production_path_integrated": True,
        "release_gate_passed": True,
        "client_delivery_state": "blocked_pending_human_approval",
    }


def _bundle() -> dict:
    return {
        "schema": VERSION,
        "targets": [
            _target("BoneManTGRM/NICO", "nico"),
            _target("example/python-service", "python"),
            _target("example/typescript-ui", "typescript", bandit_status="not_applicable"),
        ],
        "human_comparison": [
            {
                "kind": "automated_finding",
                "disposition": "confirmed",
                "reviewer": {"name": "Independent Reviewer", "role": "Senior Engineer", "independent": True},
                "severity_agreement": True,
                "remediation_useful": True,
            },
            {
                "kind": "automated_finding",
                "disposition": "false_positive",
                "reviewer": {"name": "Independent Reviewer", "role": "Senior Engineer", "independent": True},
                "severity_agreement": False,
                "remediation_useful": False,
            },
            {
                "kind": "human_only_finding",
                "disposition": "possible_false_negative",
                "reviewer": {"name": "Independent Reviewer", "role": "Senior Engineer", "independent": True},
                "severity_agreement": None,
                "remediation_useful": None,
            },
        ],
        "conclusion": {
            "recommendation": "release_with_limitations",
            "limitations": ["Validation applies only to the retained target revisions."],
        },
    }


def test_target_accepts_bandit_exit_one_as_completed_with_findings() -> None:
    result = validate_target(_target("BoneManTGRM/NICO", "nico"))
    assert result["valid"] is True
    assert result["finding_count"] == 1


def test_target_rejects_bandit_execution_failure() -> None:
    target = _target("BoneManTGRM/NICO", "nico")
    target["scanner_records"][0]["exit_code"] = 2
    with pytest.raises(Phase10ValidationError, match="exit code"):
        validate_target(target)


def test_target_rejects_wrong_bandit_revision() -> None:
    target = _target("BoneManTGRM/NICO", "nico")
    target["scanner_records"][0]["commit_sha"] = "c" * 40
    with pytest.raises(Phase10ValidationError, match="wrong revision"):
        validate_target(target)


def test_target_rejects_duplicate_terminal_filename_tokens() -> None:
    target = _target("BoneManTGRM/NICO", "nico")
    target["filenames"]["english_pdf"] = "report-final-pending-approval-final.pdf"
    with pytest.raises(Phase10ValidationError, match="terminal-state"):
        validate_target(target)


def test_target_rejects_surface_count_drift() -> None:
    target = _target("BoneManTGRM/NICO", "nico")
    target["surface_finding_counts"]["csv"] = 0
    with pytest.raises(Phase10ValidationError, match="same non-negative finding count"):
        validate_target(target)


def test_target_rejects_semantic_duplicate_findings() -> None:
    target = _target("BoneManTGRM/NICO", "nico")
    duplicate = deepcopy(target["findings"][0])
    duplicate["finding_id"] = "nico-F2"
    target["findings"].append(duplicate)
    for key in target["surface_finding_counts"]:
        target["surface_finding_counts"][key] = 2
    with pytest.raises(Phase10ValidationError, match="semantic duplicate"):
        validate_target(target)


def test_target_rejects_duplicate_acceptance_criteria() -> None:
    target = _target("BoneManTGRM/NICO", "nico")
    target["findings"][0]["acceptance_criteria"] = ["Add test", "  add   test  "]
    with pytest.raises(Phase10ValidationError, match="duplicate acceptance criteria"):
        validate_target(target)


def test_human_metrics_are_computed_without_overclaiming() -> None:
    metrics = aggregate_human_comparison(_bundle()["human_comparison"])
    assert metrics.precision == 0.5
    assert metrics.recall_proxy == 0.5
    assert metrics.severity_agreement == 0.5
    assert metrics.remediation_usefulness == 0.5


def test_bundle_requires_nico_and_two_unrelated_repositories() -> None:
    bundle = _bundle()
    bundle["targets"] = bundle["targets"][:2]
    with pytest.raises(Phase10ValidationError, match="at least three"):
        validate_phase10_bundle(bundle)


def test_bundle_requires_independent_human_review() -> None:
    bundle = _bundle()
    bundle["human_comparison"] = [
        {"kind": "automated_finding", "disposition": "not_independently_reviewed"}
    ]
    with pytest.raises(Phase10ValidationError, match="independent human review"):
        validate_phase10_bundle(bundle)


def test_complete_bundle_returns_hash_and_claim_boundary() -> None:
    result = validate_phase10_bundle(_bundle())
    assert result["valid"] is True
    assert result["target_count"] == 3
    assert len(result["validation_bundle_sha256"]) == 64
    assert "no consulting-replacement claim" in result["claim_boundary"]
