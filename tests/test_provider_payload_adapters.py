from nico.provider_neutral_contract import ProviderKind
from nico.provider_payload_adapters import (
    adapt_azure_devops_payload,
    adapt_bitbucket_payload,
    adapt_gitlab_payload,
    adapt_offline_source,
)


def test_gitlab_payload_maps_merge_requests_and_exact_pipeline_revision() -> None:
    result = adapt_gitlab_payload({
        "instance_url": "https://gitlab.example.com",
        "collected_at": "2026-07-17T12:00:00Z",
        "revision": "abc123",
        "project": {"id": 17, "path_with_namespace": "team/service", "path": "service", "default_branch": "main"},
        "merge_requests": [{"iid": 8, "title": "Fix", "state": "merged", "source_branch": "fix", "target_branch": "main", "author": {"username": "dev"}, "created_at": "a", "updated_at": "b", "merged_at": "b"}],
        "pipelines": [{"id": 9, "ref": "main", "sha": "abc123", "status": "success", "created_at": "a", "finished_at": "b"}],
    })
    assert result.warnings == ()
    assert result.envelope.identity.provider is ProviderKind.GITLAB
    assert result.envelope.change_requests[0].native_id == "8"
    assert result.envelope.ci_runs[0].revision == "abc123"


def test_bitbucket_payload_maps_pr_and_pipeline() -> None:
    result = adapt_bitbucket_payload({
        "revision": "def456",
        "collected_at": "2026-07-17T12:00:00Z",
        "repository": {"uuid": "repo-1", "slug": "service", "workspace": {"slug": "team"}, "mainbranch": {"name": "main"}},
        "pull_requests": [{"id": 3, "title": "Change", "state": "MERGED", "source": {"branch": {"name": "feature"}}, "destination": {"branch": {"name": "main"}}, "author": {"display_name": "Dev"}, "created_on": "a", "updated_on": "b"}],
        "pipelines": [{"uuid": "pipe-1", "name": "test", "target": {"commit": {"hash": "def456"}, "ref_name": "main"}, "state": {"name": "COMPLETED", "result": {"name": "SUCCESSFUL"}}, "created_on": "a", "completed_on": "b"}],
    })
    assert result.warnings == ()
    assert result.envelope.identity.provider is ProviderKind.BITBUCKET
    assert result.envelope.ci_runs[0].conclusion == "SUCCESSFUL"


def test_azure_payload_strips_ref_prefixes_and_binds_build() -> None:
    result = adapt_azure_devops_payload({
        "revision": "fedcba",
        "collected_at": "2026-07-17T12:00:00Z",
        "repository": {"id": "repo-2", "name": "service", "defaultBranch": "refs/heads/main", "project": {"name": "Platform"}},
        "pull_requests": [{"pullRequestId": 4, "title": "Update", "status": "completed", "sourceRefName": "refs/heads/feature", "targetRefName": "refs/heads/main", "createdBy": {"displayName": "Dev"}, "creationDate": "a", "closedDate": "b"}],
        "builds": [{"id": 5, "definition": {"name": "CI"}, "sourceVersion": "fedcba", "sourceBranch": "refs/heads/main", "status": "completed", "result": "succeeded", "startTime": "a", "finishTime": "b"}],
    })
    assert result.warnings == ()
    assert result.envelope.identity.default_branch == "main"
    assert result.envelope.change_requests[0].source_branch == "feature"
    assert result.envelope.ci_runs[0].branch == "main"


def test_cross_revision_ci_is_exposed_as_warning_not_silently_accepted() -> None:
    result = adapt_gitlab_payload({
        "revision": "expected",
        "project": {"id": 17, "path": "service", "path_with_namespace": "team/service"},
        "pipelines": [{"id": 9, "ref": "main", "sha": "different", "status": "success"}],
    })
    assert "ci_revision_outside_snapshot:9" in result.warnings


def test_offline_archive_is_read_only_and_snapshot_bound() -> None:
    result = adapt_offline_source({
        "filename": "service.zip",
        "content_hash": "sha256:archive",
        "collected_at": "2026-07-17T12:00:00Z",
    }, archive=True)
    assert result.warnings == ()
    assert result.envelope.identity.provider is ProviderKind.ARCHIVE
    assert result.envelope.access.read_only is True
    assert result.envelope.snapshot.revision == "sha256:archive"
