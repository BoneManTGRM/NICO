from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class ProviderKind(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    AZURE_DEVOPS = "azure_devops"
    GENERIC_GIT = "generic_git"
    ARCHIVE = "archive"


class Capability(str, Enum):
    REPOSITORY = "repository"
    COMMITS = "commits"
    BRANCHES = "branches"
    TREE = "tree"
    BLOBS = "blobs"
    TAGS = "tags"
    CHANGE_REQUESTS = "change_requests"
    REVIEWS = "reviews"
    CI_RUNS = "ci_runs"
    CI_JOBS = "ci_jobs"
    ENVIRONMENTS = "environments"
    DEPLOYMENTS = "deployments"
    WORK_ITEMS = "work_items"
    RELEASES = "releases"
    ARTIFACTS = "artifacts"
    PERMISSIONS = "permissions"
    SOURCE_LINKS = "source_links"
    WEBHOOKS = "webhooks"


class CapabilityState(str, Enum):
    SUPPORTED = "supported"
    SUPPORTED_LIMITED = "supported_limited"
    UNAVAILABLE_PERMISSION = "unavailable_permission"
    UNAVAILABLE_PROVIDER = "unavailable_provider"
    UNSUPPORTED = "unsupported"
    NOT_CONFIGURED = "not_configured"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class ProviderIdentity:
    provider: ProviderKind
    instance_url: str
    namespace: str
    repository: str
    repository_id: str
    default_branch: str


@dataclass(frozen=True)
class ProviderAccess:
    read_only: bool
    scopes: tuple[str, ...]
    capabilities: tuple[Capability, ...]
    partial_access: bool = False
    limitation_reason: str = ""


@dataclass(frozen=True)
class SnapshotIdentity:
    provider: ProviderKind
    repository_id: str
    revision: str
    collected_at: str
    source_fingerprint: str


@dataclass(frozen=True)
class CanonicalRepositoryRef:
    provider: ProviderKind
    repository_id: str
    name: str
    target_revision: str
    ref_type: str


@dataclass(frozen=True)
class CanonicalSourceObject:
    provider: ProviderKind
    repository_id: str
    revision: str
    path: str
    object_id: str
    object_type: str
    size: int | None = None
    mode: str = ""
    exact_url: str = ""


@dataclass(frozen=True)
class CanonicalExactSourceLocator:
    provider: ProviderKind
    repository_id: str
    revision: str
    path: str
    start_line: int | None = None
    end_line: int | None = None
    object_id: str = ""
    exact_url: str = ""


@dataclass(frozen=True)
class CanonicalChangeRequest:
    provider: ProviderKind
    native_id: str
    title: str
    state: str
    source_branch: str
    target_branch: str
    author: str
    created_at: str
    updated_at: str
    merged_at: str = ""
    review_state: str = "unknown"


@dataclass(frozen=True)
class CanonicalCIRun:
    provider: ProviderKind
    native_id: str
    name: str
    revision: str
    branch: str
    status: str
    conclusion: str
    started_at: str
    completed_at: str = ""
    url: str = ""


@dataclass(frozen=True)
class CanonicalCIJob:
    provider: ProviderKind
    run_id: str
    native_id: str
    name: str
    stage: str
    status: str
    conclusion: str
    started_at: str = ""
    completed_at: str = ""
    url: str = ""
    artifact_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalEnvironment:
    provider: ProviderKind
    native_id: str
    name: str
    state: str
    tier: str = ""
    url: str = ""


@dataclass(frozen=True)
class CanonicalDeployment:
    provider: ProviderKind
    native_id: str
    environment_id: str
    environment_name: str
    revision: str
    status: str
    created_at: str = ""
    completed_at: str = ""
    url: str = ""


@dataclass(frozen=True)
class CanonicalRelease:
    provider: ProviderKind
    native_id: str
    name: str
    tag_name: str
    revision: str
    created_at: str = ""
    released_at: str = ""
    url: str = ""
    artifact_references: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderCapabilityStatus:
    capability: Capability
    state: CapabilityState
    reason: str = ""


@dataclass(frozen=True)
class ProviderEvidenceEnvelope:
    identity: ProviderIdentity
    access: ProviderAccess
    snapshot: SnapshotIdentity
    change_requests: tuple[CanonicalChangeRequest, ...] = ()
    ci_runs: tuple[CanonicalCIRun, ...] = ()
    source_objects: tuple[CanonicalSourceObject, ...] = ()
    tags: tuple[CanonicalRepositoryRef, ...] = ()
    exact_source_locators: tuple[CanonicalExactSourceLocator, ...] = ()
    ci_jobs: tuple[CanonicalCIJob, ...] = ()
    environments: tuple[CanonicalEnvironment, ...] = ()
    deployments: tuple[CanonicalDeployment, ...] = ()
    releases: tuple[CanonicalRelease, ...] = ()
    capability_status: tuple[ProviderCapabilityStatus, ...] = ()
    pagination_complete: bool = True
    collection_limitations: tuple[str, ...] = ()


def _text(value: Any, *, empty: str = "") -> str:
    if value is None:
        return empty
    return " ".join(str(value).split())


def normalize_provider(value: Any) -> ProviderKind:
    token = _text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "github_enterprise": ProviderKind.GITHUB,
        "gitlab_self_managed": ProviderKind.GITLAB,
        "bitbucket_cloud": ProviderKind.BITBUCKET,
        "bitbucket_server": ProviderKind.BITBUCKET,
        "bitbucket_data_center": ProviderKind.BITBUCKET,
        "azure_repos": ProviderKind.AZURE_DEVOPS,
        "azure_devops_repos": ProviderKind.AZURE_DEVOPS,
        "uploaded_archive": ProviderKind.ARCHIVE,
        "zip": ProviderKind.ARCHIVE,
        "tar": ProviderKind.ARCHIVE,
        "ssh": ProviderKind.GENERIC_GIT,
        "https": ProviderKind.GENERIC_GIT,
    }
    if token in aliases:
        return aliases[token]
    return ProviderKind(token)


def normalize_capabilities(values: Iterable[Any]) -> tuple[Capability, ...]:
    output: list[Capability] = []
    seen: set[Capability] = set()
    for value in values:
        capability = value if isinstance(value, Capability) else Capability(_text(value).lower())
        if capability not in seen:
            seen.add(capability)
            output.append(capability)
    return tuple(output)


def provider_access_from_mapping(data: Mapping[str, Any]) -> ProviderAccess:
    return ProviderAccess(
        read_only=bool(data.get("read_only", True)),
        scopes=tuple(_text(item) for item in data.get("scopes", ()) if _text(item)),
        capabilities=normalize_capabilities(data.get("capabilities", ())),
        partial_access=bool(data.get("partial_access", False)),
        limitation_reason=_text(data.get("limitation_reason")),
    )


def _validate_source_coordinates(
    *,
    provider: ProviderKind,
    repository_id: str,
    revision: str,
    native_id: str,
    item_provider: ProviderKind,
    item_repository_id: str,
    item_revision: str,
) -> list[str]:
    issues: list[str] = []
    if item_provider is not provider:
        issues.append(f"source_provider_mismatch:{native_id}")
    if item_repository_id != repository_id:
        issues.append(f"source_repository_mismatch:{native_id}")
    if item_revision != revision:
        issues.append(f"source_revision_mismatch:{native_id}")
    return issues


def validate_provider_envelope(envelope: ProviderEvidenceEnvelope) -> list[str]:
    issues: list[str] = []
    if not envelope.access.read_only:
        issues.append("provider_access_must_be_read_only")
    if not envelope.identity.repository_id:
        issues.append("provider_repository_id_required")
    if not envelope.snapshot.revision:
        issues.append("provider_snapshot_revision_required")
    if envelope.snapshot.provider != envelope.identity.provider:
        issues.append("provider_snapshot_identity_mismatch")
    if envelope.snapshot.repository_id != envelope.identity.repository_id:
        issues.append("provider_snapshot_repository_mismatch")
    if Capability.REPOSITORY not in envelope.access.capabilities:
        issues.append("provider_repository_capability_required")
    if envelope.access.partial_access and not envelope.access.limitation_reason:
        issues.append("provider_partial_access_limitation_required")
    if not envelope.pagination_complete and not envelope.collection_limitations:
        issues.append("provider_incomplete_pagination_requires_limitation")

    seen_status: set[Capability] = set()
    for status in envelope.capability_status:
        if status.capability in seen_status:
            issues.append(f"provider_capability_state_duplicate:{status.capability.value}")
        seen_status.add(status.capability)
        if status.state in {CapabilityState.SUPPORTED, CapabilityState.SUPPORTED_LIMITED}:
            if status.capability not in envelope.access.capabilities:
                issues.append(f"provider_capability_state_access_mismatch:{status.capability.value}")
        elif status.state in {
            CapabilityState.UNAVAILABLE_PERMISSION,
            CapabilityState.UNAVAILABLE_PROVIDER,
            CapabilityState.UNSUPPORTED,
        } and not status.reason:
            issues.append(f"provider_capability_state_reason_required:{status.capability.value}")

    for source in envelope.source_objects:
        issues.extend(
            _validate_source_coordinates(
                provider=envelope.identity.provider,
                repository_id=envelope.identity.repository_id,
                revision=envelope.snapshot.revision,
                native_id=source.path or source.object_id,
                item_provider=source.provider,
                item_repository_id=source.repository_id,
                item_revision=source.revision,
            )
        )
        if not source.path or not source.object_id:
            issues.append(f"source_object_identity_incomplete:{source.path or source.object_id}")

    for locator in envelope.exact_source_locators:
        issues.extend(
            _validate_source_coordinates(
                provider=envelope.identity.provider,
                repository_id=envelope.identity.repository_id,
                revision=envelope.snapshot.revision,
                native_id=locator.path,
                item_provider=locator.provider,
                item_repository_id=locator.repository_id,
                item_revision=locator.revision,
            )
        )
        if not locator.path:
            issues.append("exact_source_path_required")
        if locator.start_line is not None and locator.start_line < 1:
            issues.append(f"exact_source_start_line_invalid:{locator.path}")
        if locator.end_line is not None:
            if locator.end_line < 1 or (
                locator.start_line is not None and locator.end_line < locator.start_line
            ):
                issues.append(f"exact_source_end_line_invalid:{locator.path}")

    for ref in envelope.tags:
        if ref.provider is not envelope.identity.provider:
            issues.append(f"tag_provider_mismatch:{ref.name}")
        if ref.repository_id != envelope.identity.repository_id:
            issues.append(f"tag_repository_mismatch:{ref.name}")
        if ref.ref_type != "tag":
            issues.append(f"tag_ref_type_invalid:{ref.name}")

    for run in envelope.ci_runs:
        if run.provider != envelope.identity.provider:
            issues.append(f"ci_provider_mismatch:{run.native_id}")
        if run.revision and run.revision != envelope.snapshot.revision:
            issues.append(f"ci_revision_outside_snapshot:{run.native_id}")

    run_ids = {run.native_id for run in envelope.ci_runs}
    for job in envelope.ci_jobs:
        if job.provider is not envelope.identity.provider:
            issues.append(f"ci_job_provider_mismatch:{job.native_id}")
        if job.run_id and job.run_id not in run_ids:
            issues.append(f"ci_job_run_missing:{job.native_id}")

    for item in (*envelope.environments, *envelope.deployments, *envelope.releases):
        if item.provider is not envelope.identity.provider:
            issues.append(f"provider_native_evidence_mismatch:{item.native_id}")
    return issues


PROVIDER_MINIMUM_CAPABILITIES: dict[ProviderKind, tuple[Capability, ...]] = {
    ProviderKind.GITHUB: (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
        Capability.WORK_ITEMS,
        Capability.RELEASES,
        Capability.PERMISSIONS,
        Capability.WEBHOOKS,
    ),
    ProviderKind.GITLAB: (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
        Capability.WORK_ITEMS,
        Capability.RELEASES,
        Capability.PERMISSIONS,
        Capability.WEBHOOKS,
    ),
    ProviderKind.BITBUCKET: (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
        Capability.WORK_ITEMS,
        Capability.PERMISSIONS,
        Capability.WEBHOOKS,
    ),
    ProviderKind.AZURE_DEVOPS: (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
        Capability.WORK_ITEMS,
        Capability.RELEASES,
        Capability.PERMISSIONS,
        Capability.WEBHOOKS,
    ),
    ProviderKind.GENERIC_GIT: (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
    ),
    ProviderKind.ARCHIVE: (
        Capability.REPOSITORY,
    ),
}


PROVIDER_FIRST_CLASS_CAPABILITIES: dict[ProviderKind, tuple[Capability, ...]] = {
    provider: tuple(
        dict.fromkeys(
            (*PROVIDER_MINIMUM_CAPABILITIES[provider],
             Capability.TREE,
             Capability.BLOBS,
             Capability.TAGS,
             Capability.CI_JOBS,
             Capability.ENVIRONMENTS,
             Capability.DEPLOYMENTS,
             Capability.SOURCE_LINKS)
        )
    )
    for provider in (
        ProviderKind.GITHUB,
        ProviderKind.GITLAB,
        ProviderKind.BITBUCKET,
        ProviderKind.AZURE_DEVOPS,
    )
}


__all__ = [
    "CanonicalCIJob",
    "CanonicalCIRun",
    "CanonicalChangeRequest",
    "CanonicalDeployment",
    "CanonicalEnvironment",
    "CanonicalExactSourceLocator",
    "CanonicalRelease",
    "CanonicalRepositoryRef",
    "CanonicalSourceObject",
    "Capability",
    "CapabilityState",
    "PROVIDER_FIRST_CLASS_CAPABILITIES",
    "PROVIDER_MINIMUM_CAPABILITIES",
    "ProviderAccess",
    "ProviderCapabilityStatus",
    "ProviderEvidenceEnvelope",
    "ProviderIdentity",
    "ProviderKind",
    "SnapshotIdentity",
    "normalize_capabilities",
    "normalize_provider",
    "provider_access_from_mapping",
    "validate_provider_envelope",
]
