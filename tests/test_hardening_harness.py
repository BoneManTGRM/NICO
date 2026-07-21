from __future__ import annotations

import json
from pathlib import Path

from nico.hardening_harness import (
    HardeningCase,
    accessibility_evidence,
    load_observations,
    pseudo_localize,
    run_case,
    run_hardening_matrix,
    write_hardening_evidence,
)
from nico.post_release_hardening import HardeningScenario


def _success_payload(sha: str, *, evidence: dict | None = None) -> dict:
    return {
        "exact_sha": sha,
        "status": "passed",
        "terminal": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "markdown": "# Report",
        "html": "<h1>Report</h1>",
        "pdf": b"%PDF-test",
        "json": {"status": "passed"},
        "evidence": evidence or {},
    }


def test_case_measures_runtime_memory_and_artifacts() -> None:
    sha = "a" * 40
    observation = run_case(
        HardeningCase(HardeningScenario.CLEAN, lambda: _success_payload(sha)),
        expected_sha=sha,
    )
    assert observation.status == "passed"
    assert observation.runtime_seconds >= 0
    assert observation.peak_memory_mb >= 0
    assert observation.artifact_bytes > 0
    assert observation.client_delivery_allowed is False


def test_runner_exception_becomes_fail_closed_observation() -> None:
    def explode():
        raise RuntimeError("fixture_failed")

    observation = run_case(
        HardeningCase(HardeningScenario.PROVIDER_OUTAGE, explode),
        expected_sha="a" * 40,
    )
    assert observation.status == "failed"
    assert observation.terminal is False
    assert observation.human_review_required is True
    assert observation.client_delivery_allowed is False


def test_complete_matrix_writes_and_loads_immutable_json(tmp_path: Path) -> None:
    sha = "a" * 40
    cases = []
    for scenario in HardeningScenario:
        if scenario in {
            HardeningScenario.PARTIAL_ACCESS,
            HardeningScenario.TIMEOUT,
            HardeningScenario.PROVIDER_OUTAGE,
            HardeningScenario.REVOKED_APPROVAL,
            HardeningScenario.INTERRUPTED_RUN,
        }:
            evidence = {}
            if scenario is HardeningScenario.REVOKED_APPROVAL:
                evidence = {"approval_revoked": True, "delivery_available": False}
            if scenario is HardeningScenario.INTERRUPTED_RUN:
                evidence = {"restart_identity_preserved": True, "idempotent_continuation": True}
            cases.append(
                HardeningCase(
                    scenario,
                    lambda scenario=scenario, evidence=evidence: {
                        "exact_sha": sha,
                        "status": "blocked" if scenario is not HardeningScenario.INTERRUPTED_RUN else "interrupted",
                        "terminal": False,
                        "human_review_required": True,
                        "client_delivery_allowed": False,
                        "evidence": evidence,
                    },
                )
            )
        elif scenario is HardeningScenario.ACCESSIBILITY:
            cases.append(
                HardeningCase(
                    scenario,
                    lambda: _success_payload(
                        sha,
                        evidence=accessibility_evidence(
                            keyboard=True,
                            screen_reader=True,
                            contrast=True,
                            reduced_motion=True,
                            semantic_headings=True,
                            focus_order=True,
                        ),
                    ),
                )
            )
        elif scenario is HardeningScenario.PSEUDO_LOCALIZATION:
            cases.append(
                HardeningCase(
                    scenario,
                    lambda: _success_payload(
                        sha,
                        evidence={
                            "route_parity": True,
                            "translation_key_parity": True,
                            "long_string_layout": True,
                            "no_untranslated_copy": True,
                        },
                    ),
                )
            )
        else:
            cases.append(HardeningCase(scenario, lambda: _success_payload(sha)))

    run = run_hardening_matrix(cases, expected_sha=sha)
    assert run.verdict["status"] == "passed"

    path = write_hardening_evidence(run, tmp_path / "hardening.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["verdict"]["status"] == "passed"
    loaded_sha, loaded = load_observations(path)
    assert loaded_sha == sha
    assert len(loaded) == len(HardeningScenario)


def test_pseudo_localization_expands_and_marks_copy() -> None:
    source = "Start assessment"
    rendered = pseudo_localize(source)
    assert rendered.startswith("⟦")
    assert rendered.endswith("⟧")
    assert len(rendered) > len(source)
    assert "á" in rendered
