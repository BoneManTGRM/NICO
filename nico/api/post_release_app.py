from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

from fastapi import FastAPI

from nico.post_release_production_bootstrap import (
    PostReleaseDependencies,
    PostReleaseRuntimeConfig,
    install_post_release_runtime,
)
from nico.provider_credentials import EnvironmentCredentialResolver, SecretValue, build_reference
from nico.provider_enterprise_clients import BitbucketDataCenterClient
from nico.provider_live_clients import AzureDevOpsClient, BitbucketCloudClient, GitLabClient, RetryPolicy
from nico.provider_neutral_contract import ProviderKind


VERSION = "nico.post_release_app.v1"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _positive_int(value: Any, *, default: int, minimum: int, maximum: int, code: str) -> int:
    token = str(value or "").strip()
    try:
        parsed = default if not token else int(token)
    except ValueError as exc:
        raise RuntimeError(code) from exc
    if parsed < minimum or parsed > maximum:
        raise RuntimeError(code)
    return parsed


def _https_host(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("post_release_provider_https_url_required")
    return parsed.hostname.lower()


def _database_dependencies(
    environ: Mapping[str, str],
    *,
    required: bool,
) -> tuple[Callable[[], Any] | None, str, dict[str, Any]]:
    database_url = str(environ.get("DATABASE_URL") or "").strip()
    if database_url:
        if not database_url.lower().startswith(("postgres://", "postgresql://")):
            raise RuntimeError("post_release_database_url_must_be_postgres")

        def postgres_connection() -> Any:
            try:
                import psycopg
            except ImportError as exc:
                raise RuntimeError("post_release_psycopg_not_installed") from exc
            return psycopg.connect(database_url)

        return postgres_connection, "postgres", {
            "adapter": "postgres",
            "configured": True,
            "source": "DATABASE_URL",
            "secret_exposed": False,
        }

    sqlite_enabled = _truthy(environ.get("NICO_ENABLE_SQLITE_DURABLE_STORAGE"))
    sqlite_path = str(
        environ.get("NICO_POST_RELEASE_SQLITE_PATH")
        or environ.get("NICO_RUNTIME_SQLITE_PATH")
        or ""
    ).strip()
    if sqlite_enabled and sqlite_path:
        path = Path(sqlite_path).expanduser().resolve()
        if not str(path).startswith("/data/") and not _truthy(environ.get("NICO_ALLOW_NON_VOLUME_SQLITE")):
            raise RuntimeError("post_release_sqlite_requires_persistent_data_path")
        path.parent.mkdir(parents=True, exist_ok=True)

        def sqlite_connection() -> sqlite3.Connection:
            connection = sqlite3.connect(path, timeout=30)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=30000")
            return connection

        return sqlite_connection, "sqlite", {
            "adapter": "railway_volume_sqlite",
            "configured": True,
            "source": str(path),
            "single_writer_required": True,
            "secret_exposed": False,
        }

    if required:
        return None, "sqlite", {
            "adapter": "none",
            "configured": False,
            "reason": "durable_database_not_configured",
            "secret_exposed": False,
        }
    return None, "sqlite", {
        "adapter": "none",
        "configured": False,
        "reason": "runtime_features_disabled",
        "secret_exposed": False,
    }


def _credential(
    resolver: EnvironmentCredentialResolver,
    *,
    provider: str,
    env_var: str,
    scheme: str,
    key_id: str,
    hosts: tuple[str, ...],
    scopes: tuple[str, ...],
):
    return resolver.resolve(
        build_reference(
            provider=provider,
            env_var=env_var,
            scheme=scheme,
            key_id=key_id,
            allowed_hosts=hosts,
            scopes=scopes,
        )
    )


def _provider_dependencies(
    environ: Mapping[str, str],
) -> tuple[dict[ProviderKind, Any], dict[ProviderKind, SecretValue], list[Any], dict[str, Any]]:
    resolver = EnvironmentCredentialResolver(environ)
    retry = RetryPolicy(
        max_attempts=_positive_int(
            environ.get("NICO_PROVIDER_MAX_ATTEMPTS"),
            default=4,
            minimum=1,
            maximum=10,
            code="post_release_provider_max_attempts_invalid",
        ),
        base_delay_seconds=float(environ.get("NICO_PROVIDER_BASE_DELAY_SECONDS") or 1),
        max_delay_seconds=float(environ.get("NICO_PROVIDER_MAX_DELAY_SECONDS") or 30),
        timeout_seconds=float(environ.get("NICO_PROVIDER_TIMEOUT_SECONDS") or 45),
        max_pages=_positive_int(
            environ.get("NICO_PROVIDER_MAX_PAGES"),
            default=200,
            minimum=1,
            maximum=5000,
            code="post_release_provider_max_pages_invalid",
        ),
    )
    retry.validate()
    collectors: dict[ProviderKind, Any] = {}
    webhook_secrets: dict[ProviderKind, SecretValue] = {}
    closeables: list[Any] = []
    configured: dict[str, Any] = {}

    gitlab_url = str(environ.get("NICO_GITLAB_URL") or "").strip()
    if gitlab_url and str(environ.get("NICO_GITLAB_TOKEN") or "").strip():
        collector = GitLabClient(
            instance_url=gitlab_url,
            credential=_credential(
                resolver,
                provider="gitlab",
                env_var="NICO_GITLAB_TOKEN",
                scheme="private_token",
                key_id=str(environ.get("NICO_GITLAB_KEY_ID") or "production-gitlab"),
                hosts=(_https_host(gitlab_url),),
                scopes=("read_api", "read_repository"),
            ),
            retry_policy=retry,
        )
        collectors[ProviderKind.GITLAB] = collector
        closeables.append(collector)
        configured["gitlab"] = collector.credential.safe_metadata()

    bitbucket_cloud_url = str(
        environ.get("NICO_BITBUCKET_CLOUD_URL") or "https://api.bitbucket.org"
    ).strip()
    if str(environ.get("NICO_BITBUCKET_CLOUD_TOKEN") or "").strip():
        collector = BitbucketCloudClient(
            instance_url=bitbucket_cloud_url,
            credential=_credential(
                resolver,
                provider="bitbucket",
                env_var="NICO_BITBUCKET_CLOUD_TOKEN",
                scheme="bearer",
                key_id=str(environ.get("NICO_BITBUCKET_CLOUD_KEY_ID") or "production-bitbucket-cloud"),
                hosts=(_https_host(bitbucket_cloud_url),),
                scopes=("repository:read", "pullrequest:read", "pipeline:read"),
            ),
            retry_policy=retry,
        )
        collectors[ProviderKind.BITBUCKET] = collector
        closeables.append(collector)
        configured["bitbucket_cloud"] = collector.credential.safe_metadata()

    bitbucket_dc_url = str(environ.get("NICO_BITBUCKET_DC_URL") or "").strip()
    if bitbucket_dc_url and str(environ.get("NICO_BITBUCKET_DC_TOKEN") or "").strip():
        if ProviderKind.BITBUCKET in collectors:
            raise RuntimeError("post_release_multiple_bitbucket_collectors_require_separate_runtime")
        collector = BitbucketDataCenterClient(
            instance_url=bitbucket_dc_url,
            credential=_credential(
                resolver,
                provider="bitbucket",
                env_var="NICO_BITBUCKET_DC_TOKEN",
                scheme="bearer",
                key_id=str(environ.get("NICO_BITBUCKET_DC_KEY_ID") or "production-bitbucket-dc"),
                hosts=(_https_host(bitbucket_dc_url),),
                scopes=("repository:read", "pullrequest:read", "build-status:read"),
            ),
            retry_policy=retry,
        )
        collectors[ProviderKind.BITBUCKET] = collector
        closeables.append(collector)
        configured["bitbucket_data_center"] = collector.credential.safe_metadata()

    azure_url = str(environ.get("NICO_AZURE_DEVOPS_URL") or "https://dev.azure.com").strip()
    azure_organization = str(environ.get("NICO_AZURE_DEVOPS_ORGANIZATION") or "").strip()
    azure_project = str(environ.get("NICO_AZURE_DEVOPS_PROJECT") or "").strip()
    if (
        str(environ.get("NICO_AZURE_DEVOPS_TOKEN") or "").strip()
        and azure_organization
        and azure_project
    ):
        collector = AzureDevOpsClient(
            instance_url=azure_url,
            organization=azure_organization,
            project=azure_project,
            credential=_credential(
                resolver,
                provider="azure_devops",
                env_var="NICO_AZURE_DEVOPS_TOKEN",
                scheme="basic_token",
                key_id=str(environ.get("NICO_AZURE_DEVOPS_KEY_ID") or "production-azure-devops"),
                hosts=(_https_host(azure_url),),
                scopes=("vso.code", "vso.build", "vso.work"),
            ),
            retry_policy=retry,
        )
        collectors[ProviderKind.AZURE_DEVOPS] = collector
        closeables.append(collector)
        configured["azure_devops"] = collector.credential.safe_metadata()

    for provider, env_var in (
        (ProviderKind.GITLAB, "NICO_GITLAB_WEBHOOK_SECRET"),
        (ProviderKind.BITBUCKET, "NICO_BITBUCKET_WEBHOOK_SECRET"),
        (ProviderKind.AZURE_DEVOPS, "NICO_AZURE_DEVOPS_WEBHOOK_SECRET"),
    ):
        value = str(environ.get(env_var) or "")
        if value:
            if provider not in collectors:
                raise RuntimeError("post_release_webhook_secret_without_collector")
            webhook_secrets[provider] = SecretValue(value)

    return collectors, webhook_secrets, closeables, {
        "configured": configured,
        "collectors": sorted(provider.value for provider in collectors),
        "webhook_secrets": sorted(provider.value for provider in webhook_secrets),
        "raw_secret_exposed": False,
    }


def build_app(
    *,
    base_app: FastAPI | None = None,
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    selected: Mapping[str, str] = dict(os.environ if environ is None else environ)
    if base_app is None:
        from nico.api.comprehensive_production_bootstrap import app as production_app

        target = production_app
    else:
        target = base_app

    enable_provider = _truthy(selected.get("NICO_ENABLE_PROVIDER_SYNC"))
    enable_monitor = _truthy(selected.get("NICO_ENABLE_MONITOR_EXECUTE"))
    connection_factory, dialect, storage = _database_dependencies(
        selected,
        required=enable_provider or enable_monitor,
    )
    collectors: dict[ProviderKind, Any] = {}
    webhook_secrets: dict[ProviderKind, SecretValue] = {}
    closeables: list[Any] = []
    provider_metadata: dict[str, Any] = {
        "configured": {},
        "collectors": [],
        "webhook_secrets": [],
        "raw_secret_exposed": False,
    }
    if enable_provider:
        collectors, webhook_secrets, closeables, provider_metadata = _provider_dependencies(selected)

    status = install_post_release_runtime(
        target,
        config=PostReleaseRuntimeConfig(
            enable_provider_sync=enable_provider,
            enable_monitor_execute=enable_monitor,
            database_dialect=dialect,
            provider_poll_interval_seconds=_positive_int(
                selected.get("NICO_PROVIDER_POLL_INTERVAL_SECONDS"),
                default=900,
                minimum=60,
                maximum=86400,
                code="post_release_provider_poll_interval_invalid",
            ),
            provider_max_failure_backoff_seconds=_positive_int(
                selected.get("NICO_PROVIDER_MAX_BACKOFF_SECONDS"),
                default=3600,
                minimum=60,
                maximum=604800,
                code="post_release_provider_backoff_invalid",
            ),
        ),
        dependencies=PostReleaseDependencies(
            connection_factory=connection_factory,
            provider_collectors=collectors,
            provider_webhook_secrets=webhook_secrets,
        ),
    )
    status["app_wrapper"] = VERSION
    status["storage"] = storage
    status["provider_configuration"] = provider_metadata
    target.state.nico_post_release_runtime = status
    target.state.nico_post_release_closeables = closeables

    if closeables and not getattr(target.state, "nico_post_release_shutdown_registered", False):
        def close_clients() -> None:
            for item in list(getattr(target.state, "nico_post_release_closeables", ()) or ()):
                close = getattr(item, "close", None)
                if callable(close):
                    close()

        target.router.add_event_handler("shutdown", close_clients)
        target.state.nico_post_release_shutdown_registered = True
    return target


app = build_app()


__all__ = ["VERSION", "app", "build_app"]