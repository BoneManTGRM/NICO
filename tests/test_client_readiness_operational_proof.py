from __future__ import annotations

from copy import deepcopy

from nico.client_readiness_operational_proof import (
    REQUIRED_JOURNEYS,
    build_operational_proof_bundle,
    operational_proof_gate,
)


SHA = "a" * 40
DIGEST = "b" * 64


def _evidence(evidence_id: str, **extra) -> dict:
    return {
        "evidence_id": evidence_id,
        "release_sha": SHA,
        "environment": "production",
        "observed_at": "2026-08-05T18:00:00Z",
        "artifact_sha256": DIGEST,
        **extra,
    }


def _valid_kwargs() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "release_sha": SHA,
        "frontend_deployment": _evidence("frontend", deployed_sha=SHA, status="successful"),
        "backend_deployment": _evidence("backend", deployed_sha=SHA, status="successful"),
        "required_checks": [
            _evidence("check-ci", name="NICO CI", conclusion="success", required=True),
            _evidence("check-codeql", name="CodeQL", conclusion="success", required=True),
        ],
        "journeys": [
            _evidence(f"journey-{name}", journey=name, status="passed")
            for name in sorted(REQUIRED_JOURNEYS)
        ],
        "deployments": [
            _evidence("deployment-1", deployment_id="deployment-1", classification="successful", classification_basis="Exact production release accepted."),
            _evidence("deployment-2", deployment_id="deployment-2", classification="canceled_or_superseded", classification_basis="A newer release superseded the run."),
        ],
        "rollback": _evidence(
            "rollback-1",
            procedure="Redeploy the last verified release and verify health endpoints.",
            exercise_status="passed",
            exercise_result="Previous release restored and smoke checks passed.",
        ),
    }


def test_complete_exact_sha_bundle_passes_without_authorizing_delivery() -> None:
    bundle = build_operational_proof_bundle(**_valid_kwargs())
    gate = operational_proof_gate(bundle, expected_repository="BoneManTGRM/NICO", expected_release_sha=SHA)

    assert bundle["status"] == "passed"
    assert bundle["operational_readiness_demonstrated"] is True
    assert bundle["deployment_summary"]["observed"] == 2
    assert bundle["deployment_summary"]["successful"] == 1
    assert bundle["deployment_summary"]["non_success"] == 1
    assert bundle["deployment_summary"]["population_reconciles"] is True
    assert gate["status"] == "passed"
    assert gate["client_delivery_allowed"] is False


def test_repository_configuration_cannot_replace_missing_runtime_journey() -> None:
    kwargs = _valid_kwargs()
    kwargs["journeys"] = [item for item in kwargs["journeys"] if item["journey"] != "authorization"]

    bundle = build_operational_proof_bundle(**kwargs)

    assert bundle["status"] == "blocked"
    assert "authorization" in bundle["missing_journeys"]
    assert "required production journeys are missing" in " ".join(bundle["blockers"])


def test_service_deployment_must_match_exact_release_sha() -> None:
    kwargs = _valid_kwargs()
    kwargs["backend_deployment"] = _evidence("backend", deployed_sha="c" * 40, status="successful")

    bundle = build_operational_proof_bundle(**kwargs)
    backend_errors = next(item["errors"] for item in bundle["invalid_evidence"] if item["id"] == "backend")

    assert bundle["status"] == "blocked"
    assert "deployed_sha does not match" in " ".join(backend_errors)


def test_required_checks_must_be_required_passed_and_exact_sha_bound() -> None:
    kwargs = _valid_kwargs()
    kwargs["required_checks"][0]["conclusion"] = "failure"
    kwargs["required_checks"][0]["required"] = False
    kwargs["required_checks"][0]["release_sha"] = "c" * 40

    bundle = build_operational_proof_bundle(**kwargs)
    errors = next(item["errors"] for item in bundle["invalid_evidence"] if item["kind"] == "required_check")

    assert "not bound to the exact release SHA" in " ".join(errors)
    assert "did not pass" in " ".join(errors)
    assert "not proven to be required" in " ".join(errors)


def test_every_deployment_requires_an_explicit_supported_classification() -> None:
    kwargs = _valid_kwargs()
    kwargs["deployments"][1]["classification"] = ""

    bundle = build_operational_proof_bundle(**kwargs)

    assert bundle["status"] == "blocked"
    errors = next(item["errors"] for item in bundle["invalid_evidence"] if item["kind"] == "deployment")
    assert "classification is missing or unsupported" in " ".join(errors)


def test_current_release_requires_a_successful_deployment_observation() -> None:
    kwargs = _valid_kwargs()
    kwargs["deployments"][0]["classification"] = "configuration_issue"
    kwargs["deployments"][0]["classification_basis"] = "Configuration prevented release acceptance."

    bundle = build_operational_proof_bundle(**kwargs)

    assert bundle["status"] == "blocked"
    assert "successful observation for the exact release SHA" in " ".join(bundle["blockers"])


def test_rollback_procedure_without_exercise_remains_blocked() -> None:
    kwargs = _valid_kwargs()
    kwargs["rollback"]["exercise_status"] = "not_run"
    kwargs["rollback"]["exercise_result"] = ""

    bundle = build_operational_proof_bundle(**kwargs)
    rollback_errors = next(item["errors"] for item in bundle["invalid_evidence"] if item["kind"] == "rollback")

    assert bundle["status"] == "blocked"
    assert "successful rollback or recovery exercise" in " ".join(rollback_errors)


def test_duplicate_check_journey_and_deployment_identity_fail_closed() -> None:
    kwargs = _valid_kwargs()
    kwargs["required_checks"].append(deepcopy(kwargs["required_checks"][0]))
    kwargs["journeys"].append(deepcopy(kwargs["journeys"][0]))
    kwargs["deployments"].append(deepcopy(kwargs["deployments"][0]))

    bundle = build_operational_proof_bundle(**kwargs)
    blockers = " ".join(bundle["blockers"])

    assert bundle["status"] == "blocked"
    assert "duplicate required checks" in blockers
    assert "duplicate journey evidence" in blockers
    assert "duplicate deployment observations" in blockers


def test_gate_rejects_reuse_for_different_repository_or_release() -> None:
    bundle = build_operational_proof_bundle(**_valid_kwargs())

    gate = operational_proof_gate(bundle, expected_repository="Other/Repo", expected_release_sha="c" * 40)

    assert gate["status"] == "blocked"
    assert "repository identity" in " ".join(gate["blockers"])
    assert "release SHA" in " ".join(gate["blockers"])
