import pytest

from nico.provider_adapters_v1 import GitHubAdapter, GitLabAdapter, normalize_pipeline_status
from nico.provider_platform_contract_v1 import (
    ProviderCapabilitySet,
    ProviderContractViolation,
    assert_tier1_conformance,
)


def fixture():
    return {
        "authentication": {"authorized": True},
        "repository": {
            "provider_instance": "example.test",
            "organization_or_workspace": "org",
            "project": "project",
            "repository": "repo",
            "repository_id": "1",
            "branch": "main",
            "immutable_revision": "abc",
            "provider_evidence_artifact": "provider.json",
            "provider_evidence_sha256": "f" * 64,
        },
        "resolved_revision": "abc",
        "branches": ["main"],
        "commits": [{"sha": "abc"}],
        "change_requests": [],
        "pipeline_runs": [{
            "id": "run-1",
            "name": "CI",
            "revision": "abc",
            "branch": "main",
            "status": "passed",
            "jobs": [{"id": "job-1", "name": "tests", "status": "success"}],
        }],
        "branch_policies": [],
        "deployments": [],
        "artifacts": {"provider.json": "{}"},
    }


def tier1_capabilities():
    return ProviderCapabilitySet(
        repository_snapshot=True,
        immutable_revision_resolution=True,
        change_requests=True,
        pipeline_history=True,
        job_history=True,
        artifacts=True,
        branch_policies=True,
        deployments=True,
    )


def test_statuses_are_normalized_without_claiming_unknown_success():
    assert normalize_pipeline_status("passed") == "success"
    assert normalize_pipeline_status("mystery") == "unknown_review_required"


def test_github_and_gitlab_share_same_contract():
    for adapter_type in (GitHubAdapter, GitLabAdapter):
        adapter = adapter_type(fixture(), tier1_capabilities())
        assert_tier1_conformance(adapter)
        [run] = adapter.list_pipeline_runs(revision="abc")
        assert run.normalized_status == "success"
        assert run.jobs[0].normalized_status == "success"


def test_revision_mismatch_fails_closed():
    adapter = GitHubAdapter(fixture(), tier1_capabilities())
    with pytest.raises(ProviderContractViolation):
        adapter.resolve_immutable_revision("wrong")


def test_authentication_failure_is_explicit():
    data = fixture()
    data["authentication"] = {"authorized": False}
    adapter = GitHubAdapter(data, tier1_capabilities())
    with pytest.raises(ProviderContractViolation):
        adapter.authenticate()
