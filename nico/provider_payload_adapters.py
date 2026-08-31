from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urlencode

from nico.provider_neutral_contract import (
    CanonicalCIJob,
    CanonicalCIRun,
    CanonicalChangeRequest,
    CanonicalDeployment,
    CanonicalEnvironment,
    CanonicalExactSourceLocator,
    CanonicalRelease,
    CanonicalRepositoryRef,
    CanonicalSourceObject,
    Capability,
    CapabilityState,
    ProviderAccess,
    ProviderCapabilityStatus,
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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fingerprint(provider: ProviderKind, repository_id: str, revision: str) -> str:
    payload = f"{provider.value}:{repository_id}:{revision}".encode("utf-8")
    return f"sha256:{sha256(payload).hexdigest()}"


def _source_fingerprint(
    payload: Mapping[str, Any],
    provider: ProviderKind,
    repository_id: str,
    revision: str,
) -> str:
    value = _text(payload.get("snapshot_manifest_sha256"))
    return value or _fingerprint(provider, repository_id, revision)


def _capability_status(payload: Mapping[str, Any]) -> tuple[ProviderCapabilityStatus, ...]:
    priority = {
        CapabilityState.SUPPORTED: 0,
        CapabilityState.SUPPORTED_EMPTY: 1,
        CapabilityState.SUPPORTED_LIMITED: 2,
        CapabilityState.NOT_ASSESSED: 3,
        CapabilityState.NOT_CONFIGURED: 4,
        CapabilityState.NOT_APPLICABLE: 5,
        CapabilityState.UNAVAILABLE_PROVIDER: 6,
        CapabilityState.UNAVAILABLE_CONFIGURATION: 7,
        CapabilityState.UNAVAILABLE_AUTHENTICATION: 8,
        CapabilityState.UNAVAILABLE_PERMISSION: 9,
        CapabilityState.RATE_LIMITED: 10,
        CapabilityState.COLLECTION_FAILED: 11,
        CapabilityState.UNSUPPORTED: 12,
    }
    selected: dict[Capability, ProviderCapabilityStatus] = {}
    for raw in _sequence(payload.get("capability_status")):
        if not isinstance(raw, Mapping):
            continue
        try:
            capability = Capability(_text(raw.get("capability")).lower())
            state = CapabilityState(_text(raw.get("state")).lower())
        except ValueError:
            continue
        candidate = ProviderCapabilityStatus(
            capability=capability,
            state=state,
            reason=_text(raw.get("reason")),
        )
        current = selected.get(capability)
        if current is None or priority[state] > priority[current.state]:
            selected[capability] = candidate
    return tuple(selected[key] for key in sorted(selected, key=lambda item: item.value))


def _access(
    *,
    scopes: Iterable[str],
    capabilities: Iterable[Capability],
    partial: bool = False,
    reason: str = "",
    access_mode: str = "authenticated_read_only",
    credential_used: bool = True,
) -> ProviderAccess:
    return ProviderAccess(
        read_only=True,
        scopes=tuple(_text(item) for item in scopes if _text(item)),
        capabilities=tuple(dict.fromkeys(capabilities)),
        partial_access=partial,
        limitation_reason=_text(reason),
        access_mode=_text(access_mode, empty="authenticated_read_only"),
        credential_used=bool(credential_used),
    )


def _supported_capabilities(
    statuses: Iterable[ProviderCapabilityStatus],
    defaults: Iterable[Capability],
) -> tuple[Capability, ...]:
    values = list(defaults)
    for status in statuses:
        if status.state in {
            CapabilityState.SUPPORTED,
            CapabilityState.SUPPORTED_EMPTY,
            CapabilityState.SUPPORTED_LIMITED,
        }:
            values.append(status.capability)
    return tuple(dict.fromkeys(values))


def _limitations(payload: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        _text(item)
        for item in _sequence(payload.get("collection_limitations"))
        if _text(item)
    )


def _gitlab_source_url(project: Mapping[str, Any], instance: str, revision: str, path: str) -> str:
    base = _text(project.get("web_url"))
    if not base:
        namespace = _text(project.get("path_with_namespace"))
        base = f"{instance.rstrip('/')}/{namespace}" if namespace else instance.rstrip("/")
    return f"{base}/-/blob/{quote(revision, safe='')}/{quote(path, safe='/')}"


def _bitbucket_source_url(repo: Mapping[str, Any], instance: str, revision: str, path: str) -> str:
    workspace = _text(_mapping(repo.get("workspace")).get("slug"))
    slug = _text(repo.get("slug") or repo.get("name"))
    base = instance.replace("api.bitbucket.org", "bitbucket.org").rstrip("/")
    return (
        f"{base}/{quote(workspace, safe='')}/{quote(slug, safe='')}/src/"
        f"{quote(revision, safe='')}/{quote(path, safe='/')}"
    )


def _azure_source_url(
    payload: Mapping[str, Any],
    repo: Mapping[str, Any],
    revision: str,
    path: str,
) -> str:
    instance = _text(payload.get("instance_url") or "https://dev.azure.com").rstrip("/")
    organization = _text(payload.get("organization"))
    project = _text(_mapping(repo.get("project") or payload.get("project")).get("name"))
    repository = _text(repo.get("name") or repo.get("id"))
    params = urlencode({"path": "/" + path.lstrip("/"), "version": f"GC{revision}"})
    return (
        f"{instance}/{quote(organization, safe='')}/{quote(project, safe='')}/_git/"
        f"{quote(repository, safe='')}?{params}"
    )


def adapt_gitlab_payload(payload: Mapping[str, Any]) -> AdapterResult:
    project = _mapping(payload.get("project"))
    repository_id = _text(project.get("id"))
    revision = _text(payload.get("revision") or payload.get("commit_sha"))
    instance = _text(payload.get("instance_url") or "https://gitlab.com")
    namespace = _text(project.get("namespace") or _text(project.get("path_with_namespace")).rsplit("/", 1)[0])
    repository = _text(project.get("path") or project.get("name"))
    identity = ProviderIdentity(
        ProviderKind.GITLAB,
        instance,
        namespace,
        repository,
        repository_id,
        _text(project.get("default_branch") or "main"),
    )
    snapshot = SnapshotIdentity(
        ProviderKind.GITLAB,
        repository_id,
        revision,
        _text(payload.get("collected_at")),
        _source_fingerprint(payload, ProviderKind.GITLAB, repository_id, revision),
    )
    changes = tuple(
        CanonicalChangeRequest(
            provider=ProviderKind.GITLAB,
            native_id=_text(item.get("iid") or item.get("id")),
            title=_text(item.get("title")),
            state=_text(item.get("state")),
            source_branch=_text(item.get("source_branch")),
            target_branch=_text(item.get("target_branch")),
            author=_text(_mapping(item.get("author")).get("username") or item.get("author")),
            created_at=_text(item.get("created_at")),
            updated_at=_text(item.get("updated_at")),
            merged_at=_text(item.get("merged_at")),
            review_state=_text(item.get("detailed_merge_status") or item.get("review_state") or "unknown"),
        )
        for item in _sequence(payload.get("merge_requests"))
        if isinstance(item, Mapping)
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
        for item in _sequence(payload.get("pipelines"))
        if isinstance(item, Mapping)
    )
    source_objects = tuple(
        CanonicalSourceObject(
            provider=ProviderKind.GITLAB,
            repository_id=repository_id,
            revision=revision,
            path=_text(item.get("path")),
            object_id=_text(item.get("id")),
            object_type=_text(item.get("type")),
            size=_int_or_none(item.get("size")),
            mode=_text(item.get("mode")),
            exact_url=_gitlab_source_url(project, instance, revision, _text(item.get("path"))),
        )
        for item in _sequence(payload.get("source_tree"))
        if isinstance(item, Mapping)
    )
    tags = tuple(
        CanonicalRepositoryRef(
            provider=ProviderKind.GITLAB,
            repository_id=repository_id,
            name=_text(item.get("name")),
            target_revision=_text(_mapping(item.get("commit")).get("id") or item.get("target")),
            ref_type="tag",
        )
        for item in _sequence(payload.get("tags"))
        if isinstance(item, Mapping)
    )
    jobs = tuple(
        CanonicalCIJob(
            provider=ProviderKind.GITLAB,
            run_id=_text(item.get("pipeline_id") or _mapping(item.get("pipeline")).get("id")),
            native_id=_text(item.get("id")),
            name=_text(item.get("name")),
            stage=_text(item.get("stage")),
            status=_text(item.get("status")),
            conclusion=_text(item.get("status")),
            started_at=_text(item.get("started_at") or item.get("created_at")),
            completed_at=_text(item.get("finished_at")),
            url=_text(item.get("web_url")),
            artifact_references=tuple(
                _text(value)
                for value in (
                    _mapping(item.get("artifacts_file")).get("filename"),
                    *(
                        _mapping(entry).get("filename")
                        for entry in _sequence(item.get("artifacts"))
                    ),
                )
                if _text(value)
            ),
        )
        for item in _sequence(payload.get("pipeline_jobs"))
        if isinstance(item, Mapping)
    )
    environments = tuple(
        CanonicalEnvironment(
            provider=ProviderKind.GITLAB,
            native_id=_text(item.get("id")),
            name=_text(item.get("name")),
            state=_text(item.get("state")),
            tier=_text(item.get("tier")),
            url=_text(item.get("external_url")),
        )
        for item in _sequence(payload.get("environments"))
        if isinstance(item, Mapping)
    )
    deployments = tuple(
        CanonicalDeployment(
            provider=ProviderKind.GITLAB,
            native_id=_text(item.get("id") or item.get("iid")),
            environment_id=_text(_mapping(item.get("environment")).get("id")),
            environment_name=_text(_mapping(item.get("environment")).get("name")),
            revision=_text(item.get("sha") or _mapping(item.get("deployable")).get("commit", {}).get("id")),
            status=_text(item.get("status")),
            created_at=_text(item.get("created_at")),
            completed_at=_text(item.get("finished_at") or item.get("updated_at")),
            url=_text(item.get("web_url")),
        )
        for item in _sequence(payload.get("deployments"))
        if isinstance(item, Mapping)
    )
    releases = tuple(
        CanonicalRelease(
            provider=ProviderKind.GITLAB,
            native_id=_text(item.get("tag_name") or item.get("name")),
            name=_text(item.get("name") or item.get("tag_name")),
            tag_name=_text(item.get("tag_name")),
            revision=_text(_mapping(item.get("commit")).get("id")),
            created_at=_text(item.get("created_at")),
            released_at=_text(item.get("released_at")),
            url=_text(_mapping(item.get("_links")).get("self")),
            artifact_references=tuple(
                _text(link.get("url"))
                for link in _sequence(_mapping(item.get("assets")).get("links"))
                if isinstance(link, Mapping) and _text(link.get("url"))
            ),
        )
        for item in _sequence(payload.get("releases"))
        if isinstance(item, Mapping)
    )
    statuses = _capability_status(payload)
    limitations = _limitations(payload)
    defaults = (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
        Capability.WORK_ITEMS,
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=_access(
            scopes=payload.get("scopes", ("read_api", "read_repository")),
            capabilities=_supported_capabilities(statuses, defaults),
            partial=bool(limitations) or not bool(payload.get("pagination_complete", True)),
            reason="; ".join(limitations),
            access_mode=_text(payload.get("access_mode"), empty="authenticated_read_only"),
            credential_used=bool(payload.get("credential_used", True)),
        ),
        snapshot=snapshot,
        change_requests=changes,
        ci_runs=runs,
        source_objects=source_objects,
        tags=tags,
        exact_source_locators=tuple(
            CanonicalExactSourceLocator(
                provider=item.provider,
                repository_id=item.repository_id,
                revision=item.revision,
                path=item.path,
                object_id=item.object_id,
                exact_url=item.exact_url,
            )
            for item in source_objects
            if item.object_type in {"blob", "file"}
        ),
        ci_jobs=jobs,
        environments=environments,
        deployments=deployments,
        releases=releases,
        capability_status=statuses,
        pagination_complete=bool(payload.get("pagination_complete", True)),
        collection_limitations=limitations,
    )
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


def adapt_bitbucket_payload(payload: Mapping[str, Any]) -> AdapterResult:
    repo = _mapping(payload.get("repository"))
    repository_id = _text(repo.get("uuid") or repo.get("id"))
    revision = _text(payload.get("revision") or payload.get("commit_hash"))
    instance = _text(payload.get("instance_url") or "https://bitbucket.org")
    identity = ProviderIdentity(
        ProviderKind.BITBUCKET,
        instance,
        _text(_mapping(repo.get("workspace")).get("slug") or repo.get("project_key")),
        _text(repo.get("slug") or repo.get("name")),
        repository_id,
        _text(_mapping(repo.get("mainbranch")).get("name") or repo.get("default_branch") or "main"),
    )
    snapshot = SnapshotIdentity(
        ProviderKind.BITBUCKET,
        repository_id,
        revision,
        _text(payload.get("collected_at")),
        _source_fingerprint(payload, ProviderKind.BITBUCKET, repository_id, revision),
    )
    changes = tuple(
        CanonicalChangeRequest(
            provider=ProviderKind.BITBUCKET,
            native_id=_text(item.get("id")),
            title=_text(item.get("title")),
            state=_text(item.get("state")),
            source_branch=_text(_mapping(_mapping(item.get("source")).get("branch")).get("name")),
            target_branch=_text(_mapping(_mapping(item.get("destination")).get("branch")).get("name")),
            author=_text(_mapping(item.get("author")).get("display_name")),
            created_at=_text(item.get("created_on")),
            updated_at=_text(item.get("updated_on")),
            merged_at=_text(_mapping(item.get("merge_commit")).get("date")),
            review_state=_text(item.get("review_state") or "unknown"),
        )
        for item in _sequence(payload.get("pull_requests"))
        if isinstance(item, Mapping)
    )
    runs = tuple(
        CanonicalCIRun(
            provider=ProviderKind.BITBUCKET,
            native_id=_text(item.get("uuid") or item.get("build_number")),
            name=_text(item.get("name") or "pipeline"),
            revision=_text(_mapping(_mapping(item.get("target")).get("commit")).get("hash") or item.get("revision")),
            branch=_text(_mapping(item.get("target")).get("ref_name") or item.get("branch")),
            status=_text(_mapping(item.get("state")).get("name") or item.get("state")),
            conclusion=_text(_mapping(_mapping(item.get("state")).get("result")).get("name") or item.get("result")),
            started_at=_text(item.get("created_on")),
            completed_at=_text(item.get("completed_on")),
            url=_text(_mapping(_mapping(item.get("links")).get("html")).get("href")),
        )
        for item in _sequence(payload.get("pipelines"))
        if isinstance(item, Mapping)
    )
    source_objects = tuple(
        CanonicalSourceObject(
            provider=ProviderKind.BITBUCKET,
            repository_id=repository_id,
            revision=revision,
            path=_text(item.get("path")),
            object_id=_text(
                item.get("id")
                or _mapping(item.get("commit")).get("hash")
                or _mapping(_mapping(item.get("links")).get("self")).get("href")
            ),
            object_type=_text(item.get("type") or "file"),
            size=_int_or_none(item.get("size")),
            mode=_text(item.get("attributes")),
            exact_url=_bitbucket_source_url(repo, instance, revision, _text(item.get("path"))),
        )
        for item in _sequence(payload.get("source_tree"))
        if isinstance(item, Mapping)
    )
    tags = tuple(
        CanonicalRepositoryRef(
            provider=ProviderKind.BITBUCKET,
            repository_id=repository_id,
            name=_text(item.get("name")),
            target_revision=_text(_mapping(item.get("target")).get("hash")),
            ref_type="tag",
        )
        for item in _sequence(payload.get("tags"))
        if isinstance(item, Mapping)
    )
    jobs = tuple(
        CanonicalCIJob(
            provider=ProviderKind.BITBUCKET,
            run_id=_text(item.get("pipeline_id")),
            native_id=_text(item.get("uuid") or item.get("id")),
            name=_text(item.get("name")),
            stage=_text(item.get("stage")),
            status=_text(_mapping(item.get("state")).get("name") or item.get("state")),
            conclusion=_text(_mapping(_mapping(item.get("state")).get("result")).get("name") or item.get("result")),
            started_at=_text(item.get("started_on") or item.get("created_on")),
            completed_at=_text(item.get("completed_on")),
            url=_text(_mapping(_mapping(item.get("links")).get("html")).get("href")),
        )
        for item in _sequence(payload.get("pipeline_jobs"))
        if isinstance(item, Mapping)
    )
    environments = tuple(
        CanonicalEnvironment(
            provider=ProviderKind.BITBUCKET,
            native_id=_text(item.get("uuid") or item.get("id")),
            name=_text(item.get("name")),
            state=_text(item.get("state")),
            tier=_text(item.get("environment_type")),
        )
        for item in _sequence(payload.get("environments"))
        if isinstance(item, Mapping)
    )
    deployments = tuple(
        CanonicalDeployment(
            provider=ProviderKind.BITBUCKET,
            native_id=_text(item.get("uuid") or item.get("id")),
            environment_id=_text(_mapping(item.get("environment")).get("uuid")),
            environment_name=_text(_mapping(item.get("environment")).get("name")),
            revision=_text(_mapping(_mapping(item.get("pipeline")).get("target")).get("commit", {}).get("hash")),
            status=_text(_mapping(item.get("state")).get("name") or item.get("state")),
            created_at=_text(item.get("created_on")),
            completed_at=_text(item.get("completed_on")),
            url=_text(_mapping(_mapping(item.get("links")).get("html")).get("href")),
        )
        for item in _sequence(payload.get("deployments"))
        if isinstance(item, Mapping)
    )
    statuses = _capability_status(payload)
    limitations = _limitations(payload)
    defaults = (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=_access(
            scopes=payload.get("scopes", ("repository:read", "pullrequest:read", "pipeline:read")),
            capabilities=_supported_capabilities(statuses, defaults),
            partial=bool(limitations) or not bool(payload.get("pagination_complete", True)),
            reason="; ".join(limitations),
            access_mode=_text(payload.get("access_mode"), empty="authenticated_read_only"),
            credential_used=bool(payload.get("credential_used", True)),
        ),
        snapshot=snapshot,
        change_requests=changes,
        ci_runs=runs,
        source_objects=source_objects,
        tags=tags,
        exact_source_locators=tuple(
            CanonicalExactSourceLocator(
                provider=item.provider,
                repository_id=item.repository_id,
                revision=item.revision,
                path=item.path,
                object_id=item.object_id,
                exact_url=item.exact_url,
            )
            for item in source_objects
            if item.object_type in {"commit_file", "file"}
        ),
        ci_jobs=jobs,
        environments=environments,
        deployments=deployments,
        releases=(),
        capability_status=statuses,
        pagination_complete=bool(payload.get("pagination_complete", True)),
        collection_limitations=limitations,
    )
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


def adapt_azure_devops_payload(payload: Mapping[str, Any]) -> AdapterResult:
    repo = _mapping(payload.get("repository"))
    project = _mapping(repo.get("project") or payload.get("project"))
    repository_id = _text(repo.get("id"))
    revision = _text(payload.get("revision") or payload.get("commit_id"))
    instance = _text(payload.get("instance_url") or "https://dev.azure.com")
    identity = ProviderIdentity(
        ProviderKind.AZURE_DEVOPS,
        instance,
        _text(project.get("name") or project.get("id")),
        _text(repo.get("name")),
        repository_id,
        _text(repo.get("defaultBranch") or "refs/heads/main").removeprefix("refs/heads/"),
    )
    snapshot = SnapshotIdentity(
        ProviderKind.AZURE_DEVOPS,
        repository_id,
        revision,
        _text(payload.get("collected_at")),
        _source_fingerprint(payload, ProviderKind.AZURE_DEVOPS, repository_id, revision),
    )
    changes = tuple(
        CanonicalChangeRequest(
            provider=ProviderKind.AZURE_DEVOPS,
            native_id=_text(item.get("pullRequestId")),
            title=_text(item.get("title")),
            state=_text(item.get("status")),
            source_branch=_text(item.get("sourceRefName")).removeprefix("refs/heads/"),
            target_branch=_text(item.get("targetRefName")).removeprefix("refs/heads/"),
            author=_text(_mapping(item.get("createdBy")).get("displayName")),
            created_at=_text(item.get("creationDate")),
            updated_at=_text(item.get("closedDate") or item.get("creationDate")),
            merged_at=_text(item.get("closedDate") if _text(item.get("status")).lower() == "completed" else ""),
            review_state=_text(item.get("review_state") or "unknown"),
        )
        for item in _sequence(payload.get("pull_requests"))
        if isinstance(item, Mapping)
    )
    runs = tuple(
        CanonicalCIRun(
            provider=ProviderKind.AZURE_DEVOPS,
            native_id=_text(item.get("id")),
            name=_text(_mapping(item.get("definition")).get("name") or item.get("name")),
            revision=_text(item.get("sourceVersion")),
            branch=_text(item.get("sourceBranch")).removeprefix("refs/heads/"),
            status=_text(item.get("status")),
            conclusion=_text(item.get("result")),
            started_at=_text(item.get("startTime") or item.get("queueTime")),
            completed_at=_text(item.get("finishTime")),
            url=_text(item.get("url")),
        )
        for item in _sequence(payload.get("builds"))
        if isinstance(item, Mapping)
    )
    source_objects = tuple(
        CanonicalSourceObject(
            provider=ProviderKind.AZURE_DEVOPS,
            repository_id=repository_id,
            revision=revision,
            path=_text(item.get("path")).lstrip("/"),
            object_id=_text(item.get("objectId") or item.get("commitId")),
            object_type=_text(item.get("gitObjectType") or item.get("isFolder") and "tree" or "blob"),
            size=_int_or_none(_mapping(item.get("contentMetadata")).get("fileSize")),
            exact_url=_azure_source_url(payload, repo, revision, _text(item.get("path")).lstrip("/")),
        )
        for item in _sequence(payload.get("source_tree"))
        if isinstance(item, Mapping)
    )
    tags = tuple(
        CanonicalRepositoryRef(
            provider=ProviderKind.AZURE_DEVOPS,
            repository_id=repository_id,
            name=_text(item.get("name")).removeprefix("refs/tags/"),
            target_revision=_text(item.get("objectId")),
            ref_type="tag",
        )
        for item in _sequence(payload.get("tags"))
        if isinstance(item, Mapping)
    )
    jobs = tuple(
        CanonicalCIJob(
            provider=ProviderKind.AZURE_DEVOPS,
            run_id=_text(item.get("build_id")),
            native_id=_text(item.get("id")),
            name=_text(item.get("name")),
            stage=_text(item.get("type")),
            status=_text(item.get("state")),
            conclusion=_text(item.get("result")),
            started_at=_text(item.get("startTime")),
            completed_at=_text(item.get("finishTime")),
            url=_text(item.get("url")),
        )
        for item in _sequence(payload.get("pipeline_jobs"))
        if isinstance(item, Mapping)
    )
    environments = tuple(
        CanonicalEnvironment(
            provider=ProviderKind.AZURE_DEVOPS,
            native_id=_text(item.get("id")),
            name=_text(item.get("name")),
            state=_text(item.get("status")),
            tier=_text(item.get("description")),
        )
        for item in _sequence(payload.get("environments"))
        if isinstance(item, Mapping)
    )
    deployments = tuple(
        CanonicalDeployment(
            provider=ProviderKind.AZURE_DEVOPS,
            native_id=_text(item.get("id") or item.get("deploymentAttempt")),
            environment_id=_text(item.get("environment_id") or _mapping(item.get("environment")).get("id")),
            environment_name=_text(_mapping(item.get("environment")).get("name")),
            revision=_text(item.get("sourceVersion") or _mapping(item.get("owner")).get("version")),
            status=_text(item.get("result") or item.get("status")),
            created_at=_text(item.get("startTime") or item.get("createdOn")),
            completed_at=_text(item.get("finishTime") or item.get("lastModifiedOn")),
            url=_text(item.get("url")),
        )
        for item in _sequence(payload.get("deployments"))
        if isinstance(item, Mapping)
    )
    statuses = _capability_status(payload)
    limitations = _limitations(payload)
    defaults = (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
        Capability.CHANGE_REQUESTS,
        Capability.REVIEWS,
        Capability.CI_RUNS,
        Capability.WORK_ITEMS,
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=_access(
            scopes=payload.get("scopes", ("vso.code", "vso.build", "vso.work")),
            capabilities=_supported_capabilities(statuses, defaults),
            partial=bool(limitations) or not bool(payload.get("pagination_complete", True)),
            reason="; ".join(limitations),
            access_mode=_text(payload.get("access_mode"), empty="authenticated_read_only"),
            credential_used=bool(payload.get("credential_used", True)),
        ),
        snapshot=snapshot,
        change_requests=changes,
        ci_runs=runs,
        source_objects=source_objects,
        tags=tags,
        exact_source_locators=tuple(
            CanonicalExactSourceLocator(
                provider=item.provider,
                repository_id=item.repository_id,
                revision=item.revision,
                path=item.path,
                object_id=item.object_id,
                exact_url=item.exact_url,
            )
            for item in source_objects
            if item.object_type in {"blob", "file"}
        ),
        ci_jobs=jobs,
        environments=environments,
        deployments=deployments,
        releases=(),
        capability_status=statuses,
        pagination_complete=bool(payload.get("pagination_complete", True)),
        collection_limitations=limitations,
    )
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


def adapt_offline_source(payload: Mapping[str, Any], *, archive: bool = False) -> AdapterResult:
    provider = ProviderKind.ARCHIVE if archive else ProviderKind.GENERIC_GIT
    repository_id = _text(payload.get("repository_id") or payload.get("source_uri") or payload.get("filename"))
    revision = _text(payload.get("revision") or payload.get("content_hash"))
    identity = ProviderIdentity(
        provider,
        _text(payload.get("instance_url") or "offline"),
        _text(payload.get("namespace")),
        _text(payload.get("repository") or payload.get("filename")),
        repository_id,
        _text(payload.get("default_branch") or "main"),
    )
    capabilities = (Capability.REPOSITORY,) if archive else (
        Capability.REPOSITORY,
        Capability.COMMITS,
        Capability.BRANCHES,
    )
    access = _access(
        scopes=("offline_read_only",),
        capabilities=capabilities,
        partial=bool(payload.get("partial_access")),
        reason=_text(payload.get("limitation_reason")),
    )
    snapshot = SnapshotIdentity(
        provider,
        repository_id,
        revision,
        _text(payload.get("collected_at")),
        _text(payload.get("source_fingerprint") or _fingerprint(provider, repository_id, revision)),
    )
    envelope = ProviderEvidenceEnvelope(identity, access, snapshot)
    return AdapterResult(envelope, tuple(validate_provider_envelope(envelope)))


__all__ = [
    "AdapterResult",
    "adapt_azure_devops_payload",
    "adapt_bitbucket_payload",
    "adapt_gitlab_payload",
    "adapt_offline_source",
]
