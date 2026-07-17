from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Mapping

from nico.provider_neutral_contract import (
    CanonicalCIRun,
    CanonicalChangeRequest,
    Capability,
    ProviderAccess,
    ProviderEvidenceEnvelope,
    ProviderIdentity,
    ProviderKind,
    SnapshotIdentity,
    validate_provider_envelope,
)


@dataclass(frozen=True)
class AdapterResult:
    envelope: ProviderEvidenceEnvelope
    warnings: tuple[str, ...] = ()


def _text(value: Any, *, empty: str = "") -> str:
    if value is None:
        return empty
    return " ".join(str(value).split())


def _fingerprint(provider: ProviderKind, repository_id: str, revision: str) -> str:
    payload = f"{provider.value}:{repository_id}:{revision}".encode("utf-8")
    return f"sha256:{sha256(payload).hexdigest()}"


def _access(*, scopes: Iterable[str], capabilities: Iterable[Capability], partial: bool = False, reason: str = "") -> ProviderAccess:
    return ProviderAccess(
        read_only=True,
        scopes=tuple(_text(item) for item in scopes if _text(item)),
        capabilities=tuple(dict.fromkeys(capabilities)),
        partial_access=partial,
        limitation_reason=_text(reason),
    )


def adapt_gitlab_payload(payload: Mapping[str, Any]) -> AdapterResult:
    project = payload.get("project") or {}
    repository_id = _text(project.get("id"))
    revision = _text(payload.get("revision") or payload.get("commit_sha"))
    instance = _text(payload.get("instance_url") or "https://gitlab.com")
    namespace = _text(project.get("namespace") or project.get("path_with_namespace", "").rsplit("/", 1)[0])
    repository = _text(project.get("path") or project.get("name"))
    identity = ProviderIdentity(ProviderKind.GITLAB, instance, namespace, repository, repository_id, _text(project.get("default_branch") or "main"))
    snapshot = SnapshotIdentity(ProviderKind.GITLAB, repository_id, revision, _text(payload.get("collected_at")), _fingerprint(ProviderKind.GITLAB, repository_id, revision))
    changes = tuple(
        CanonicalChangeRequest(
            provider=ProviderKind.GITLAB,
            native_id=_text(item.get("iid") or item.get("id")),
            title=_text(item.get("title")),
            state=_text(item.get("state")),
            source_branch=_text(item.get("source_branch")),
            target_branch=_text(item.get("target_branch")),
            author=_text((item.get("author") or {}).get("username") or item.get("author")),
            created_at=_text(item.get("created_at")),
            updated_at=_text(item.get("updated_at")),
            merged_at=_text(item.get("merged_at")),
            review_state=_text(item.get("detailed_merge_status") or item.get("review_state") or "unknown"),
        )
        for item in payload.get("merge_requests", ())
    )
    runs = tuple(
        CanonicalCIRun(
            provider=ProviderKind.GITLAB,
            native_id=_text(item.get("id")),
            name=_text(item.get("name") or item.get("ref") or "pipeline"),
            revision=_text(item.get("sha")),
            branch=_text(item.get("ref")),
            status=_text(item.get("status")),
            conclusion=_text(item.get("conclusion") or item.get("status")),
            started_at=_text(item.get("created_at") or item.get("started_at")),
            completed_at=_text(item.get("finished_at")),
            url=_text(item.get("web_url")),
        )
        for item in payload.get("pipelines", ())
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=_access(scopes=payload.get("scopes", ("read_api", "read_repository")), capabilities=(Capability.REPOSITORY, Capability.COMMITS, Capability.BRANCHES, Capability.CHANGE_REQUESTS, Capability.REVIEWS, Capability.CI_RUNS, Capability.WORK_ITEMS)),
        snapshot=snapshot,
        change_requests=changes,
        ci_runs=runs,
    )
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


def adapt_bitbucket_payload(payload: Mapping[str, Any]) -> AdapterResult:
    repo = payload.get("repository") or {}
    repository_id = _text(repo.get("uuid") or repo.get("id"))
    revision = _text(payload.get("revision") or payload.get("commit_hash"))
    identity = ProviderIdentity(
        ProviderKind.BITBUCKET,
        _text(payload.get("instance_url") or "https://bitbucket.org"),
        _text((repo.get("workspace") or {}).get("slug") or repo.get("project_key")),
        _text(repo.get("slug") or repo.get("name")),
        repository_id,
        _text(((repo.get("mainbranch") or {}).get("name")) or repo.get("default_branch") or "main"),
    )
    snapshot = SnapshotIdentity(ProviderKind.BITBUCKET, repository_id, revision, _text(payload.get("collected_at")), _fingerprint(ProviderKind.BITBUCKET, repository_id, revision))
    changes = tuple(
        CanonicalChangeRequest(
            provider=ProviderKind.BITBUCKET,
            native_id=_text(item.get("id")),
            title=_text(item.get("title")),
            state=_text(item.get("state")),
            source_branch=_text((((item.get("source") or {}).get("branch") or {}).get("name"))),
            target_branch=_text((((item.get("destination") or {}).get("branch") or {}).get("name"))),
            author=_text(((item.get("author") or {}).get("display_name"))),
            created_at=_text(item.get("created_on")),
            updated_at=_text(item.get("updated_on")),
            merged_at=_text(item.get("merge_commit", {}).get("date") if isinstance(item.get("merge_commit"), Mapping) else ""),
            review_state=_text(item.get("review_state") or "unknown"),
        )
        for item in payload.get("pull_requests", ())
    )
    runs = tuple(
        CanonicalCIRun(
            provider=ProviderKind.BITBUCKET,
            native_id=_text(item.get("uuid") or item.get("build_number")),
            name=_text(item.get("name") or "pipeline"),
            revision=_text(((item.get("target") or {}).get("commit") or {}).get("hash") or item.get("revision")),
            branch=_text(((item.get("target") or {}).get("ref_name")) or item.get("branch")),
            status=_text(item.get("state", {}).get("name") if isinstance(item.get("state"), Mapping) else item.get("state")),
            conclusion=_text(item.get("result") or (item.get("state", {}).get("result", {}).get("name") if isinstance(item.get("state"), Mapping) else "")),
            started_at=_text(item.get("created_on")),
            completed_at=_text(item.get("completed_on")),
            url=_text((item.get("links") or {}).get("html", {}).get("href") if isinstance((item.get("links") or {}).get("html"), Mapping) else ""),
        )
        for item in payload.get("pipelines", ())
    )
    envelope = ProviderEvidenceEnvelope(identity, _access(scopes=payload.get("scopes", ("repository:read", "pullrequest:read", "pipeline:read")), capabilities=(Capability.REPOSITORY, Capability.COMMITS, Capability.BRANCHES, Capability.CHANGE_REQUESTS, Capability.REVIEWS, Capability.CI_RUNS)), snapshot, changes, runs)
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


def adapt_azure_devops_payload(payload: Mapping[str, Any]) -> AdapterResult:
    repo = payload.get("repository") or {}
    project = repo.get("project") or payload.get("project") or {}
    repository_id = _text(repo.get("id"))
    revision = _text(payload.get("revision") or payload.get("commit_id"))
    identity = ProviderIdentity(ProviderKind.AZURE_DEVOPS, _text(payload.get("instance_url") or "https://dev.azure.com"), _text(project.get("name") or project.get("id")), _text(repo.get("name")), repository_id, _text(repo.get("defaultBranch") or "refs/heads/main").removeprefix("refs/heads/"))
    snapshot = SnapshotIdentity(ProviderKind.AZURE_DEVOPS, repository_id, revision, _text(payload.get("collected_at")), _fingerprint(ProviderKind.AZURE_DEVOPS, repository_id, revision))
    changes = tuple(
        CanonicalChangeRequest(
            provider=ProviderKind.AZURE_DEVOPS,
            native_id=_text(item.get("pullRequestId")),
            title=_text(item.get("title")),
            state=_text(item.get("status")),
            source_branch=_text(item.get("sourceRefName")).removeprefix("refs/heads/"),
            target_branch=_text(item.get("targetRefName")).removeprefix("refs/heads/"),
            author=_text((item.get("createdBy") or {}).get("displayName")),
            created_at=_text(item.get("creationDate")),
            updated_at=_text(item.get("closedDate") or item.get("creationDate")),
            merged_at=_text(item.get("closedDate") if _text(item.get("status")).lower() == "completed" else ""),
            review_state=_text(item.get("review_state") or "unknown"),
        )
        for item in payload.get("pull_requests", ())
    )
    runs = tuple(
        CanonicalCIRun(
            provider=ProviderKind.AZURE_DEVOPS,
            native_id=_text(item.get("id")),
            name=_text(item.get("definition", {}).get("name") if isinstance(item.get("definition"), Mapping) else item.get("name")),
            revision=_text(item.get("sourceVersion")),
            branch=_text(item.get("sourceBranch")).removeprefix("refs/heads/"),
            status=_text(item.get("status")),
            conclusion=_text(item.get("result")),
            started_at=_text(item.get("startTime") or item.get("queueTime")),
            completed_at=_text(item.get("finishTime")),
            url=_text(item.get("url")),
        )
        for item in payload.get("builds", ())
    )
    envelope = ProviderEvidenceEnvelope(identity, _access(scopes=payload.get("scopes", ("vso.code", "vso.build", "vso.work")), capabilities=(Capability.REPOSITORY, Capability.COMMITS, Capability.BRANCHES, Capability.CHANGE_REQUESTS, Capability.REVIEWS, Capability.CI_RUNS, Capability.WORK_ITEMS)), snapshot, changes, runs)
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


def adapt_offline_source(payload: Mapping[str, Any], *, archive: bool = False) -> AdapterResult:
    provider = ProviderKind.ARCHIVE if archive else ProviderKind.GENERIC_GIT
    repository_id = _text(payload.get("repository_id") or payload.get("source_uri") or payload.get("filename"))
    revision = _text(payload.get("revision") or payload.get("content_hash"))
    identity = ProviderIdentity(provider, _text(payload.get("instance_url") or "offline"), _text(payload.get("namespace")), _text(payload.get("repository") or payload.get("filename")), repository_id, _text(payload.get("default_branch") or "main"))
    capabilities = (Capability.REPOSITORY,) if archive else (Capability.REPOSITORY, Capability.COMMITS, Capability.BRANCHES)
    access = _access(scopes=("offline_read_only",), capabilities=capabilities, partial=bool(payload.get("partial_access")), reason=_text(payload.get("limitation_reason")))
    snapshot = SnapshotIdentity(provider, repository_id, revision, _text(payload.get("collected_at")), _text(payload.get("source_fingerprint") or _fingerprint(provider, repository_id, revision)))
    envelope = ProviderEvidenceEnvelope(identity, access, snapshot)
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


__all__ = [
    "AdapterResult",
    "adapt_azure_devops_payload",
    "adapt_bitbucket_payload",
    "adapt_gitlab_payload",
    "adapt_offline_source",
]
