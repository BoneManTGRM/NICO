from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from nico.provider_platform_contract_v1 import (
    BranchPolicy,
    ChangeRequest,
    DeploymentReference,
    PipelineJob,
    PipelineRun,
    ProviderCapabilitySet,
    ProviderContractViolation,
    ProviderKind,
    RepositoryIdentity,
)

VERSION = "nico.provider_adapters.v1"

_STATUS_MAP = {
    "success": "success",
    "succeeded": "success",
    "passed": "success",
    "completed": "success",
    "failed": "genuine_failure",
    "failure": "genuine_failure",
    "error": "genuine_failure",
    "cancelled": "cancelled_by_user",
    "canceled": "cancelled_by_user",
    "skipped": "skipped",
    "running": "active",
    "in_progress": "active",
    "pending": "active",
    "queued": "active",
    "manual": "manual_action_required",
    "timed_out": "timed_out",
}


def normalize_pipeline_status(value: str) -> str:
    return _STATUS_MAP.get(str(value or "").strip().lower(), "unknown_review_required")


@dataclass
class FixtureProviderAdapter:
    kind: ProviderKind
    fixture: Mapping[str, Any]
    capabilities: ProviderCapabilitySet

    def authenticate(self) -> Mapping[str, Any]:
        auth = dict(self.fixture.get("authentication") or {})
        if auth.get("authorized") is not True:
            raise ProviderContractViolation(f"{self.kind.value}: authentication not authorized")
        return auth

    def get_repository_identity(self) -> RepositoryIdentity:
        repo = dict(self.fixture.get("repository") or {})
        identity = RepositoryIdentity(
            provider=self.kind,
            provider_instance=str(repo.get("provider_instance") or ""),
            organization_or_workspace=str(repo.get("organization_or_workspace") or ""),
            project=str(repo.get("project") or ""),
            repository=str(repo.get("repository") or ""),
            repository_id=str(repo.get("repository_id") or ""),
            branch=str(repo.get("branch") or ""),
            immutable_revision=str(repo.get("immutable_revision") or ""),
            revision_algorithm=str(repo.get("revision_algorithm") or "git-sha1"),
            clone_url_fingerprint=str(repo.get("clone_url_fingerprint") or ""),
            snapshot_created_at=str(repo.get("snapshot_created_at") or ""),
            provider_evidence_artifact=str(repo.get("provider_evidence_artifact") or ""),
            provider_evidence_sha256=str(repo.get("provider_evidence_sha256") or ""),
        )
        identity.validate()
        return identity

    def resolve_immutable_revision(self, revision: str | None = None) -> str:
        resolved = str(self.fixture.get("resolved_revision") or self.get_repository_identity().immutable_revision)
        if revision and revision != resolved:
            raise ProviderContractViolation(f"{self.kind.value}: requested revision does not resolve exactly")
        return resolved

    def snapshot_repository(self, revision: str) -> Mapping[str, Any]:
        if revision != self.resolve_immutable_revision(revision):
            raise ProviderContractViolation("snapshot revision mismatch")
        return dict(self.fixture.get("snapshot") or {})

    def list_branches(self) -> Sequence[str]:
        return tuple(str(item) for item in self.fixture.get("branches") or ())

    def list_commits(self, *, limit: int = 100) -> Sequence[Mapping[str, Any]]:
        return tuple(dict(item) for item in (self.fixture.get("commits") or ())[:limit])

    def list_change_requests(self, *, limit: int = 100) -> Sequence[ChangeRequest]:
        output = []
        for item in (self.fixture.get("change_requests") or ())[:limit]:
            output.append(ChangeRequest(**dict(item)))
        return tuple(output)

    def list_pipeline_runs(self, *, revision: str | None = None, limit: int = 100) -> Sequence[PipelineRun]:
        output = []
        for raw in (self.fixture.get("pipeline_runs") or ())[:limit]:
            item = dict(raw)
            if revision and item.get("revision") != revision:
                continue
            jobs = tuple(
                PipelineJob(
                    provider_job_id=str(job.get("provider_job_id") or job.get("id") or ""),
                    name=str(job.get("name") or ""),
                    provider_status=str(job.get("provider_status") or job.get("status") or ""),
                    normalized_status=normalize_pipeline_status(str(job.get("provider_status") or job.get("status") or "")),
                    started_at=str(job.get("started_at") or ""),
                    finished_at=str(job.get("finished_at") or ""),
                    stage=str(job.get("stage") or ""),
                    artifact_references=tuple(job.get("artifact_references") or ()),
                )
                for job in item.pop("jobs", ())
            )
            provider_status = str(item.pop("provider_status", item.pop("status", "")))
            output.append(PipelineRun(
                provider_run_id=str(item.get("provider_run_id") or item.get("id") or ""),
                name=str(item.get("name") or ""),
                revision=str(item.get("revision") or ""),
                branch=str(item.get("branch") or ""),
                provider_status=provider_status,
                normalized_status=normalize_pipeline_status(provider_status),
                started_at=str(item.get("started_at") or ""),
                finished_at=str(item.get("finished_at") or ""),
                jobs=jobs,
                web_url=str(item.get("web_url") or ""),
            ))
        return tuple(output)

    def list_branch_policies(self) -> Sequence[BranchPolicy]:
        return tuple(BranchPolicy(**dict(item)) for item in self.fixture.get("branch_policies") or ())

    def list_deployments(self, *, limit: int = 100) -> Sequence[DeploymentReference]:
        return tuple(DeploymentReference(**dict(item)) for item in (self.fixture.get("deployments") or ())[:limit])

    def download_artifact(self, artifact_reference: str) -> bytes:
        artifacts = self.fixture.get("artifacts") or {}
        if artifact_reference not in artifacts:
            raise ProviderContractViolation(f"Artifact not found: {artifact_reference}")
        value = artifacts[artifact_reference]
        return value if isinstance(value, bytes) else str(value).encode("utf-8")


class GitHubAdapter(FixtureProviderAdapter):
    def __init__(self, fixture: Mapping[str, Any], capabilities: ProviderCapabilitySet):
        super().__init__(ProviderKind.GITHUB, fixture, capabilities)


class GitLabAdapter(FixtureProviderAdapter):
    def __init__(self, fixture: Mapping[str, Any], capabilities: ProviderCapabilitySet):
        super().__init__(ProviderKind.GITLAB, fixture, capabilities)


class BitbucketCloudAdapter(FixtureProviderAdapter):
    def __init__(self, fixture: Mapping[str, Any], capabilities: ProviderCapabilitySet):
        super().__init__(ProviderKind.BITBUCKET_CLOUD, fixture, capabilities)


class AzureDevOpsAdapter(FixtureProviderAdapter):
    def __init__(self, fixture: Mapping[str, Any], capabilities: ProviderCapabilitySet):
        super().__init__(ProviderKind.AZURE_DEVOPS, fixture, capabilities)


class GiteaAdapter(FixtureProviderAdapter):
    def __init__(self, fixture: Mapping[str, Any], capabilities: ProviderCapabilitySet):
        super().__init__(ProviderKind.GITEA, fixture, capabilities)


class ForgejoAdapter(FixtureProviderAdapter):
    def __init__(self, fixture: Mapping[str, Any], capabilities: ProviderCapabilitySet):
        super().__init__(ProviderKind.FORGEJO, fixture, capabilities)


__all__ = [
    "AzureDevOpsAdapter",
    "BitbucketCloudAdapter",
    "FixtureProviderAdapter",
    "ForgejoAdapter",
    "GitHubAdapter",
    "GitLabAdapter",
    "GiteaAdapter",
    "normalize_pipeline_status",
]
