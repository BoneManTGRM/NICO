from __future__ import annotations

from copy import deepcopy

from nico.operations_readiness import OPERATIONS_READINESS_SCHEMA
from nico.production_release_gate import (
    FRONTEND_DEPLOYMENT_SCHEMA,
    REQUIRED_WORKFLOWS,
    build_production_release_manifest,
    provider_summary,
    safe_origin,
    sha_matches,
)


RELEASE_SHA = "a" * 40
STALE_SHA = "b" * 40
BACKEND_URL = "https://nico-api.example.com"
FRONTEND_URL = "https://app.example.com"
GENERATED_AT = "2026-07-12T17:30:00Z"


def _workflow_runs(sha: str = RELEASE_SHA) -> list[dict]:
    return [
        {
            "id": index + 1,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "event": "pull_request",
            "head_sha": sha,
            "run_number": 100 + index,
            "run_attempt": 1,
            "html_url": f"https://github.com/example/actions/runs/{index + 1}",
        }
        for index, name in enumerate(REQUIRED_WORKFLOWS)
    ]


def _check_runs() -> list[dict]:
    return [
        {
            "name": "Vercel - nicoaudit",
            "status": "completed",
            "conclusion": "success",
            "details_url": "https://vercel.example/deployments/1",
        },
        {
            "name": "Railway",
            "status": "completed",
            "conclusion": "success",
            "details_url": "https://railway.example/deployments/1",
        },
    ]


def _backend(sha: str = RELEASE_SHA) -> dict:
    return {
        "artifact_schema": OPERATIONS_READINESS_SCHEMA,
        "status": "ready",
        "operational_ready": True,
        "blockers": [],
        "deployment": {
            "deployed_commit": sha,
            "matches_expected_build": True,
        },
    }


def _frontend(sha: str = RELEASE_SHA) -> dict:
    return {
        "artifact_schema": FRONTEND_DEPLOYMENT_SCHEMA,
        "status": "ok",
        "provider": "vercel",
        "frontend_commit": sha,
    }


def _manifest(**overrides):
    values = {
        "repository": "BoneManTGRM/NICO",
        "expected_sha": RELEASE_SHA,
        "main_head_sha": RELEASE_SHA,
        "workflow_runs": _workflow_runs(),
        "check_runs": _check_runs(),
        "commit_statuses": [],
        "backend_readiness": _backend(),
        "frontend_deployment": _frontend(),
        "backend_url": BACKEND_URL,
        "frontend_url": FRONTEND_URL,
        "generated_at": GENERATED_AT,
    }
    values.update(overrides)
    return build_production_release_manifest(**values)


def _failed_ids(manifest: dict) -> set[str]:
    return {item["id"] for item in manifest["checks"] if not item["passed"]}


def test_complete_exact_release_is_ready_and_last_known_good_eligible():
    manifest = _manifest()

    assert manifest["status"] == "ready"
    assert manifest["release_ready"] is True
    assert manifest["last_known_good_eligible"] is True
    assert manifest["blockers"] == []
    assert len(manifest["release_identity_sha256"]) == 64
    assert len(manifest["manifest_sha256"]) == 64
    assert manifest["backend"]["commit"] == RELEASE_SHA
    assert manifest["frontend"]["commit"] == RELEASE_SHA
    assert manifest["human_review_required"] is True
    assert manifest["client_delivery_allowed"] is False


def test_stale_frontend_blocks_release_and_cross_deployment_alignment():
    manifest = _manifest(frontend_deployment=_frontend(STALE_SHA))

    assert manifest["status"] == "blocked"
    assert manifest["release_ready"] is False
    assert {"frontend_release_sha", "frontend_backend_alignment"} <= _failed_ids(manifest)


def test_non_head_release_is_blocked_even_when_deployments_match_it():
    manifest = _manifest(main_head_sha=STALE_SHA)

    assert manifest["status"] == "blocked"
    assert "release_is_main_head" in manifest["blockers"]


def test_missing_required_workflow_is_not_treated_as_success():
    runs = [run for run in _workflow_runs() if run["name"] != "Security Audit Evidence"]
    manifest = _manifest(workflow_runs=runs)

    assert manifest["status"] == "blocked"
    assert "workflow_security_audit_evidence" in manifest["blockers"]


def test_latest_failed_workflow_attempt_overrides_older_success():
    runs = _workflow_runs()
    runs.append(
        {
            "id": 999,
            "name": "NICO CI",
            "status": "completed",
            "conclusion": "failure",
            "event": "pull_request",
            "head_sha": RELEASE_SHA,
            "run_number": 1000,
            "run_attempt": 1,
        }
    )
    manifest = _manifest(workflow_runs=runs)

    assert manifest["status"] == "blocked"
    assert "workflow_nico_ci" in manifest["blockers"]


def test_provider_failure_or_missing_provider_blocks_release():
    failed = deepcopy(_check_runs())
    failed[0]["conclusion"] = "failure"
    manifest = _manifest(check_runs=failed)

    assert manifest["status"] == "blocked"
    assert "provider_vercel" in manifest["blockers"]

    missing = _manifest(check_runs=[_check_runs()[0]])
    assert "provider_railway" in missing["blockers"]


def test_commit_status_success_can_supply_provider_evidence():
    manifest = _manifest(
        check_runs=[],
        commit_statuses=[
            {"context": "Vercel", "state": "success", "target_url": "https://vercel.example/1"},
            {"context": "Railway", "state": "success", "target_url": "https://railway.example/1"},
        ],
    )

    assert manifest["status"] == "ready"


def test_real_railway_style_context_matches_safe_target_origin_only():
    statuses = [
        {
            "context": "Vercel",
            "state": "success",
            "target_url": "https://vercel.com/acme/nico/deployment?token=discarded",
        },
        {
            "context": "successful-cat - NICO",
            "state": "success",
            "target_url": (
                "https://railway.com/project/project-id/service/service-id"
                "?id=deployment-id&environmentId=environment-id#details"
            ),
        },
    ]

    providers = provider_summary([], statuses)
    manifest = _manifest(check_runs=[], commit_statuses=statuses)
    railway_observation = providers["railway"]["observations"][0]

    assert providers["railway"]["matched"] is True
    assert providers["railway"]["passed"] is True
    assert railway_observation["name"] == "successful-cat - NICO"
    assert railway_observation["url"] == "https://railway.com"
    assert "project-id" not in repr(providers)
    assert "deployment-id" not in repr(providers)
    assert "environment-id" not in repr(providers)
    assert "?" not in railway_observation["url"]
    assert manifest["status"] == "ready"
    assert manifest["providers"]["railway"]["observations"][0]["url"] == "https://railway.com"


def test_unrelated_domain_does_not_impersonate_railway():
    providers = provider_summary(
        [],
        [
            {
                "context": "successful-cat - NICO",
                "state": "success",
                "target_url": "https://railway.com.attacker.example/project/1",
            }
        ],
    )

    assert providers["railway"]["matched"] is False
    assert providers["railway"]["passed"] is False


def test_malformed_or_degraded_backend_readiness_blocks_release():
    malformed = _manifest(backend_readiness={"status": "ready", "operational_ready": True})
    assert "backend_readiness_schema" in malformed["blockers"]

    degraded_backend = _backend()
    degraded_backend["status"] = "degraded"
    degraded_backend["operational_ready"] = False
    degraded = _manifest(backend_readiness=degraded_backend)
    assert "backend_semantic_readiness" in degraded["blockers"]


def test_manifest_hashing_is_deterministic_for_identical_evidence():
    first = _manifest()
    second = _manifest()

    assert first["release_identity_sha256"] == second["release_identity_sha256"]
    assert first["manifest_sha256"] == second["manifest_sha256"]

    changed = _manifest(frontend_deployment=_frontend(STALE_SHA))
    assert changed["release_identity_sha256"] != first["release_identity_sha256"]
    assert changed["manifest_sha256"] != first["manifest_sha256"]


def test_sha_matching_and_safe_origin_fail_closed():
    assert sha_matches(RELEASE_SHA, RELEASE_SHA)
    assert sha_matches(RELEASE_SHA, RELEASE_SHA[:12])
    assert not sha_matches(RELEASE_SHA, STALE_SHA)
    assert not sha_matches("bad", RELEASE_SHA)
    assert safe_origin("https://app.example.com/path?token=hidden") == "https://app.example.com"
    assert safe_origin("http://app.example.com") == ""
    assert safe_origin("https://user:pass@app.example.com") == ""
