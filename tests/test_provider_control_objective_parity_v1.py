from __future__ import annotations

import pytest

from nico import comprehensive_native_providers_v3 as scoring
from nico.provider_control_objective_parity_v1 import (
    analyze_provider_neutral_workflow_controls,
    install_provider_control_objective_parity,
    provider_neutral_immutable_ci_score,
)


@pytest.mark.parametrize(
    "path,text,expected_true",
    (
        (
            ".gitlab-ci.yml",
            """
            stages: [test, build, deploy]
            cache:\n  paths: [.cache/]
            test:\n  script: [pytest, ruff check .]\n  timeout: 20m
            build:\n  script: [npm run build]\n  artifacts:\n    paths: [dist/]
            security:\n  script: [semgrep --config auto]
            deploy:\n  script: [kubectl apply -f k8s/]\n  environment: production\n  when: manual
            """,
            {"cache", "timeout", "artifact_upload", "environment_gate", "test_command", "lint_command", "build_command", "security_command", "deployment_command"},
        ),
        (
            "bitbucket-pipelines.yml",
            """
            definitions:\n  caches:\n    npm: ~/.npm
            pipelines:\n  default:\n    - parallel:\n      - step:\n          script:\n            - npm test\n            - npm run lint\n            - npm run build\n            - npm audit
      - step:\n          script:\n            - vercel deploy
            """,
            {"cache", "matrix", "test_command", "lint_command", "build_command", "security_command", "deployment_command"},
        ),
        (
            "azure-pipelines.yml",
            """
            strategy:\n  matrix:\n    py311:\n      python.version: '3.11'
            jobs:\n- job: test\n  timeoutInMinutes: 30\n  steps:\n  - script: pytest\n  - script: ruff check .\n  - task: Cache@2\n  - task: PublishPipelineArtifact@1
            - deployment: production\n  environment: prod\n  strategy:\n    runOnce:\n      deploy:\n        steps:\n        - script: az webapp deploy
            """,
            {"cache", "timeout", "matrix", "artifact_upload", "environment_gate", "test_command", "lint_command", "deployment_command"},
        ),
    ),
)
def test_hosted_ci_files_map_into_same_canonical_control_vocabulary(
    path: str,
    text: str,
    expected_true: set[str],
) -> None:
    result = analyze_provider_neutral_workflow_controls({path: text})

    assert result["workflow_configuration_assessed"] is True
    assert set(result["configuration_controls"]) == set(scoring._IMMUTABLE_CONTROL_FIELDS)
    assert set(result["configuration_control_states"]) == set(scoring._IMMUTABLE_CONTROL_FIELDS)
    assert all(state == "assessed" for state in result["configuration_control_states"].values())
    assert expected_true <= {
        key for key, value in result["configuration_controls"].items() if value is True
    }


def test_missing_hosted_workflow_is_not_converted_into_failed_detail_controls() -> None:
    result = analyze_provider_neutral_workflow_controls({"src/app.py": "print('ok')"})

    assert result["workflow_configuration_assessed"] is False
    assert result["configuration_controls"] == {}
    assert all(
        state == "not_assessed"
        for state in result["configuration_control_states"].values()
    )


def _workflow(*, permission_assessed: bool, permission_value, history: tuple[int, int]) -> dict:
    controls = {name: False for name in scoring._IMMUTABLE_CONTROL_FIELDS}
    controls.update(
        {
            "cache": True,
            "timeout": True,
            "artifact_upload": True,
            "test_command": True,
            "lint_command": True,
            "build_command": True,
            "security_command": True,
            "deployment_command": True,
        }
    )
    return {
        "workflow_file_count": 1,
        "workflow_configuration_assessed": True,
        "workflow_configuration_snapshot_sha": "a" * 40,
        "permission_control_assessed": permission_assessed,
        "permission_control_state": "assessed" if permission_assessed else "not_assessed",
        "explicit_permissions_present": permission_value,
        "configuration_controls": controls,
        "configuration_control_states": {
            name: "assessed" for name in scoring._IMMUTABLE_CONTROL_FIELDS
        },
        "successful_runs": history[0],
        "non_success_runs": history[1],
        "jobs_observed": history[0] + history[1],
        "deployments_observed": history[0],
    }


def test_unassessed_permission_capability_is_neither_passed_nor_failed() -> None:
    score, evidence, findings, contract = provider_neutral_immutable_ci_score(
        _workflow(permission_assessed=False, permission_value=None, history=(8, 2)),
        "a" * 40,
    )

    assert 0 <= score <= 100
    assert contract["objective_states"]["explicit_permissions_present"] == "not_assessed"
    assert contract["score_inputs"]["explicit_permissions_present"] is None
    assert "explicit_permissions_present" in contract["not_assessed_control_objectives"]
    assert contract["unavailable_or_unassessed_capability_treated_as_failed"] is False
    assert contract["not_assessed_capability_treated_as_passed"] is False
    assert not any("permission boundaries were assessed and not proven" in item for item in findings)
    assert any("no pass/fail claim" in item for item in evidence)


def test_assessed_missing_permission_boundary_remains_a_real_failed_control() -> None:
    unknown_score, _, unknown_findings, _ = provider_neutral_immutable_ci_score(
        _workflow(permission_assessed=False, permission_value=None, history=(8, 2)),
        "a" * 40,
    )
    failed_score, _, failed_findings, failed_contract = provider_neutral_immutable_ci_score(
        _workflow(permission_assessed=True, permission_value=False, history=(8, 2)),
        "a" * 40,
    )

    assert failed_contract["objective_states"]["explicit_permissions_present"] == "failed"
    assert failed_score < unknown_score
    assert not unknown_findings
    assert any("permission boundaries were assessed and not proven" in item for item in failed_findings)


def test_mutable_provider_history_cannot_change_immutable_ci_score() -> None:
    clean_history = _workflow(
        permission_assessed=False,
        permission_value=None,
        history=(12, 0),
    )
    noisy_history = _workflow(
        permission_assessed=False,
        permission_value=None,
        history=(1, 40),
    )

    clean_score, _, clean_findings, clean_contract = provider_neutral_immutable_ci_score(
        clean_history,
        "a" * 40,
    )
    noisy_score, _, noisy_findings, noisy_contract = provider_neutral_immutable_ci_score(
        noisy_history,
        "a" * 40,
    )

    assert clean_score == noisy_score
    assert clean_findings == noisy_findings
    assert clean_contract["mutable_operational_history_affects_technical_score"] is False
    assert noisy_contract["mutable_operational_history_affects_technical_score"] is False
    assert clean_contract["operational_trend"] != noisy_contract["operational_trend"]
    assert clean_contract["operational_trend"]["score_effect"] == "none"
    assert noisy_contract["operational_trend"]["score_effect"] == "none"


def test_installation_binds_hosted_capture_and_authoritative_immutable_scorer() -> None:
    status = install_provider_control_objective_parity()

    assert status["bound"] is True
    assert status["hosted_profile_control_capture_bound"] is True
    assert status["hosted_repository_evidence_control_binding_bound"] is True
    assert status["provider_neutral_control_objectives"] is True
    assert status["unavailable_or_unassessed_capability_treated_as_failed"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
