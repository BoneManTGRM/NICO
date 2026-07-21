from __future__ import annotations

import json
from pathlib import Path

import pytest

from nico.hardening_acceptance import (
    HardeningAcceptanceError,
    StabilityThresholds,
    acceptance_mapping,
    evaluate_two_pass_acceptance,
)
from nico.post_release_hardening import HardeningScenario


def _evidence(
    path: Path,
    *,
    sha: str = "a" * 40,
    runtime_multiplier: float = 1.0,
    changed_truth: bool = False,
    missing_scenario: str = "",
    verdict_status: str = "passed",
) -> Path:
    observations = []
    for index, scenario in enumerate(HardeningScenario, start=1):
        if scenario.value == missing_scenario:
            continue
        adverse = scenario in {
            HardeningScenario.PARTIAL_ACCESS,
            HardeningScenario.TIMEOUT,
            HardeningScenario.PROVIDER_OUTAGE,
            HardeningScenario.REVOKED_APPROVAL,
            HardeningScenario.INTERRUPTED_RUN,
        }
        evidence = {}
        if scenario is HardeningScenario.REVOKED_APPROVAL:
            evidence = {"approval_revoked": True, "delivery_available": False}
        elif scenario is HardeningScenario.INTERRUPTED_RUN:
            evidence = {"restart_identity_preserved": True, "idempotent_continuation": True}
        elif scenario is HardeningScenario.ACCESSIBILITY:
            evidence = {
                "keyboard": True,
                "screen_reader": True,
                "contrast": True,
                "reduced_motion": True,
                "semantic_headings": True,
                "focus_order": True,
            }
        elif scenario is HardeningScenario.PSEUDO_LOCALIZATION:
            evidence = {
                "route_parity": True,
                "translation_key_parity": True,
                "long_string_layout": True,
                "no_untranslated_copy": True,
            }
        if changed_truth and scenario is HardeningScenario.CLEAN:
            evidence = {"unexpected_change": True}
        observations.append(
            {
                "scenario": scenario.value,
                "exact_sha": sha,
                "status": "blocked" if adverse else "passed",
                "terminal": not adverse,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "runtime_seconds": index * runtime_multiplier,
                "peak_memory_mb": index * 10 * runtime_multiplier,
                "artifact_bytes": index * 1000 * runtime_multiplier,
                "evidence": evidence,
            }
        )
    payload = {
        "artifact_schema": "nico.post_release_hardening.v1",
        "expected_sha": sha,
        "observations": observations,
        "verdict": {
            "status": verdict_status,
            "expected_sha": sha,
            "required_scenarios": [item.value for item in HardeningScenario],
            "missing_scenarios": [],
            "duplicate_scenarios": [],
            "verdicts": [],
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_two_stable_passes_are_accepted(tmp_path: Path) -> None:
    one = _evidence(tmp_path / "one.json")
    two = _evidence(tmp_path / "two.json", runtime_multiplier=1.05)

    result = evaluate_two_pass_acceptance(one, two, expected_sha="a" * 40)
    payload = acceptance_mapping(result)

    assert result.accepted is True
    assert result.issues == ()
    assert result.pass_one_fingerprint == result.pass_two_fingerprint
    assert payload["status"] == "passed"
    assert payload["passes_completed"] == 2
    assert len(payload["scenarios"]) == len(HardeningScenario)
    assert all(item["passed"] is True for item in payload["scenarios"].values())
    assert payload["client_delivery_allowed"] is False


def test_truth_change_between_passes_fails_even_when_each_verdict_passed(tmp_path: Path) -> None:
    one = _evidence(tmp_path / "one.json")
    two = _evidence(tmp_path / "two.json", changed_truth=True)

    result = evaluate_two_pass_acceptance(one, two, expected_sha="a" * 40)
    assert result.accepted is False
    assert "hardening_truth_fingerprint_mismatch" in result.issues


def test_runtime_memory_and_artifact_regressions_are_bounded(tmp_path: Path) -> None:
    one = _evidence(tmp_path / "one.json")
    two = _evidence(tmp_path / "two.json", runtime_multiplier=2.0)

    result = evaluate_two_pass_acceptance(
        one,
        two,
        expected_sha="a" * 40,
        thresholds=StabilityThresholds(
            max_runtime_regression_ratio=0.25,
            max_memory_regression_ratio=0.25,
            max_artifact_size_regression_ratio=0.10,
        ),
    )
    assert result.accepted is False
    assert any("scenario_runtime_regression_exceeded" in issue for issue in result.issues)
    assert any("scenario_memory_regression_exceeded" in issue for issue in result.issues)
    assert any("scenario_artifact_size_regression_exceeded" in issue for issue in result.issues)


def test_expected_sha_mismatch_fails(tmp_path: Path) -> None:
    one = _evidence(tmp_path / "one.json", sha="a" * 40)
    two = _evidence(tmp_path / "two.json", sha="b" * 40)

    result = evaluate_two_pass_acceptance(one, two, expected_sha="a" * 40)
    assert result.accepted is False
    assert "hardening_two_pass_sha_mismatch" in result.issues
    assert "hardening_expected_sha_mismatch" in result.issues


def test_incomplete_or_unpassed_evidence_is_rejected_before_acceptance(tmp_path: Path) -> None:
    complete = _evidence(tmp_path / "complete.json")
    incomplete = _evidence(
        tmp_path / "incomplete.json",
        missing_scenario=HardeningScenario.ACCESSIBILITY.value,
    )
    with pytest.raises(HardeningAcceptanceError, match="scenario_set_incomplete"):
        evaluate_two_pass_acceptance(complete, incomplete, expected_sha="a" * 40)

    failed = _evidence(tmp_path / "failed.json", verdict_status="failed")
    with pytest.raises(HardeningAcceptanceError, match="verdict_not_passed"):
        evaluate_two_pass_acceptance(complete, failed, expected_sha="a" * 40)


def test_invalid_stability_threshold_is_rejected(tmp_path: Path) -> None:
    one = _evidence(tmp_path / "one.json")
    two = _evidence(tmp_path / "two.json")
    with pytest.raises(ValueError, match="stability_threshold_invalid"):
        evaluate_two_pass_acceptance(
            one,
            two,
            thresholds=StabilityThresholds(max_runtime_regression_ratio=-1),
        )
