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
    CHANGE_REQUESTS = "change_requests"
    REVIEWS = "reviews"
    CI_RUNS = "ci_runs"
    WORK_ITEMS = "work_items"
    RELEASES = "releases"
    PERMISSIONS = "permissions"
    WEBHOOKS = "webhooks"


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
class ProviderEvidenceEnvelope:
    identity: ProviderIdentity
    access: ProviderAccess
    snapshot: SnapshotIdentity
    change_requests: tuple[CanonicalChangeRequest, ...] = ()
    ci_runs: tuple[CanonicalCIRun, ...] = ()


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
    for run in envelope.ci_runs:
        if run.provider != envelope.identity.provider:
            issues.append(f"ci_provider_mismatch:{run.native_id}")
        if run.revision and run.revision != envelope.snapshot.revision:
            issues.append(f"ci_revision_outside_snapshot:{run.native_id}")
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


__all__ = [
    "CanonicalCIRun",
    "CanonicalChangeRequest",
    "Capability",
    "PROVIDER_MINIMUM_CAPABILITIES",
    "ProviderAccess",
    "ProviderEvidenceEnvelope",
    "ProviderIdentity",
    "ProviderKind",
    "SnapshotIdentity",
    "normalize_capabilities",
    "normalize_provider",
    "provider_access_from_mapping",
    "validate_provider_envelope",
]
