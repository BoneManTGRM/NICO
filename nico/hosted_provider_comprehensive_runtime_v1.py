from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from nico import comprehensive_api_routes as api_routes
from nico import comprehensive_native_providers as native
from nico import snapshot_scanner_worker as snapshot_worker
from nico.admin_security import require_admin_write
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.exact_commit_binding import expected_commit_sha
from nico.full_assessment_complexity_evidence import collect_complexity_evidence
from nico.hosted_assessment import (
    KNOWN_FILE_PATHS,
    MAX_FILE_BYTES,
    MAX_TEXT_FILES,
    collect_dependencies,
    normalize_repository,
    should_fetch_path,
)
from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_live_clients import AzureDevOpsClient, BitbucketCloudClient, GitLabClient, RetryPolicy
from nico.provider_neutral_contract import ProviderAccessMode
from nico.provider_neutral_contract import ProviderKind as NeutralProviderKind
from nico.provider_platform_contract_v1 import ProviderKind
from nico.provider_rollout_control_v1 import ProviderRolloutRegistry, STATE_KEY as ROLLOUT_STATE_KEY
from nico.repository_snapshot import capture_repository_snapshot, repository_snapshot_id
from nico.source_signal_analysis_v2 import analyze_source_signals
from nico.storage import STORE, StorageAdapter

VERSION = "nico.hosted-provider-comprehensive-runtime.v1"
OPERATOR_INTAKE_ROUTE = "/providers/operator/comprehensive-intake"
_PATCH_MARKER = "_nico_hosted_provider_checkout_v1"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_VISUAL_STUDIO_HOST_RE = re.compile(r"^([a-z0-9-]+)\.visualstudio\.com$", re.I)

_HOSTED = {
    ProviderKind.GITHUB,
    ProviderKind.GITLAB,
    ProviderKind.BITBUCKET_CLOUD,
    ProviderKind.AZURE_DEVOPS,
}
_TOKEN_ENV = {
    ProviderKind.GITLAB: "NICO_GITLAB_TOKEN",
    ProviderKind.BITBUCKET_CLOUD: "NICO_BITBUCKET_CLOUD_TOKEN",
    ProviderKind.AZURE_DEVOPS: "NICO_AZURE_DEVOPS_TOKEN",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _required(value: Any, field: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def _provider(value: Any) -> ProviderKind:
    token = _text(value).casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "github": ProviderKind.GITHUB,
        "github.com": ProviderKind.GITHUB,
        "gitlab": ProviderKind.GITLAB,
        "gitlab.com": ProviderKind.GITLAB,
        "bitbucket": ProviderKind.BITBUCKET_CLOUD,
        "bitbucket_cloud": ProviderKind.BITBUCKET_CLOUD,
        "bitbucket.org": ProviderKind.BITBUCKET_CLOUD,
        "azure": ProviderKind.AZURE_DEVOPS,
        "azure_devops": ProviderKind.AZURE_DEVOPS,
        "azure_repos": ProviderKind.AZURE_DEVOPS,
        "dev.azure.com": ProviderKind.AZURE_DEVOPS,
    }
    selected = aliases.get(token)
    if selected not in _HOSTED:
        raise ValueError("provider_not_supported")
    return selected


def _access_mode(value: Any) -> ProviderAccessMode:
    normalized = _text(value).casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "": ProviderAccessMode.AUTO,
        "auto": ProviderAccessMode.AUTO,
        "anonymous_public": ProviderAccessMode.ANONYMOUS_PUBLIC,
        "anonymous": ProviderAccessMode.ANONYMOUS_PUBLIC,
        "public": ProviderAccessMode.ANONYMOUS_PUBLIC,
        "authenticated_read_only": ProviderAccessMode.AUTHENTICATED_READ_ONLY,
        "authenticated": ProviderAccessMode.AUTHENTICATED_READ_ONLY,
        "read_only": ProviderAccessMode.AUTHENTICATED_READ_ONLY,
    }
    selected = aliases.get(normalized)
    if selected is None:
        raise ValueError("provider_access_mode_invalid")
    return selected


def assert_no_raw_provider_credentials(payload: Mapping[str, Any]) -> None:
    forbidden = {
        "token",
        "access_token",
        "private_token",
        "password",
        "secret",
        "credential",
        "credentials",
        "authorization",
        "api_key",
    }
    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if str(key).casefold() in forbidden:
                    raise ValueError("raw_provider_credentials_prohibited")
                visit(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                visit(nested)

    visit(payload)


def _safe_segment(value: Any, error: str = "provider_repository_invalid") -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or not _SAFE_SEGMENT_RE.fullmatch(normalized)
    ):
        raise ValueError(error)
    return normalized


def _safe_path(value: Any, *, minimum_parts: int = 2) -> str:
    raw = str(value or "").strip()
    if not raw or raw.startswith("/") or raw.endswith("/"):
        raise ValueError("provider_repository_invalid")
    if (
        "://" in raw
        or "\\" in raw
        or "\x00" in raw
        or "\r" in raw
        or "\n" in raw
    ):
        raise ValueError("provider_repository_invalid")
    parts = raw.split("/")
    if len(parts) < minimum_parts:
        raise ValueError("provider_repository_invalid")
    return "/".join(_safe_segment(part) for part in parts)


def _strip_git_suffix(value: str) -> str:
    return value[:-4] if value.lower().endswith(".git") else value


def _absolute_repository_url(value: Any) -> Any:
    raw = str(value or "").strip()
    if not raw.lower().startswith("https://"):
        return None
    parsed = urlparse(raw)
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("provider_repository_invalid")
    return parsed


def _path_parts(parsed: Any) -> list[str]:
    return [part.strip() for part in parsed.path.split("/") if part.strip()]


def _normalize_shorthand_repository(
    provider: ProviderKind,
    repository: str,
    *,
    organization: str = "",
    project: str = "",
) -> tuple[ProviderKind, str, str, str]:
    if provider is ProviderKind.GITHUB:
        return provider, normalize_repository(repository), "", ""
    if provider is ProviderKind.GITLAB:
        parts = _safe_path(repository, minimum_parts=2).split("/")
        parts[-1] = _strip_git_suffix(parts[-1])
        return provider, "/".join(parts), "", ""
    if provider is ProviderKind.BITBUCKET_CLOUD:
        path = _safe_path(repository, minimum_parts=2).split("/")
        if len(path) != 2:
            raise ValueError("bitbucket_repository_coordinates_invalid")
        path[-1] = _strip_git_suffix(path[-1])
        return provider, "/".join(path), "", ""
    if provider is ProviderKind.AZURE_DEVOPS:
        repo = _text(repository)
        org = _text(organization)
        project_name = _text(project)
        if "/" in repo:
            parts = _safe_path(repo, minimum_parts=3).split("/")
            if len(parts) != 3:
                raise ValueError("azure_provider_coordinates_invalid")
            org, project_name, repo = parts
        else:
            repo = _safe_path(repo, minimum_parts=1)
            if "/" in repo:
                raise ValueError("azure_repository_name_invalid")
            org = _safe_segment(org, "azure_provider_coordinates_invalid")
            project_name = _safe_segment(
                project_name, "azure_provider_coordinates_invalid"
            )
        return provider, _strip_git_suffix(repo), org, project_name
    raise ValueError("provider_not_supported")


def normalize_submitted_provider_repository(
    repository: Any,
    provider: Any,
    *,
    organization: Any = "",
    project: Any = "",
) -> tuple[ProviderKind, str, str, str]:
    raw_repository = _required(repository, "repository")
    selected_provider = _provider(provider or "github")
    parsed = _absolute_repository_url(raw_repository)
    if parsed is None:
        return _normalize_shorthand_repository(
            selected_provider,
            raw_repository,
            organization=_text(organization),
            project=_text(project),
        )

    host = (parsed.hostname or "").lower().rstrip(".")
    detected_provider = (
        ProviderKind.GITHUB
        if host == "github.com"
        else ProviderKind.GITLAB
        if host == "gitlab.com"
        else ProviderKind.BITBUCKET_CLOUD
        if host == "bitbucket.org"
        else ProviderKind.AZURE_DEVOPS
        if host == "dev.azure.com" or _VISUAL_STUDIO_HOST_RE.fullmatch(host)
        else None
    )
    if detected_provider is None:
        raise ValueError("provider_repository_host_not_supported")
    if selected_provider is not detected_provider:
        raise ValueError("provider_repository_selection_mismatch")

    parts = _path_parts(parsed)
    if selected_provider is ProviderKind.GITHUB:
        if host != "github.com" or len(parts) != 2:
            raise ValueError("github_repository_url_invalid")
        return _normalize_shorthand_repository(
            selected_provider,
            f"{parts[0]}/{_strip_git_suffix(parts[1])}",
        )
    if selected_provider is ProviderKind.GITLAB:
        if host != "gitlab.com" or len(parts) < 2 or "-" in parts:
            raise ValueError("gitlab_repository_url_invalid")
        parts[-1] = _strip_git_suffix(parts[-1])
        return _normalize_shorthand_repository(selected_provider, "/".join(parts))
    if selected_provider is ProviderKind.BITBUCKET_CLOUD:
        if host != "bitbucket.org" or len(parts) != 2:
            raise ValueError("bitbucket_repository_url_invalid")
        return _normalize_shorthand_repository(
            selected_provider,
            f"{parts[0]}/{_strip_git_suffix(parts[1])}",
        )

    if host == "dev.azure.com":
        if len(parts) != 4 or parts[2].lower() != "_git":
            raise ValueError("azure_repository_url_invalid")
        return _normalize_shorthand_repository(
            selected_provider,
            _strip_git_suffix(parts[3]),
            organization=parts[0],
            project=parts[1],
        )
    visual_studio = _VISUAL_STUDIO_HOST_RE.fullmatch(host)
    if not visual_studio or len(parts) != 3 or parts[1].lower() != "_git":
        raise ValueError("azure_repository_url_invalid")
    return _normalize_shorthand_repository(
        selected_provider,
        _strip_git_suffix(parts[2]),
        organization=visual_studio.group(1),
        project=parts[0],
    )


def canonical_repository_label(
    provider: ProviderKind,
    repository: str,
    *,
    organization: str = "",
    project: str = "",
) -> str:
    if provider is ProviderKind.GITHUB:
        return normalize_repository(repository)
    if provider is ProviderKind.GITLAB:
        return "gitlab.com/" + _safe_path(repository)
    if provider is ProviderKind.BITBUCKET_CLOUD:
        path = _safe_path(repository, minimum_parts=2)
        if len(path.split("/")) != 2:
            raise ValueError("bitbucket_repository_coordinates_invalid")
        return "bitbucket.org/" + path
    if provider is ProviderKind.AZURE_DEVOPS:
        org = _safe_segment(
            _required(organization, "provider_organization"),
            "azure_provider_coordinates_invalid",
        )
        project_name = _safe_segment(
            _required(project, "provider_project"),
            "azure_provider_coordinates_invalid",
        )
        repo = _safe_path(repository, minimum_parts=1)
        if "/" in repo:
            raise ValueError("azure_repository_name_invalid")
        return f"dev.azure.com/{org}/{project_name}/_git/{repo}"
    raise ValueError("provider_not_supported")


def _hosted_url(value: str, *, host: str, default: str) -> str:
    raw = _text(value) or default
    parsed = urlparse(raw)
    try:
        explicit_port = parsed.port
    except ValueError as exc:
        raise ValueError("hosted_provider_instance_invalid") from exc
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() != host:
        raise ValueError("hosted_provider_instance_invalid")
    if (
        parsed.username
        or parsed.password
        or explicit_port is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("hosted_provider_instance_invalid")
    return f"https://{host}"


def _credential(
    provider: NeutralProviderKind,
    *,
    env_var: str,
    scheme: str,
    key_id: str,
    host: str,
    scopes: tuple[str, ...],
    environ: Mapping[str, str] | None = None,
    required: bool = False,
    resolve_optional: bool = True,
):
    reference = build_reference(
        provider=provider,
        env_var=env_var,
        scheme=scheme,
        key_id=key_id,
        allowed_hosts=(host,),
        scopes=scopes,
    )
    resolver = EnvironmentCredentialResolver(environ)
    credential = (
        resolver.resolve(reference)
        if required
        else resolver.resolve_optional(reference)
        if resolve_optional
        else None
    )
    return reference, credential


def build_hosted_provider_client(
    provider: ProviderKind,
    context: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
):
    selected = os.environ if environ is None else environ
    access_mode = _access_mode(context.get("provider_access_mode"))
    optional_fallback_authorized = (
        access_mode is ProviderAccessMode.AUTO
        and context.get("provider_credential_fallback_authorized") is True
    )
    activity_callback = context.get("_provider_activity_callback")
    if activity_callback is not None and not callable(activity_callback):
        raise ValueError("provider_activity_callback_invalid")
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=0.25, max_delay_seconds=5, timeout_seconds=45, max_pages=200)
    if provider is ProviderKind.GITLAB:
        instance = _hosted_url(str(selected.get("NICO_GITLAB_URL") or ""), host="gitlab.com", default="https://gitlab.com")
        reference, credential = _credential(
            NeutralProviderKind.GITLAB,
            env_var="NICO_GITLAB_TOKEN",
            scheme="private_token",
            key_id="comprehensive-gitlab",
            host="gitlab.com",
            scopes=("read_api", "read_repository"),
            environ=selected,
            required=access_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY,
            resolve_optional=optional_fallback_authorized,
        )
        return GitLabClient(
            instance_url=instance,
            credential=credential,
            credential_reference=reference,
            access_mode=access_mode,
            retry_policy=policy,
            activity_callback=activity_callback,
        )
    if provider is ProviderKind.BITBUCKET_CLOUD:
        instance = _hosted_url(str(selected.get("NICO_BITBUCKET_CLOUD_URL") or ""), host="api.bitbucket.org", default="https://api.bitbucket.org")
        reference, credential = _credential(
            NeutralProviderKind.BITBUCKET,
            env_var="NICO_BITBUCKET_CLOUD_TOKEN",
            scheme="bearer",
            key_id="comprehensive-bitbucket-cloud",
            host="api.bitbucket.org",
            scopes=("repository:read", "pullrequest:read", "pipeline:read"),
            environ=selected,
            required=access_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY,
            resolve_optional=optional_fallback_authorized,
        )
        return BitbucketCloudClient(
            instance_url=instance,
            credential=credential,
            credential_reference=reference,
            access_mode=access_mode,
            retry_policy=policy,
            activity_callback=activity_callback,
        )
    if provider is ProviderKind.AZURE_DEVOPS:
        instance = _hosted_url(str(selected.get("NICO_AZURE_DEVOPS_URL") or ""), host="dev.azure.com", default="https://dev.azure.com")
        organization = _required(context.get("provider_organization") or selected.get("NICO_AZURE_DEVOPS_ORGANIZATION"), "provider_organization")
        project = _required(context.get("provider_project") or selected.get("NICO_AZURE_DEVOPS_PROJECT"), "provider_project")
        reference, credential = _credential(
            NeutralProviderKind.AZURE_DEVOPS,
            env_var="NICO_AZURE_DEVOPS_TOKEN",
            scheme="basic_token",
            key_id="comprehensive-azure-devops",
            host="dev.azure.com",
            scopes=("vso.code", "vso.build", "vso.work"),
            environ=selected,
            required=access_mode is ProviderAccessMode.AUTHENTICATED_READ_ONLY,
            resolve_optional=optional_fallback_authorized,
        )
        return AzureDevOpsClient(
            instance_url=instance,
            organization=organization,
            project=project,
            credential=credential,
            credential_reference=reference,
            access_mode=access_mode,
            retry_policy=policy,
            activity_callback=activity_callback,
        )
    raise ValueError("hosted_provider_client_not_required")


def _collection_id(run_id: str, provider: ProviderKind, repository: str) -> str:
    digest = hashlib.sha256(f"{VERSION}|{run_id}|{provider.value}|{repository}".encode()).hexdigest()[:24]
    return f"evidence_provider_collection_{digest}"


def _evidence_id(prefix: str, run_id: str, repository: str, snapshot_id: str) -> str:
    digest = hashlib.sha256(f"{prefix}|{run_id}|{repository}|{snapshot_id}".encode()).hexdigest()[:20]
    return f"evidence_{prefix}_{digest}"


def _json_safe(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def capture_hosted_provider_snapshot(
    context: Mapping[str, Any],
    provider: ProviderKind,
    *,
    collector: Any | None = None,
    store: StorageAdapter | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if provider not in {ProviderKind.GITLAB, ProviderKind.BITBUCKET_CLOUD, ProviderKind.AZURE_DEVOPS}:
        raise ValueError("hosted_provider_snapshot_requires_non_github_provider")
    active_store = store or STORE
    run_id = _required(context.get("run_id"), "run_id")
    provider_repository = _required(context.get("provider_repository") or context.get("repository"), "repository")
    organization = _text(context.get("provider_organization"))
    project = _text(context.get("provider_project"))
    repository = canonical_repository_label(provider, provider_repository, organization=organization, project=project)
    snapshot_id = repository_snapshot_id(run_id, repository)
    existing = active_store.get("evidence_items", snapshot_id)
    prior = existing.get("evidence") if isinstance(existing, dict) and isinstance(existing.get("evidence"), dict) else None
    if prior and prior.get("status") == "attached":
        reused = dict(prior)
        reused["idempotent_reuse"] = True
        return reused

    expected = _text(context.get("expected_commit_sha") or context.get("commit_sha")).casefold()
    if expected and not _SHA_RE.fullmatch(expected):
        raise ValueError("invalid_explicit_commit_sha")
    owned = collector is None
    client = collector or build_hosted_provider_client(provider, context, environ=environ)
    try:
        collection = client.collect(provider_repository, revision=expected)
        adapted = collection.adapt()
        if adapted.warnings:
            raise ValueError("provider_canonical_evidence_invalid:" + ",".join(adapted.warnings))
        envelope = adapted.envelope
        if envelope.access.read_only is not True:
            raise ValueError("provider_access_must_be_read_only")
        commit_sha = _text(envelope.snapshot.revision).casefold()
        if not commit_sha or not _SHA_RE.fullmatch(commit_sha):
            raise ValueError("provider_snapshot_revision_invalid")
        if expected and commit_sha != expected:
            raise ValueError("provider_snapshot_revision_mismatch")
        collection_id = _collection_id(run_id, provider, repository)
        safe_payload = _json_safe(collection.payload)
        if owned and client.credential is not None:
            secret = client.credential.secret.reveal()
            if secret and secret in json.dumps(safe_payload, sort_keys=True, default=str):
                raise ValueError("provider_credential_leaked_into_collection")
        active_store.put(
            "evidence_items",
            collection_id,
            {
                "evidence_id": collection_id,
                "customer_id": _text(context.get("customer_id")) or "default_customer",
                "project_id": _text(context.get("project_id")) or "default_project",
                "run_id": run_id,
                "filename": f"{provider.value}-provider-collection.json",
                "content_type": "application/json",
                "source": f"{provider.value}_api_read_only",
                "repository": repository,
                "evidence": {
                    "artifact_schema": VERSION,
                    "provider": provider.value,
                    "repository": repository,
                    "provider_repository": provider_repository,
                    "repository_id": envelope.identity.repository_id,
                    "revision": commit_sha,
                    "collected_at": collection.collected_at,
                    "payload": safe_payload,
                    "warnings": [],
                    "read_only": True,
                    "access_mode": collection.access_mode,
                    "credential_used": collection.credential_used,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
            },
        )
        source_fingerprint = _text(envelope.snapshot.source_fingerprint)
        snapshot = {
            "artifact_schema": VERSION,
            "status": "attached",
            "snapshot_id": snapshot_id,
            "run_id": run_id,
            "repository": repository,
            "provider": provider.value,
            "provider_instance": _text(envelope.identity.instance_url),
            "provider_repository": provider_repository,
            "provider_repository_id": _text(envelope.identity.repository_id),
            "provider_collection_id": collection_id,
            "provider_source_fingerprint": source_fingerprint,
            "access_mode": collection.access_mode,
            "credential_used": collection.credential_used,
            "provider_access_mode": collection.access_mode,
            "provider_credential_used": collection.credential_used,
            "required_source_evidence_complete": True,
            "provider_capability_states": list(safe_payload.get("capability_status") or []),
            "pagination_complete": collection.pagination_complete,
            "provider_rate_limit_state": dict(collection.rate_limit_state or {}),
            "provider_collection_limitations": list(collection.collection_limitations),
            "customer_id": _text(context.get("customer_id")) or "default_customer",
            "project_id": _text(context.get("project_id")) or "default_project",
            "default_branch": _text(envelope.identity.default_branch),
            "requested_ref": expected or commit_sha,
            "expected_commit_sha": expected or commit_sha,
            "commit_binding_source": "explicit_request" if expected else "provider_default_branch_resolved_once",
            "exact_commit_verified": True,
            "commit_sha": commit_sha,
            "tree_sha": source_fingerprint,
            "tree_identity_type": "provider_snapshot_manifest_sha256",
            "source": f"{provider.value}_api_read_only",
            "commit_capture_method": f"{provider.value}_api_exact_revision",
            "repository_visibility": "public" if not collection.credential_used else "authorized_provider_scope",
            "provider_organization": organization,
            "provider_project": project,
            "captured_at": collection.collected_at,
            "idempotent_reuse": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "guardrail": "All repository evidence and scanners for this run must remain bound to this exact provider, repository identity, and immutable revision.",
        }
        active_store.put(
            "evidence_items",
            snapshot_id,
            {
                "evidence_id": snapshot_id,
                "customer_id": snapshot["customer_id"],
                "project_id": snapshot["project_id"],
                "run_id": run_id,
                "filename": "provider-repository-snapshot.json",
                "content_type": "application/json",
                "source": snapshot["source"],
                "repository": repository,
                "evidence": snapshot,
            },
        )
        active_store.audit(
            "assessment.provider_repository_snapshot_captured",
            {
                "snapshot_id": snapshot_id,
                "run_id": run_id,
                "provider": provider.value,
                "repository": repository,
                "provider_repository_id": snapshot["provider_repository_id"],
                "commit_sha": commit_sha,
                "source_fingerprint": source_fingerprint,
            },
            customer_id=snapshot["customer_id"],
            project_id=snapshot["project_id"],
        )
        return snapshot
    finally:
        if owned:
            client.close()


def _load_collection(snapshot: Mapping[str, Any], store: StorageAdapter) -> Mapping[str, Any]:
    collection_id = _required(snapshot.get("provider_collection_id"), "provider_collection_id")
    record = store.get("evidence_items", collection_id)
    evidence = record.get("evidence") if isinstance(record, Mapping) and isinstance(record.get("evidence"), Mapping) else {}
    if evidence.get("read_only") is not True or _text(evidence.get("revision")).casefold() != _text(snapshot.get("commit_sha")).casefold():
        raise ValueError("provider_collection_snapshot_mismatch")
    payload = evidence.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("provider_collection_payload_missing")
    return payload


def _clone_spec(repository: str) -> tuple[ProviderKind, str, str, str] | None:
    label = str(repository or "").strip()
    if not label:
        return None
    if (
        label.startswith("/")
        or label.endswith("/")
        or "://" in label
        or "\\" in label
        or "\x00" in label
        or "\r" in label
        or "\n" in label
    ):
        raise ValueError("provider_repository_label_invalid")
    parts = label.split("/")
    host = parts[0].casefold()

    if host == "gitlab.com":
        path = _safe_path("/".join(parts[1:]))
        return (
            ProviderKind.GITLAB,
            f"https://gitlab.com/{path}.git",
            "oauth2",
            _TOKEN_ENV[ProviderKind.GITLAB],
        )

    if host == "bitbucket.org":
        if len(parts) != 3:
            raise ValueError("bitbucket_repository_label_invalid")
        workspace = _safe_segment(parts[1], "bitbucket_repository_label_invalid")
        repo = _safe_segment(parts[2], "bitbucket_repository_label_invalid")
        return (
            ProviderKind.BITBUCKET_CLOUD,
            f"https://bitbucket.org/{workspace}/{repo}.git",
            "x-token-auth",
            _TOKEN_ENV[ProviderKind.BITBUCKET_CLOUD],
        )

    if host == "dev.azure.com":
        if len(parts) != 5 or parts[3] != "_git":
            raise ValueError("azure_repository_label_invalid")
        organization = _safe_segment(parts[1], "azure_repository_label_invalid")
        project = _safe_segment(parts[2], "azure_repository_label_invalid")
        repo = _safe_segment(parts[4], "azure_repository_label_invalid")
        return (
            ProviderKind.AZURE_DEVOPS,
            f"https://dev.azure.com/{organization}/{project}/_git/{repo}",
            "nico",
            _TOKEN_ENV[ProviderKind.AZURE_DEVOPS],
        )

    return None


def _git_run(command: list[str], *, cwd: Path | None, env: Mapping[str, str], timeout: int = 90, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> subprocess.CompletedProcess[str]:
    return runner(command, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout, check=False, shell=False, env=dict(env))


def checkout_hosted_provider_snapshot(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: Mapping[str, str],
    *,
    environ: Mapping[str, str] | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[Path | None, str, list[str]]:
    spec = _clone_spec(repository)
    if spec is None:
        return None, "", ["hosted_provider_checkout_not_applicable"]
    provider, clone_url, username, token_env = spec
    if shutil.which("git") is None:
        return None, "", ["git is unavailable in this worker image; provider snapshot checkout was skipped."]
    if not _SHA_RE.fullmatch(str(commit_sha or "")):
        return None, "", ["A valid full provider snapshot revision is required before scanner execution."]
    selected = os.environ if environ is None else environ
    secret = str(selected.get(token_env) or "")
    if not secret:
        return None, "", [f"{provider.value} server-side credential is not configured for exact snapshot checkout."]

    askpass = workspace / "nico-provider-git-askpass.sh"
    askpass.write_text(
        "#!/bin/sh\ncase \"$1\" in\n  *Username*) printf '%s\\n' \"$NICO_GIT_AUTH_USERNAME\" ;;\n  *) printf '%s\\n' \"$NICO_GIT_AUTH_PASSWORD\" ;;\nesac\n",
        encoding="utf-8",
    )
    askpass.chmod(0o700)
    git_env = dict(env)
    git_env.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_ASKPASS": str(askpass),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "NICO_GIT_AUTH_USERNAME": username,
            "NICO_GIT_AUTH_PASSWORD": secret,
        }
    )
    repo_path = workspace / "repo"
    clone = _git_run(["git", "-c", "credential.helper=", "clone", "--filter=blob:none", "--no-checkout", clone_url, str(repo_path)], cwd=None, env=git_env, runner=runner)
    if clone.returncode != 0:
        return None, "", [f"{provider.value} snapshot-bound git clone failed safely."]
    fetch = _git_run(["git", "-c", "credential.helper=", "fetch", "--depth", "1", "origin", commit_sha], cwd=repo_path, env=git_env, runner=runner)
    if fetch.returncode != 0:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, "", [f"{provider.value} exact snapshot revision could not be fetched."]
    checkout = _git_run(["git", "checkout", "--detach", commit_sha], cwd=repo_path, env=git_env, runner=runner)
    if checkout.returncode != 0:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, "", [f"{provider.value} exact snapshot revision could not be checked out."]
    resolved = _git_run(["git", "rev-parse", "HEAD"], cwd=repo_path, env=git_env, timeout=30, runner=runner)
    actual = (resolved.stdout or "").strip().casefold()
    if resolved.returncode != 0 or actual != commit_sha.casefold():
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual, ["Provider scanner checkout did not match the immutable assessment revision."]
    from nico import scanner_worker as scanner_base

    if scanner_base.directory_size(repo_path) > scanner_base.MAX_REPO_BYTES:
        shutil.rmtree(repo_path, ignore_errors=True)
        return None, actual, ["Provider repository exceeds the configured scanner size limit."]
    return repo_path, actual, []


def _profile_checkout(repo_path: Path) -> dict[str, Any]:
    tree_paths: list[str] = []
    sizes: dict[str, int] = {}
    root_items: set[str] = set()
    for item in repo_path.rglob("*"):
        if not item.is_file():
            continue
        relative = item.relative_to(repo_path).as_posix()
        if relative == ".git" or relative.startswith(".git/"):
            continue
        tree_paths.append(relative)
        root_items.add(relative.split("/", 1)[0])
        try:
            sizes[relative] = item.stat().st_size
        except OSError:
            sizes[relative] = 0
    candidates = [path for path in KNOWN_FILE_PATHS if path in sizes]
    candidates.extend(path for path in sorted(sizes) if path not in candidates and should_fetch_path(path, sizes[path]))
    files: dict[str, str] = {}
    unavailable: list[str] = []
    for path in candidates[:MAX_TEXT_FILES]:
        if sizes.get(path, 0) > MAX_FILE_BYTES:
            continue
        try:
            files[path] = (repo_path / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            unavailable.append(f"Exact provider snapshot file {path} could not be read by the isolated worker.")
    return {"files": files, "tree_paths": sorted(tree_paths), "root_items": sorted(root_items), "unavailable": unavailable}


def _workflow_paths(provider: str, paths: list[str]) -> list[str]:
    if provider == ProviderKind.GITLAB.value:
        return [path for path in paths if path == ".gitlab-ci.yml" or (path.startswith(".gitlab/") and path.endswith((".yml", ".yaml")))]
    if provider == ProviderKind.BITBUCKET_CLOUD.value:
        return [path for path in paths if path == "bitbucket-pipelines.yml"]
    if provider == ProviderKind.AZURE_DEVOPS.value:
        return [path for path in paths if path.casefold().endswith(("azure-pipelines.yml", "azure-pipelines.yaml")) or path.startswith(".azuredevops/")]
    return []


def _state_success(value: Any) -> bool:
    return _text(value).casefold() in {"success", "succeeded", "successful", "passed", "completed"}


def _state_failure(value: Any) -> bool:
    return _text(value).casefold() in {"failure", "failed", "error", "canceled", "cancelled", "timed_out", "partially_succeeded"}


def _adapt_payload(provider: str, payload: Mapping[str, Any]):
    from nico.provider_payload_adapters import adapt_azure_devops_payload, adapt_bitbucket_payload, adapt_gitlab_payload

    if provider == ProviderKind.GITLAB.value:
        return adapt_gitlab_payload(payload)
    if provider == ProviderKind.BITBUCKET_CLOUD.value:
        return adapt_bitbucket_payload(payload)
    if provider == ProviderKind.AZURE_DEVOPS.value:
        return adapt_azure_devops_payload(payload)
    raise ValueError("provider_payload_adapter_missing")


def _persist_evidence(bundle: Mapping[str, Any], store: StorageAdapter, filename: str) -> None:
    store.put(
        "evidence_items",
        str(bundle["evidence_id"]),
        {
            "evidence_id": bundle["evidence_id"],
            "customer_id": bundle.get("customer_id") or "default_customer",
            "project_id": bundle.get("project_id") or "default_project",
            "run_id": bundle.get("run_id") or "",
            "filename": filename,
            "content_type": "application/json",
            "source": bundle.get("source") or "provider_snapshot_bound_read_only",
            "repository": bundle.get("repository") or "",
            "evidence": dict(bundle),
        },
    )


def collect_hosted_provider_repository_evidence(
    context: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    store: StorageAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    active_store = store or STORE
    run_id = _required(context.get("run_id"), "run_id")
    repository = _required(context.get("repository"), "repository")
    snapshot_id = _required(snapshot.get("snapshot_id"), "snapshot_id")
    evidence_id = _evidence_id("snapshot_repo", run_id, repository, snapshot_id)
    complexity_id = _evidence_id("snapshot_complexity", run_id, repository, snapshot_id)
    existing = active_store.get("evidence_items", evidence_id)
    prior_complexity = active_store.get("evidence_items", complexity_id)
    if isinstance(existing, Mapping) and isinstance(existing.get("evidence"), Mapping) and isinstance(prior_complexity, Mapping) and isinstance(prior_complexity.get("evidence"), Mapping):
        bundle = dict(existing["evidence"])
        complexity = dict(prior_complexity["evidence"])
        bundle["idempotent_reuse"] = complexity["idempotent_reuse"] = True
        return bundle, complexity
    if snapshot.get("status") != "attached" or _text(snapshot.get("repository")) != repository or _text(snapshot.get("run_id")) != run_id:
        unavailable = {
            "status": "unavailable",
            "evidence_id": evidence_id,
            "run_id": run_id,
            "repository": repository,
            "snapshot_id": snapshot_id,
            "source": "provider_snapshot_bound_read_only",
            "unavailable_data_notes": ["Provider repository evidence requires the exact attached provider snapshot for this run."],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return unavailable, {**unavailable, "evidence_id": complexity_id}

    provider = _required(snapshot.get("provider"), "provider")
    collection_payload = _load_collection(snapshot, active_store)
    adapted = _adapt_payload(provider, collection_payload)
    if adapted.warnings:
        raise ValueError("provider_collection_canonical_warnings:" + ",".join(adapted.warnings))
    envelope = adapted.envelope
    notes = list(getattr(envelope, "collection_limitations", ()) or ())

    with tempfile.TemporaryDirectory(prefix="nico-provider-evidence-") as temporary:
        root = Path(temporary)
        from nico import scanner_worker as scanner_base

        repo_path, actual_sha, checkout_notes = checkout_hosted_provider_snapshot(repository, _text(snapshot.get("commit_sha")), root, scanner_base.clean_env(root))
        notes.extend(checkout_notes)
        if repo_path is None or actual_sha != _text(snapshot.get("commit_sha")).casefold():
            unavailable = {
                "status": "unavailable",
                "evidence_id": evidence_id,
                "run_id": run_id,
                "repository": repository,
                "snapshot_id": snapshot_id,
                "source": f"{provider}_snapshot_bound_read_only",
                "unavailable_data_notes": sorted({_text(item) for item in notes if _text(item)}),
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            return unavailable, {**unavailable, "evidence_id": complexity_id}
        profile = _profile_checkout(repo_path)

    files = profile["files"]
    paths = profile["tree_paths"]
    notes.extend(profile["unavailable"])
    workflows: dict[str, str] = {path: files[path] for path in _workflow_paths(provider, paths) if path in files}
    dependencies = collect_dependencies(files)
    source_scan = analyze_source_signals(files)
    source_paths = [path for path in paths if path.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".cs", ".java", ".go", ".rs")) and "/test" not in path.casefold() and not path.casefold().startswith("test")]

    ci_runs = [asdict(item) for item in envelope.ci_runs]
    ci_jobs = [asdict(item) for item in getattr(envelope, "ci_jobs", ())]
    deployments = [asdict(item) for item in getattr(envelope, "deployments", ())]
    changes = [asdict(item) for item in envelope.change_requests]
    success_runs = sum(_state_success(item.get("conclusion") or item.get("status")) for item in ci_runs)
    failed_runs = sum(_state_failure(item.get("conclusion") or item.get("status")) for item in ci_runs)
    success_jobs = sum(_state_success(item.get("conclusion") or item.get("status")) for item in ci_jobs)
    failed_jobs = sum(_state_failure(item.get("conclusion") or item.get("status")) for item in ci_jobs)
    success_deployments = sum(_state_success(item.get("status")) for item in deployments)
    failed_deployments = sum(_state_failure(item.get("status")) for item in deployments)
    snapshot_sha = _text(snapshot.get("commit_sha"))
    capability_states = [asdict(item) for item in getattr(envelope, "capability_status", ())]

    bundle = {
        "status": "attached",
        "evidence_id": evidence_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "source": f"{provider}_snapshot_bound_read_only",
        "authorization_scope": "authorized defensive repository assessment",
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot_sha,
        "snapshot_tree_sha": snapshot.get("tree_sha") or "",
        "snapshot_captured_at": snapshot.get("captured_at") or "",
        "repository_provider": provider,
        "repository_provider_instance": snapshot.get("provider_instance") or "",
        "provider_repository_id": snapshot.get("provider_repository_id") or "",
        "provider_capability_states": capability_states,
        "code_evidence_scope": "Repository files, manifests, CI configuration, source signals, and complexity are read from the exact immutable provider revision.",
        "operational_evidence_scope": "Change requests and provider-native CI/job/deployment records are separately retained provider evidence and do not mutate exact-revision code truth.",
        "repository_metadata": {
            "full_name": repository,
            "provider": provider,
            "repository_id": snapshot.get("provider_repository_id") or "",
            "default_branch": snapshot.get("default_branch") or "",
            "visibility": snapshot.get("repository_visibility") or "authorized_provider_scope",
            "commit_sha": snapshot_sha,
            "tree_sha": snapshot.get("tree_sha") or "",
        },
        "file_evidence": {
            "files_profiled": len(files),
            "tree_paths_seen": len(paths),
            "sampled_paths": sorted(files)[:40],
            "top_level_items": profile["root_items"][:40],
            "snapshot_commit_sha": snapshot_sha,
        },
        "architecture_evidence": {
            "source_file_count": len(source_paths),
            "test_path_count": sum("test" in path.casefold() for path in paths),
            "documentation_path_count": sum(path.casefold().endswith(".md") or path.startswith("docs/") for path in paths),
            "deployment_manifests": sorted(path for path in paths if path.rsplit("/", 1)[-1] in {"Dockerfile", "Procfile", "render.yaml", "railway.json", "railway.toml", "fly.toml", "vercel.json"})[:20],
            "top_level_directories": [item for item in profile["root_items"] if "." not in item][:30],
            "snapshot_commit_sha": snapshot_sha,
        },
        "dependency_evidence": {
            "manifest_paths": sorted(path for path in files if path.rsplit("/", 1)[-1] in {"requirements.txt", "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}),
            "lockfile_paths": sorted(path for path in files if path.rsplit("/", 1)[-1] in {"Pipfile.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"}),
            "dependency_entries": len(dependencies),
            "ecosystems": sorted({_text(item.get("ecosystem")) or "unknown" for item in dependencies}),
            "snapshot_commit_sha": snapshot_sha,
        },
        "activity_evidence": {
            "status": "provider_operational_evidence",
            "change_requests_returned": len(changes),
            "merged_pull_requests": sum(_text(item.get("state")).casefold() in {"merged", "completed"} for item in changes),
            "open_pull_requests": sum(_text(item.get("state")).casefold() in {"open", "opened", "active"} for item in changes),
            "sample_pull_requests": changes[:10],
        },
        "workflow_evidence": {
            "workflow_files": sorted(workflows),
            "workflow_file_count": len(workflows),
            "workflow_configuration_snapshot_sha": snapshot_sha,
            "workflow_run_count": len(ci_runs),
            "successful_runs": success_runs,
            "non_success_runs": failed_runs,
            "runs_matching_snapshot_sha": sum(_text(item.get("revision")).casefold() == snapshot_sha.casefold() for item in ci_runs),
            "explicit_permissions_present": None,
            "permission_control_assessed": False,
            "permission_control_state": "not_assessed",
            "provider_native_ci_evidence": True,
            "repository_provider": provider,
            "ci_provider": provider,
            "external_ci_is_separate": True,
            "job_evidence": {
                "jobs_observed": len(ci_jobs),
                "successful_jobs": success_jobs,
                "non_success_jobs": failed_jobs,
                "job_success_rate": round(success_jobs / len(ci_jobs), 4) if ci_jobs else None,
            },
            "deployment_evidence": {
                "deployments_observed": len(deployments),
                "successful_deployments": success_deployments,
                "non_success_deployments": failed_deployments,
            },
            "jobs_observed": len(ci_jobs),
            "successful_jobs": success_jobs,
            "non_success_jobs": failed_jobs,
            "job_success_rate": round(success_jobs / len(ci_jobs), 4) if ci_jobs else None,
            "deployments_observed": len(deployments),
            "successful_deployments": success_deployments,
            "non_success_deployments": failed_deployments,
            "ci_runtime_guardrail": "Provider-native CI evidence is operational evidence. CI configuration is evaluated from the exact immutable repository revision.",
        },
        "code_signal_evidence": {
            "todo_fixme_security_notes": len(source_scan.get("todos") or []),
            "risk_pattern_hits": len(source_scan.get("risks") or []),
            "risk_records": list(source_scan.get("risk_records") or [])[:50],
            "excluded_non_production_risk_count": len(source_scan.get("excluded_non_production_risks") or []),
            "potential_secret_pattern_hits": len(source_scan.get("secrets") or []),
            "verified_example_placeholder_secret_count": len(source_scan.get("verified_example_placeholder_secrets") or []),
            "test_files_profiled": len(source_scan.get("test_paths") or []),
            "documentation_files_profiled": len(source_scan.get("docs") or []),
            "analysis_version": source_scan.get("analysis_version"),
            "executable_source_only": source_scan.get("executable_source_only") is True,
            "comments_and_strings_excluded": source_scan.get("comments_and_strings_excluded") is True,
            "snapshot_commit_sha": snapshot_sha,
        },
        "unavailable_data_notes": sorted({_text(item) for item in notes if _text(item)}),
        "retention_note": "Only summarized evidence and bounded sampled-file analysis are retained; provider credentials and raw CI logs are not retained.",
        "idempotent_reuse": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    measured = collect_complexity_evidence(files)
    complexity = {
        **measured,
        "evidence_id": complexity_id,
        "run_id": run_id,
        "repository": repository,
        "customer_id": bundle["customer_id"],
        "project_id": bundle["project_id"],
        "source": f"{provider}_snapshot_bound_complexity",
        "snapshot_id": snapshot_id,
        "snapshot_commit_sha": snapshot_sha,
        "snapshot_tree_sha": snapshot.get("tree_sha") or "",
        "profiled_file_count": len(files),
        "idempotent_reuse": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "guardrail": "Complexity measurements cover only readable sampled source files from the exact provider revision.",
    }
    _persist_evidence(bundle, active_store, "provider-snapshot-repository-evidence.json")
    _persist_evidence(complexity, active_store, "provider-snapshot-complexity-evidence.json")
    return bundle, complexity


def _operator_required(token: str) -> None:
    allowed, status = require_admin_write(token)
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "authorized_nico_operator_required",
                "admin_write": status,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        )


def _operator_intake(request: Request, payload: Mapping[str, Any], token: str) -> dict[str, Any]:
    _operator_required(token)
    if not isinstance(payload, Mapping):
        raise TypeError("request_body_must_be_object")
    if payload.get("authorized") is not True or payload.get("authorization_confirmed") is not True:
        raise ValueError("explicit_authorization_required")
    assert_no_raw_provider_credentials(payload)

    provider = _provider(payload.get("provider") or "github")
    provider_repository = _required(payload.get("repository"), "repository")
    customer_id = _required(payload.get("customer_id") or "default_customer", "customer_id")
    project_id = _required(payload.get("project_id") or "default_project", "project_id")
    assessment_depth = _required(payload.get("assessment_depth") or "strategic", "assessment_depth")
    report_language = _required(payload.get("report_language") or "en", "report_language")
    organization = _text(payload.get("provider_organization"))
    provider_project = _text(payload.get("provider_project"))
    repository = canonical_repository_label(provider, provider_repository, organization=organization, project=provider_project)
    requested_sha = expected_commit_sha(dict(payload))
    run_id = f"comprun_{uuid4().hex}"
    ledger_id = f"ledger_comprehensive_{uuid4().hex}"

    registry = getattr(request.app.state, ROLLOUT_STATE_KEY, None)
    if not isinstance(registry, ProviderRolloutRegistry):
        raise ValueError("provider_rollout_control_unavailable")
    registry.preflight(
        {
            "provider": provider.value,
            "client_id": customer_id,
            "project_id": project_id,
            "session_id": _required(payload.get("session_id") or f"operator:{customer_id}:{project_id}", "session_id"),
            "run_id": run_id,
            "locale": report_language,
            "execution_mode": _text(payload.get("execution_mode") or "internal_test"),
            "expected_capability_revision": payload.get("expected_capability_revision"),
            "ci_provider": payload.get("ci_provider") or provider.value,
        },
        operator_authorized=True,
    )

    if provider is ProviderKind.GITHUB:
        snapshot = capture_repository_snapshot(
            {
                "run_id": run_id,
                "repository": normalize_repository(provider_repository),
                "customer_id": customer_id,
                "project_id": project_id,
                "authorized": True,
                "authorized_by": _required(payload.get("authorized_by") or "nico_operator", "authorized_by"),
                "authorization_scope": _required(payload.get("authorization_scope") or "authorized defensive repository assessment", "authorization_scope"),
                "expected_commit_sha": requested_sha,
            }
        )
    else:
        snapshot = capture_hosted_provider_snapshot(
            {
                "run_id": run_id,
                "repository": repository,
                "provider_repository": provider_repository,
                "provider_organization": organization,
                "provider_project": provider_project,
                "customer_id": customer_id,
                "project_id": project_id,
                "expected_commit_sha": requested_sha,
                "provider_access_mode": ProviderAccessMode.AUTHENTICATED_READ_ONLY.value,
                "provider_credential_fallback_authorized": True,
            },
            provider,
        )
    if snapshot.get("status") != "attached" or not _text(snapshot.get("commit_sha")):
        raise ValueError("repository_snapshot_unavailable")

    response = api_routes._controller(request).start(
        {
            "repository": repository,
            "commit_sha": snapshot["commit_sha"],
            "run_id": run_id,
            "evidence_ledger_id": ledger_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "assessment_depth": assessment_depth,
            "report_language": report_language,
            "human_evidence": payload.get("human_evidence"),
            "authorized": True,
            "authorization_confirmed": True,
        }
    )
    return api_routes._with_runtime_truth(
        request,
        {
            **response,
            "operation": "operator_provider_intake_started",
            "repository_provider": provider.value,
            "provider_repository": provider_repository,
            "repository_snapshot": snapshot,
            "operator_run_only": True,
            "customer_self_service": False,
        },
    )


def install_hosted_provider_comprehensive_runtime(app: FastAPI) -> dict[str, Any]:
    providers = getattr(app.state, PROVIDER_STATE_KEY, None)
    if not isinstance(providers, dict):
        raise RuntimeError("comprehensive_capability_provider_registry_unavailable")

    current_repository_provider = providers.get("repository_evidence")
    if not callable(current_repository_provider):
        raise RuntimeError("comprehensive_repository_evidence_provider_unavailable")
    if not getattr(current_repository_provider, "_nico_hosted_provider_parity_v1", False):
        original_repository_provider = current_repository_provider

        def repository_evidence_provider(context: dict[str, Any]) -> dict[str, Any]:
            snapshot = native._snapshot(context)
            if _text(snapshot.get("provider")) in {
                ProviderKind.GITLAB.value,
                ProviderKind.BITBUCKET_CLOUD.value,
                ProviderKind.AZURE_DEVOPS.value,
            }:
                repository_evidence, complexity_evidence = collect_hosted_provider_repository_evidence(context, snapshot)
                if repository_evidence.get("status") != "attached":
                    return native._result(
                        context,
                        "blocked",
                        reason="snapshot_repository_evidence_unavailable",
                        repository_evidence=repository_evidence,
                        complexity_evidence=complexity_evidence,
                        unavailable_data_notes=repository_evidence.get("unavailable_data_notes") or [],
                    )
                files = repository_evidence.get("file_evidence") if isinstance(repository_evidence.get("file_evidence"), Mapping) else {}
                architecture = repository_evidence.get("architecture_evidence") if isinstance(repository_evidence.get("architecture_evidence"), Mapping) else {}
                workflows = repository_evidence.get("workflow_evidence") if isinstance(repository_evidence.get("workflow_evidence"), Mapping) else {}
                return native._result(
                    context,
                    summary="Exact-revision provider repository, dependency, architecture, workflow, activity, and complexity evidence were attached through the canonical provider-neutral path.",
                    repository_evidence=repository_evidence,
                    complexity_evidence=complexity_evidence,
                    evidence={
                        "repository_provider": snapshot.get("provider"),
                        "repository_evidence_id": repository_evidence.get("evidence_id"),
                        "complexity_evidence_id": complexity_evidence.get("evidence_id"),
                        "snapshot_commit_sha": repository_evidence.get("snapshot_commit_sha"),
                        "files_profiled": files.get("files_profiled", 0),
                        "tree_paths_seen": files.get("tree_paths_seen", 0),
                        "source_file_count": architecture.get("source_file_count", 0),
                        "workflow_file_count": workflows.get("workflow_file_count", 0),
                    },
                    unavailable_data_notes=repository_evidence.get("unavailable_data_notes") or [],
                )
            return original_repository_provider(context)

        setattr(repository_evidence_provider, "_nico_hosted_provider_parity_v1", True)
        providers["repository_evidence"] = repository_evidence_provider
        setattr(app.state, PROVIDER_STATE_KEY, providers)

    current_clone = snapshot_worker.clone_repository_at_snapshot
    if not getattr(current_clone, _PATCH_MARKER, False):
        original_clone = current_clone

        def clone_repository_at_snapshot(repository: str, commit_sha: str, workspace: Path, env: dict[str, str]):
            if _clone_spec(repository) is None:
                return original_clone(repository, commit_sha, workspace, env)
            return checkout_hosted_provider_snapshot(repository, commit_sha, workspace, env)

        setattr(clone_repository_at_snapshot, _PATCH_MARKER, True)
        setattr(clone_repository_at_snapshot, "_nico_previous", original_clone)
        snapshot_worker.clone_repository_at_snapshot = clone_repository_at_snapshot

    route_count = sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == OPERATOR_INTAKE_ROUTE
        and "POST" in {str(method).upper() for method in (getattr(route, "methods", set()) or set())}
    )
    if route_count == 0:
        @app.post(OPERATOR_INTAKE_ROUTE)
        async def operator_comprehensive_intake(
            request: Request,
            x_nico_admin_token: str = Header(default=""),
        ) -> dict[str, Any]:
            try:
                payload = await request.json()
                return await run_in_threadpool(_operator_intake, request, payload, x_nico_admin_token)
            except HTTPException:
                raise
            except Exception as exc:
                raise api_routes._translate_error(exc) from exc

        app.openapi_schema = None
        route_count = 1
    if route_count != 1:
        raise RuntimeError("provider_operator_comprehensive_intake_route_missing_or_duplicated")

    status = {
        "artifact_schema": VERSION,
        "status": "installed",
        "major_hosted_provider_count": 4,
        "github_regression_path_preserved": True,
        "gitlab_comprehensive_runtime_bound": True,
        "bitbucket_cloud_comprehensive_runtime_bound": True,
        "azure_devops_comprehensive_runtime_bound": True,
        "same_scanner_pipeline": True,
        "same_candidate_triage_report_pipeline": True,
        "operator_run_only": True,
        "customer_self_service": False,
        "credentials_server_side_only": True,
        "exact_revision_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "operator_intake_route_count": route_count,
    }
    app.state.nico_hosted_provider_comprehensive_runtime = status
    return status


__all__ = [
    "OPERATOR_INTAKE_ROUTE",
    "VERSION",
    "_access_mode",
    "assert_no_raw_provider_credentials",
    "build_hosted_provider_client",
    "canonical_repository_label",
    "capture_hosted_provider_snapshot",
    "checkout_hosted_provider_snapshot",
    "collect_hosted_provider_repository_evidence",
    "install_hosted_provider_comprehensive_runtime",
    "normalize_submitted_provider_repository",
]
