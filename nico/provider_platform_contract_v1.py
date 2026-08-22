from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

VERSION = "nico.provider_platform_contract.v1"
IDENTITY_VERSION = "nico.repository_provider_identity.v2"


class ProviderContractViolation(ValueError):
    pass


class ProviderKind(str, Enum):
    # Wire values are retained for backward compatibility.
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET_CLOUD = "bitbucket_cloud"
    AZURE_DEVOPS = "azure_devops"
    BITBUCKET_DATA_CENTER = "bitbucket_data_center"
    GITEA = "gitea"
    FORGEJO = "forgejo"
    AWS_CODECOMMIT = "aws_codecommit"
    JENKINS = "jenkins"
    CIRCLECI = "circleci"
    BUILDKITE = "buildkite"
    TEAMCITY = "teamcity"
    GERRIT = "gerrit"
    PERFORCE = "perforce"
    SUBVERSION = "subversion"


class ProviderDeployment(str, Enum):
    HOSTED = "hosted"
    SELF_MANAGED = "self_managed"
    EXTERNAL_CI = "external_ci"


_HOSTED_PROVIDER_HOSTS: Mapping[ProviderKind, frozenset[str]] = {
    ProviderKind.GITHUB: frozenset({"github.com", "api.github.com"}),
    ProviderKind.GITLAB: frozenset({"gitlab.com"}),
    ProviderKind.BITBUCKET_CLOUD: frozenset({"bitbucket.org", "api.bitbucket.org"}),
    ProviderKind.AZURE_DEVOPS: frozenset({"dev.azure.com"}),
}

_EXTERNAL_CI_PROVIDERS = frozenset(
    {
        ProviderKind.JENKINS,
        ProviderKind.CIRCLECI,
        ProviderKind.BUILDKITE,
        ProviderKind.TEAMCITY,
    }
)


def normalize_provider_instance(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ProviderContractViolation("Provider instance is required")
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlsplit(candidate)
    if not parsed.hostname:
        raise ProviderContractViolation("Provider instance must contain a hostname")
    if parsed.username or parsed.password:
        raise ProviderContractViolation("Provider instance must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ProviderContractViolation("Provider instance must not contain query or fragment data")
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ProviderContractViolation("Provider instance must use HTTP or HTTPS identity syntax")
    hostname = parsed.hostname.lower().rstrip(".")
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = "/" + "/".join(part for part in parsed.path.split("/") if part)
    if path == "/":
        path = ""
    return urlunsplit((scheme, f"{hostname}{port}", path, "", ""))


def provider_family(provider: ProviderKind) -> str:
    if provider in {ProviderKind.BITBUCKET_CLOUD, ProviderKind.BITBUCKET_DATA_CENTER}:
        return "bitbucket"
    return provider.value


def infer_provider_deployment(provider: ProviderKind, provider_instance: str) -> ProviderDeployment:
    normalized = normalize_provider_instance(provider_instance)
    host = urlsplit(normalized).hostname or ""
    if provider in _EXTERNAL_CI_PROVIDERS:
        return ProviderDeployment.EXTERNAL_CI
    if provider is ProviderKind.BITBUCKET_DATA_CENTER:
        return ProviderDeployment.SELF_MANAGED
    if provider is ProviderKind.AWS_CODECOMMIT:
        return ProviderDeployment.HOSTED
    if provider is ProviderKind.AZURE_DEVOPS and (host == "dev.azure.com" or host.endswith(".visualstudio.com")):
        return ProviderDeployment.HOSTED
    if host in _HOSTED_PROVIDER_HOSTS.get(provider, frozenset()):
        return ProviderDeployment.HOSTED
    if provider in {
        ProviderKind.GITHUB,
        ProviderKind.GITLAB,
        ProviderKind.AZURE_DEVOPS,
        ProviderKind.GITEA,
        ProviderKind.FORGEJO,
        ProviderKind.GERRIT,
        ProviderKind.PERFORCE,
        ProviderKind.SUBVERSION,
    }:
        return ProviderDeployment.SELF_MANAGED
    return ProviderDeployment.HOSTED


@dataclass(frozen=True)
class ProviderCapabilitySet:
    repository_snapshot: bool = False
    immutable_revision_resolution: bool = False
    change_requests: bool = False
    pipeline_history: bool = False
    job_history: bool = False
    artifacts: bool = False
    branch_policies: bool = False
    deployments: bool = False
    full_history_secret_scan: bool = False

    def as_dict(self) -> dict[str, bool]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RepositoryIdentity:
    provider: ProviderKind
    provider_instance: str
    organization_or_workspace: str
    project: str
    repository: str
    repository_id: str
    branch: str
    immutable_revision: str
    revision_algorithm: str = "git-sha1"
    clone_url_fingerprint: str = ""
    snapshot_created_at: str = ""
    provider_evidence_artifact: str = ""
    provider_evidence_sha256: str = ""
    provider_deployment: ProviderDeployment | None = None

    @property
    def normalized_provider_instance(self) -> str:
        return normalize_provider_instance(self.provider_instance)

    @property
    def resolved_provider_deployment(self) -> ProviderDeployment:
        inferred = infer_provider_deployment(self.provider, self.provider_instance)
        if self.provider_deployment is None:
            return inferred
        if self.provider_deployment is not inferred:
            raise ProviderContractViolation(
                "Provider deployment contradicts provider kind or instance: "
                f"declared={self.provider_deployment.value}; inferred={inferred.value}"
            )
        return self.provider_deployment

    @property
    def canonical_provider_instance_id(self) -> str:
        digest = hashlib.sha256(self.normalized_provider_instance.encode("utf-8")).hexdigest()
        return f"provider-instance-v2:{digest}"

    @property
    def canonical_repository_key(self) -> str:
        if not str(self.repository_id or "").strip():
            raise ProviderContractViolation("Immutable provider repository ID is required")
        components = (
            IDENTITY_VERSION,
            provider_family(self.provider),
            self.resolved_provider_deployment.value,
            self.canonical_provider_instance_id,
            str(self.repository_id).strip(),
        )
        digest = hashlib.sha256("\x1f".join(components).encode("utf-8")).hexdigest()
        return f"nico-repository-v2:{digest}"

    def validate(self) -> None:
        required = {
            "provider_instance": self.provider_instance,
            "repository": self.repository,
            "repository_id": self.repository_id,
            "immutable_revision": self.immutable_revision,
            "revision_algorithm": self.revision_algorithm,
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if missing:
            raise ProviderContractViolation(f"Repository identity is incomplete: {missing}")
        # Evaluate canonical coordinates during validation so unsafe or ambiguous
        # instance data cannot enter candidate lineage or approval bindings.
        _ = self.canonical_repository_key


@dataclass(frozen=True)
class ChangeRequest:
    provider_id: str
    title: str
    state: str
    source_branch: str
    target_branch: str
    source_revision: str
    merge_revision: str | None = None
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    approval_state: str = "unknown"
    web_url: str = ""


@dataclass(frozen=True)
class PipelineJob:
    provider_job_id: str
    name: str
    provider_status: str
    normalized_status: str
    started_at: str = ""
    finished_at: str = ""
    stage: str = ""
    artifact_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineRun:
    provider_run_id: str
    name: str
    revision: str
    branch: str
    provider_status: str
    normalized_status: str
    started_at: str = ""
    finished_at: str = ""
    jobs: tuple[PipelineJob, ...] = ()
    web_url: str = ""


@dataclass(frozen=True)
class BranchPolicy:
    branch: str
    required_reviews: int | None = None
    required_status_checks: tuple[str, ...] = ()
    force_push_allowed: bool | None = None
    deletion_allowed: bool | None = None
    provider_native: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeploymentReference:
    provider_deployment_id: str
    environment: str
    revision: str
    status: str
    created_at: str = ""
    web_url: str = ""


class SourceControlProvider(Protocol):
    kind: ProviderKind
    capabilities: ProviderCapabilitySet

    def authenticate(self) -> Mapping[str, Any]: ...
    def get_repository_identity(self) -> RepositoryIdentity: ...
    def resolve_immutable_revision(self, revision: str | None = None) -> str: ...
    def snapshot_repository(self, revision: str) -> Mapping[str, Any]: ...
    def list_branches(self) -> Sequence[str]: ...
    def list_commits(self, *, limit: int = 100) -> Sequence[Mapping[str, Any]]: ...
    def list_change_requests(self, *, limit: int = 100) -> Sequence[ChangeRequest]: ...
    def list_pipeline_runs(self, *, revision: str | None = None, limit: int = 100) -> Sequence[PipelineRun]: ...
    def list_branch_policies(self) -> Sequence[BranchPolicy]: ...
    def list_deployments(self, *, limit: int = 100) -> Sequence[DeploymentReference]: ...
    def download_artifact(self, artifact_reference: str) -> bytes: ...


def capability_limitations(provider: SourceControlProvider) -> list[dict[str, Any]]:
    limitations: list[dict[str, Any]] = []
    for capability, available in provider.capabilities.as_dict().items():
        if available:
            continue
        limitations.append(
            {
                "limitation_id": f"provider-capability-{provider.kind.value}-{capability}",
                "category": "provider_capability",
                "description": f"{provider.kind.value} adapter does not provide {capability} evidence.",
                "affected_controls": [capability],
                "confidence_effect": "Evidence assurance only; technical maturity is not penalized as zero.",
                "delivery_effect": "Human review required when the missing capability is decision-relevant.",
            }
        )
    return limitations


def validate_provider(adapter: SourceControlProvider) -> RepositoryIdentity:
    identity = adapter.get_repository_identity()
    identity.validate()
    if adapter.capabilities.immutable_revision_resolution:
        resolved = adapter.resolve_immutable_revision(identity.immutable_revision)
        if resolved != identity.immutable_revision:
            raise ProviderContractViolation(
                f"Provider revision mismatch: identity={identity.immutable_revision} resolved={resolved}"
            )
    if adapter.capabilities.repository_snapshot and not identity.provider_evidence_sha256:
        raise ProviderContractViolation("Snapshot-capable provider must retain a hashed provider evidence artifact")
    return identity


TIER1_REQUIRED_CAPABILITIES = ProviderCapabilitySet(
    repository_snapshot=True,
    immutable_revision_resolution=True,
    change_requests=True,
    pipeline_history=True,
    job_history=True,
    artifacts=True,
    branch_policies=True,
    deployments=True,
    full_history_secret_scan=False,
)


def assert_tier1_conformance(adapter: SourceControlProvider) -> None:
    validate_provider(adapter)
    missing = [
        name
        for name, required in TIER1_REQUIRED_CAPABILITIES.as_dict().items()
        if required and not adapter.capabilities.as_dict().get(name)
    ]
    if missing:
        raise ProviderContractViolation(f"Tier 1 provider is missing required capabilities: {missing}")


__all__ = [
    "BranchPolicy",
    "ChangeRequest",
    "DeploymentReference",
    "IDENTITY_VERSION",
    "PipelineJob",
    "PipelineRun",
    "ProviderCapabilitySet",
    "ProviderContractViolation",
    "ProviderDeployment",
    "ProviderKind",
    "RepositoryIdentity",
    "SourceControlProvider",
    "assert_tier1_conformance",
    "capability_limitations",
    "infer_provider_deployment",
    "normalize_provider_instance",
    "provider_family",
    "validate_provider",
]
