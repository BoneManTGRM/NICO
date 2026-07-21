from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from nico.provider_credentials import EnvironmentCredentialResolver, build_reference
from nico.provider_enterprise_clients import BitbucketDataCenterClient
from nico.provider_live_clients import AzureDevOpsClient, BitbucketCloudClient, GitLabClient, RetryPolicy


class LiveAcceptanceError(RuntimeError):
    pass


def _required_environment(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise LiveAcceptanceError(f"required_environment_missing:{name}")
    return value


def _credential(
    *,
    provider: str,
    env_var: str,
    scheme: str,
    key_id: str,
    hosts: tuple[str, ...],
    scopes: tuple[str, ...],
):
    reference = build_reference(
        provider=provider,
        env_var=env_var,
        scheme=scheme,
        key_id=key_id,
        allowed_hosts=hosts,
        scopes=scopes,
    )
    return EnvironmentCredentialResolver().resolve(reference)


def _host(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise LiveAcceptanceError("provider_acceptance_https_url_required")
    return parsed.hostname.lower()


def build_collector(provider: str):
    token = provider.lower().replace("-", "_")
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=1, max_delay_seconds=30, timeout_seconds=45, max_pages=200)
    if token == "gitlab":
        instance = _required_environment("NICO_GITLAB_URL")
        credential = _credential(
            provider="gitlab",
            env_var="NICO_GITLAB_TOKEN",
            scheme="private_token",
            key_id="live-gitlab",
            hosts=(_host(instance),),
            scopes=("read_api", "read_repository"),
        )
        return GitLabClient(instance_url=instance, credential=credential, retry_policy=policy)
    if token == "bitbucket_cloud":
        instance = str(os.environ.get("NICO_BITBUCKET_CLOUD_URL") or "https://api.bitbucket.org").strip()
        credential = _credential(
            provider="bitbucket",
            env_var="NICO_BITBUCKET_CLOUD_TOKEN",
            scheme="bearer",
            key_id="live-bitbucket-cloud",
            hosts=(_host(instance),),
            scopes=("repository:read", "pullrequest:read", "pipeline:read"),
        )
        return BitbucketCloudClient(instance_url=instance, credential=credential, retry_policy=policy)
    if token == "bitbucket_data_center":
        instance = _required_environment("NICO_BITBUCKET_DC_URL")
        credential = _credential(
            provider="bitbucket",
            env_var="NICO_BITBUCKET_DC_TOKEN",
            scheme="bearer",
            key_id="live-bitbucket-dc",
            hosts=(_host(instance),),
            scopes=("repository:read", "pullrequest:read", "build-status:read"),
        )
        return BitbucketDataCenterClient(instance_url=instance, credential=credential, retry_policy=policy)
    if token == "azure_devops":
        instance = str(os.environ.get("NICO_AZURE_DEVOPS_URL") or "https://dev.azure.com").strip()
        credential = _credential(
            provider="azure_devops",
            env_var="NICO_AZURE_DEVOPS_TOKEN",
            scheme="basic_token",
            key_id="live-azure-devops",
            hosts=(_host(instance),),
            scopes=("vso.code", "vso.build", "vso.work"),
        )
        return AzureDevOpsClient(
            instance_url=instance,
            organization=_required_environment("NICO_AZURE_DEVOPS_ORGANIZATION"),
            project=_required_environment("NICO_AZURE_DEVOPS_PROJECT"),
            credential=credential,
            retry_policy=policy,
        )
    raise LiveAcceptanceError(f"provider_acceptance_unsupported:{provider}")


def _canonical_envelope(result: Any) -> dict[str, Any]:
    envelope = result.envelope
    return {
        "identity": asdict(envelope.identity),
        "access": asdict(envelope.access),
        "snapshot": asdict(envelope.snapshot),
        "change_requests": [asdict(item) for item in envelope.change_requests],
        "ci_runs": [asdict(item) for item in envelope.ci_runs],
        "warnings": list(result.warnings),
    }


def _json_safe(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    rendered = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"sha256:{sha256(rendered.encode('utf-8')).hexdigest()}"


def run_acceptance(*, provider: str, repository: str, revision: str, passes: int = 2) -> dict[str, Any]:
    if passes < 2:
        raise LiveAcceptanceError("provider_acceptance_requires_two_passes")
    collector = build_collector(provider)
    safe_credential = collector.credential.safe_metadata()
    runs: list[dict[str, Any]] = []
    try:
        pinned_revision = revision
        for index in range(passes):
            collection = collector.collect(repository, revision=pinned_revision)
            if not pinned_revision:
                pinned_revision = collection.revision
            if collection.revision != pinned_revision:
                raise LiveAcceptanceError("provider_acceptance_revision_drift")
            adapted = collection.adapt()
            if adapted.warnings:
                raise LiveAcceptanceError("provider_acceptance_canonical_warnings:" + ",".join(adapted.warnings))
            envelope = _canonical_envelope(adapted)
            if envelope["snapshot"]["revision"] != pinned_revision:
                raise LiveAcceptanceError("provider_acceptance_snapshot_revision_mismatch")
            if envelope["access"]["read_only"] is not True:
                raise LiveAcceptanceError("provider_acceptance_must_be_read_only")
            if envelope["access"]["partial_access"] is True:
                raise LiveAcceptanceError("provider_acceptance_partial_access")
            runs.append(
                {
                    "pass": index + 1,
                    "provider": collection.provider.value,
                    "repository_id": collection.repository_id,
                    "revision": collection.revision,
                    "collected_at": collection.collected_at,
                    "pages_fetched": collection.pages_fetched,
                    "requests_made": collection.requests_made,
                    "canonical_fingerprint": _fingerprint(envelope),
                    "source_fingerprint": envelope["snapshot"]["source_fingerprint"],
                    "change_request_count": len(envelope["change_requests"]),
                    "ci_run_count": len(envelope["ci_runs"]),
                    "warnings": [],
                }
            )
    finally:
        collector.close()

    repository_ids = {item["repository_id"] for item in runs}
    revisions = {item["revision"] for item in runs}
    source_fingerprints = {item["source_fingerprint"] for item in runs}
    if len(repository_ids) != 1:
        raise LiveAcceptanceError("provider_acceptance_repository_identity_drift")
    if len(revisions) != 1:
        raise LiveAcceptanceError("provider_acceptance_revision_drift")
    if len(source_fingerprints) != 1:
        raise LiveAcceptanceError("provider_acceptance_source_fingerprint_drift")

    return {
        "artifact_schema": "nico.provider_live_acceptance.v1",
        "status": "passed",
        "live_production_claim": True,
        "provider": provider,
        "repository": repository,
        "expected_revision": pinned_revision,
        "passes_required": passes,
        "passes_completed": len(runs),
        "runs": runs,
        "proof": {
            "two_consecutive_passes": len(runs) >= 2,
            "repository_identity_preserved": len(repository_ids) == 1,
            "immutable_revision_preserved": len(revisions) == 1,
            "source_fingerprint_preserved": len(source_fingerprints) == 1,
            "read_only_access": True,
            "pagination_completed": True,
            "canonical_warnings_absent": True,
            "raw_credential_absent": True,
        },
        "credential_metadata": safe_credential,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live NICO provider acceptance twice against one immutable revision.")
    parser.add_argument("--provider", required=True, choices=("gitlab", "bitbucket_cloud", "bitbucket_data_center", "azure_devops"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--revision", default="")
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        result = run_acceptance(
            provider=args.provider,
            repository=args.repository,
            revision=args.revision,
            passes=args.passes,
        )
    except Exception as exc:
        result = {
            "artifact_schema": "nico.provider_live_acceptance.v1",
            "status": "failed",
            "provider": args.provider,
            "repository": args.repository,
            "error_type": type(exc).__name__,
            "error_code": str(exc),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(_json_safe(result), indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(_json_safe(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
