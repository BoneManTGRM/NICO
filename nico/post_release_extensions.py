from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlparse

from fastapi import FastAPI

from nico.notification_adapters import (
    EmailNotificationAdapter,
    SignedWebhookNotificationAdapter,
    SmtpSender,
)
from nico.notification_delivery import NotificationDispatcher, NotificationStore
from nico.operational_api import (
    HeaderOperationalAuthorizer,
    OperationalRuntime,
    register_operational_routes,
)
from nico.post_release_observability import MetricPoint, OperationalThresholds
from nico.provider_admin_api import (
    HeaderAdminAuthorizer,
    ProviderAdminRuntime,
    azure_boards_collector,
    bitbucket_issue_collector,
    gitlab_issue_collector,
    register_provider_admin_routes,
)
from nico.provider_credential_rotation import CredentialRotationLedger, CredentialRotationPolicy
from nico.provider_credentials import EnvironmentCredentialResolver, SecretValue, build_reference
from nico.provider_issue_clients import BitbucketCloudIssueClient, GitLabIssueClient
from nico.provider_live_clients import RetryPolicy
from nico.provider_neutral_contract import ProviderKind
from nico.provider_work_items import AzureBoardsClient


VERSION = "nico.post_release_extensions.v1"


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _positive_int(value: Any, *, default: int, minimum: int, maximum: int, code: str) -> int:
    token = str(value or "").strip()
    try:
        selected = default if not token else int(token)
    except ValueError as exc:
        raise RuntimeError(code) from exc
    if selected < minimum or selected > maximum:
        raise RuntimeError(code)
    return selected


def _positive_float(value: Any, *, default: float, minimum: float, maximum: float, code: str) -> float:
    token = str(value or "").strip()
    try:
        selected = default if not token else float(token)
    except ValueError as exc:
        raise RuntimeError(code) from exc
    if selected < minimum or selected > maximum:
        raise RuntimeError(code)
    return selected


def _https_host(url: str) -> str:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("post_release_extension_https_url_required")
    return parsed.hostname.lower()


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


def _retry_policy(environ: Mapping[str, str]) -> RetryPolicy:
    policy = RetryPolicy(
        max_attempts=_positive_int(
            environ.get("NICO_PROVIDER_MAX_ATTEMPTS"),
            default=4,
            minimum=1,
            maximum=10,
            code="post_release_extension_provider_attempts_invalid",
        ),
        base_delay_seconds=_positive_float(
            environ.get("NICO_PROVIDER_BASE_DELAY_SECONDS"),
            default=1.0,
            minimum=0.0,
            maximum=300.0,
            code="post_release_extension_provider_base_delay_invalid",
        ),
        max_delay_seconds=_positive_float(
            environ.get("NICO_PROVIDER_MAX_DELAY_SECONDS"),
            default=30.0,
            minimum=0.0,
            maximum=3600.0,
            code="post_release_extension_provider_max_delay_invalid",
        ),
        timeout_seconds=_positive_float(
            environ.get("NICO_PROVIDER_TIMEOUT_SECONDS"),
            default=45.0,
            minimum=1.0,
            maximum=300.0,
            code="post_release_extension_provider_timeout_invalid",
        ),
        max_pages=_positive_int(
            environ.get("NICO_PROVIDER_MAX_PAGES"),
            default=200,
            minimum=1,
            maximum=5000,
            code="post_release_extension_provider_pages_invalid",
        ),
    )
    policy.validate()
    return policy


def _admin_collectors(
    environ: Mapping[str, str],
) -> tuple[dict[ProviderKind, Callable[..., Any]], list[Any], dict[str, Any]]:
    resolver = EnvironmentCredentialResolver(environ)
    retry = _retry_policy(environ)
    collectors: dict[ProviderKind, Callable[..., Any]] = {}
    closeables: list[Any] = []
    configured: dict[str, Any] = {}

    gitlab_url = str(environ.get("NICO_GITLAB_URL") or "").strip()
    if gitlab_url and str(environ.get("NICO_GITLAB_TOKEN") or "").strip():
        credential = _credential(
            resolver,
            provider="gitlab",
            env_var="NICO_GITLAB_TOKEN",
            scheme="private_token",
            key_id=str(environ.get("NICO_GITLAB_KEY_ID") or "production-gitlab"),
            hosts=(_https_host(gitlab_url),),
            scopes=("read_api", "read_repository"),
        )
        client = GitLabIssueClient(
            instance_url=gitlab_url,
            credential=credential,
            retry_policy=retry,
        )
        collectors[ProviderKind.GITLAB] = gitlab_issue_collector(client)
        closeables.append(client)
        configured[ProviderKind.GITLAB.value] = credential.safe_metadata()

    bitbucket_url = str(
        environ.get("NICO_BITBUCKET_CLOUD_URL") or "https://api.bitbucket.org"
    ).strip()
    if str(environ.get("NICO_BITBUCKET_CLOUD_TOKEN") or "").strip():
        credential = _credential(
            resolver,
            provider="bitbucket",
            env_var="NICO_BITBUCKET_CLOUD_TOKEN",
            scheme="bearer",
            key_id=str(environ.get("NICO_BITBUCKET_CLOUD_KEY_ID") or "production-bitbucket-cloud"),
            hosts=(_https_host(bitbucket_url),),
            scopes=("repository:read", "issue:read"),
        )
        client = BitbucketCloudIssueClient(
            instance_url=bitbucket_url,
            credential=credential,
            retry_policy=retry,
        )
        collectors[ProviderKind.BITBUCKET] = bitbucket_issue_collector(client)
        closeables.append(client)
        configured[ProviderKind.BITBUCKET.value] = credential.safe_metadata()

    azure_url = str(environ.get("NICO_AZURE_DEVOPS_URL") or "https://dev.azure.com").strip()
    azure_org = str(environ.get("NICO_AZURE_DEVOPS_ORGANIZATION") or "").strip()
    azure_project = str(environ.get("NICO_AZURE_DEVOPS_PROJECT") or "").strip()
    if (
        str(environ.get("NICO_AZURE_DEVOPS_TOKEN") or "").strip()
        and azure_org
        and azure_project
    ):
        credential = _credential(
            resolver,
            provider="azure_devops",
            env_var="NICO_AZURE_DEVOPS_TOKEN",
            scheme="basic_token",
            key_id=str(environ.get("NICO_AZURE_DEVOPS_KEY_ID") or "production-azure-devops"),
            hosts=(_https_host(azure_url),),
            scopes=("vso.work",),
        )
        client = AzureBoardsClient(
            instance_url=azure_url,
            organization=azure_org,
            project=azure_project,
            credential=credential,
            retry_policy=retry,
        )
        collectors[ProviderKind.AZURE_DEVOPS] = azure_boards_collector(client)
        closeables.append(client)
        configured[ProviderKind.AZURE_DEVOPS.value] = credential.safe_metadata()

    return collectors, closeables, {
        "collectors": sorted(provider.value for provider in collectors),
        "configured": configured,
        "raw_secret_exposed": False,
    }


def _notification_adapters(
    environ: Mapping[str, str],
) -> tuple[dict[str, Any], list[Any], dict[str, Any]]:
    adapters: dict[str, Any] = {}
    closeables: list[Any] = []
    configured: list[str] = []

    webhook_url = str(environ.get("NICO_NOTIFICATION_WEBHOOK_URL") or "").strip()
    webhook_secret = str(environ.get("NICO_NOTIFICATION_WEBHOOK_SECRET") or "")
    if webhook_url or webhook_secret:
        if not webhook_url or not webhook_secret:
            raise RuntimeError("post_release_notification_webhook_configuration_incomplete")
        adapter = SignedWebhookNotificationAdapter(
            destination="webhook",
            url=webhook_url,
            signing_secret=SecretValue(webhook_secret),
            allowed_hosts=(_https_host(webhook_url),),
            timeout_seconds=_positive_float(
                environ.get("NICO_NOTIFICATION_TIMEOUT_SECONDS"),
                default=20.0,
                minimum=1.0,
                maximum=120.0,
                code="post_release_notification_timeout_invalid",
            ),
        )
        adapters[adapter.destination] = adapter
        closeables.append(adapter)
        configured.append(adapter.destination)

    smtp_host = str(environ.get("NICO_SMTP_HOST") or "").strip()
    email_from = str(environ.get("NICO_NOTIFICATION_EMAIL_FROM") or "").strip()
    email_to = tuple(
        item.strip()
        for item in str(environ.get("NICO_NOTIFICATION_EMAIL_TO") or "").split(",")
        if item.strip()
    )
    if smtp_host or email_from or email_to:
        if not smtp_host or not email_from or not email_to:
            raise RuntimeError("post_release_notification_email_configuration_incomplete")
        username = str(environ.get("NICO_SMTP_USERNAME") or "").strip()
        password_value = str(environ.get("NICO_SMTP_PASSWORD") or "")
        sender = SmtpSender(
            host=smtp_host,
            port=_positive_int(
                environ.get("NICO_SMTP_PORT"),
                default=465,
                minimum=1,
                maximum=65535,
                code="post_release_smtp_port_invalid",
            ),
            username=username,
            password=SecretValue(password_value) if password_value else None,
            timeout_seconds=_positive_float(
                environ.get("NICO_NOTIFICATION_TIMEOUT_SECONDS"),
                default=20.0,
                minimum=1.0,
                maximum=120.0,
                code="post_release_notification_timeout_invalid",
            ),
            use_ssl=not _truthy(environ.get("NICO_SMTP_USE_STARTTLS")),
        )
        adapter = EmailNotificationAdapter(
            destination="email",
            from_address=email_from,
            to_addresses=email_to,
            sender=sender,
        )
        adapters[adapter.destination] = adapter
        configured.append(adapter.destination)

    return adapters, closeables, {
        "adapters": sorted(configured),
        "raw_secret_exposed": False,
    }


def _counter(target: FastAPI, name: str) -> int:
    try:
        return max(0, int(getattr(target.state, name, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _metric_provider(
    target: FastAPI,
    connection_factory: Callable[[], Any],
) -> Callable[[], Iterable[MetricPoint]]:
    def provide() -> tuple[MetricPoint, ...]:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        started = time.perf_counter()
        storage_available = 1.0
        queue_depth = 0
        connection = None
        try:
            connection = connection_factory()
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM nico_notification_delivery WHERE status IN ('pending', 'retry')"
                )
                row = cursor.fetchone()
                queue_depth = int(row[0]) if row else 0
            except Exception:
                queue_depth = 0
        except Exception:
            storage_available = 0.0
        finally:
            if connection is not None:
                connection.close()
        latency_ms = (time.perf_counter() - started) * 1000.0
        return (
            MetricPoint("storage_available", storage_available, timestamp),
            MetricPoint("storage_latency_ms", latency_ms, timestamp),
            MetricPoint("queue_depth", queue_depth, timestamp),
            MetricPoint(
                "provider_collection_failures",
                _counter(target, "nico_provider_collection_failures"),
                timestamp,
            ),
            MetricPoint(
                "report_generation_failures",
                _counter(target, "nico_report_generation_failures"),
                timestamp,
            ),
            MetricPoint(
                "delivery_gate_blocks",
                _counter(target, "nico_delivery_gate_blocks"),
                timestamp,
            ),
            MetricPoint(
                "delivery_failures",
                _counter(target, "nico_delivery_failures"),
                timestamp,
            ),
            MetricPoint("active_runs", _counter(target, "nico_active_runs"), timestamp),
            MetricPoint("stale_runs", _counter(target, "nico_stale_runs"), timestamp),
        )

    return provide


def _exact_sha(environ: Mapping[str, str]) -> str:
    for key in (
        "NICO_EXACT_SHA",
        "RAILWAY_GIT_COMMIT_SHA",
        "VERCEL_GIT_COMMIT_SHA",
        "GIT_COMMIT_SHA",
        "SOURCE_COMMIT",
    ):
        value = str(environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _forbidden_values(environ: Mapping[str, str]) -> tuple[str, ...]:
    sensitive = (
        "DATABASE_URL",
        "NICO_PROVIDER_ADMIN_TOKEN",
        "NICO_OPERATIONAL_TOKEN",
        "NICO_GITLAB_TOKEN",
        "NICO_BITBUCKET_CLOUD_TOKEN",
        "NICO_BITBUCKET_DC_TOKEN",
        "NICO_AZURE_DEVOPS_TOKEN",
        "NICO_NOTIFICATION_WEBHOOK_SECRET",
        "NICO_SMTP_PASSWORD",
    )
    return tuple(str(environ.get(key) or "") for key in sensitive if str(environ.get(key) or ""))


def install_post_release_extensions(
    target: FastAPI,
    *,
    environ: Mapping[str, str],
    connection_factory: Callable[[], Any] | None,
    database_dialect: str,
) -> tuple[dict[str, Any], list[Any]]:
    enable_admin = _truthy(environ.get("NICO_ENABLE_PROVIDER_ADMIN"))
    enable_operational = _truthy(environ.get("NICO_ENABLE_OPERATIONAL_API"))
    closeables: list[Any] = []
    status: dict[str, Any] = {
        "artifact_schema": VERSION,
        "provider_admin": {
            "enabled": enable_admin,
            "status": "disabled" if not enable_admin else "blocked",
            "reason": "feature_disabled" if not enable_admin else "not_configured",
        },
        "operational_api": {
            "enabled": enable_operational,
            "status": "disabled" if not enable_operational else "blocked",
            "reason": "feature_disabled" if not enable_operational else "not_configured",
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
        "raw_secret_exposed": False,
    }

    if (enable_admin or enable_operational) and connection_factory is None:
        reason = "durable_database_not_configured"
        if enable_admin:
            status["provider_admin"]["reason"] = reason
        if enable_operational:
            status["operational_api"]["reason"] = reason
        return status, closeables

    if enable_admin:
        admin_token = str(environ.get("NICO_PROVIDER_ADMIN_TOKEN") or "")
        if not admin_token:
            status["provider_admin"]["reason"] = "provider_admin_token_not_configured"
        else:
            collectors, clients, metadata = _admin_collectors(environ)
            closeables.extend(clients)
            if not collectors:
                status["provider_admin"]["reason"] = "provider_admin_collectors_not_configured"
            else:
                policy = CredentialRotationPolicy(
                    max_age_days=_positive_int(
                        environ.get("NICO_CREDENTIAL_MAX_AGE_DAYS"),
                        default=90,
                        minimum=1,
                        maximum=365,
                        code="post_release_credential_max_age_invalid",
                    ),
                    minimum_overlap_minutes=_positive_int(
                        environ.get("NICO_CREDENTIAL_MINIMUM_OVERLAP_MINUTES"),
                        default=15,
                        minimum=0,
                        maximum=1440,
                        code="post_release_credential_minimum_overlap_invalid",
                    ),
                    maximum_overlap_hours=_positive_int(
                        environ.get("NICO_CREDENTIAL_MAXIMUM_OVERLAP_HOURS"),
                        default=24,
                        minimum=1,
                        maximum=720,
                        code="post_release_credential_maximum_overlap_invalid",
                    ),
                    require_dual_control=True,
                )
                runtime = ProviderAdminRuntime(
                    authorizer=HeaderAdminAuthorizer(SecretValue(admin_token)),
                    credential_ledger=CredentialRotationLedger(
                        connection_factory,
                        dialect=database_dialect,
                    ),
                    rotation_policy=policy,
                    work_item_collectors=collectors,
                )
                register_provider_admin_routes(target, runtime=runtime)
                status["provider_admin"] = {
                    "enabled": True,
                    "status": "ready",
                    "reason": "",
                    **metadata,
                    "credential_rotation_dual_control": True,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }

    if enable_operational:
        operational_token = str(environ.get("NICO_OPERATIONAL_TOKEN") or "")
        exact_sha = _exact_sha(environ)
        if not operational_token:
            status["operational_api"]["reason"] = "operational_token_not_configured"
        elif not exact_sha:
            status["operational_api"]["reason"] = "operational_exact_sha_not_configured"
        else:
            adapters, adapter_closeables, metadata = _notification_adapters(environ)
            closeables.extend(adapter_closeables)
            if not adapters:
                status["operational_api"]["reason"] = "notification_adapters_not_configured"
            else:
                store = NotificationStore(connection_factory, dialect=database_dialect)
                dispatcher = NotificationDispatcher(
                    store,
                    adapters,
                    max_attempts=_positive_int(
                        environ.get("NICO_NOTIFICATION_MAX_ATTEMPTS"),
                        default=5,
                        minimum=1,
                        maximum=20,
                        code="post_release_notification_attempts_invalid",
                    ),
                    base_retry_seconds=_positive_int(
                        environ.get("NICO_NOTIFICATION_BASE_RETRY_SECONDS"),
                        default=60,
                        minimum=1,
                        maximum=86400,
                        code="post_release_notification_base_retry_invalid",
                    ),
                    max_retry_seconds=_positive_int(
                        environ.get("NICO_NOTIFICATION_MAX_RETRY_SECONDS"),
                        default=3600,
                        minimum=1,
                        maximum=604800,
                        code="post_release_notification_max_retry_invalid",
                    ),
                )
                runtime = OperationalRuntime(
                    authorizer=HeaderOperationalAuthorizer(SecretValue(operational_token)),
                    exact_sha_provider=lambda: exact_sha,
                    metric_provider=_metric_provider(target, connection_factory),
                    log_sample_provider=lambda: (),
                    forbidden_log_value_provider=lambda: _forbidden_values(environ),
                    notification_store=store,
                    notification_dispatcher=dispatcher,
                    thresholds=OperationalThresholds(
                        max_storage_latency_ms=_positive_float(
                            environ.get("NICO_MAX_STORAGE_LATENCY_MS"),
                            default=500.0,
                            minimum=1.0,
                            maximum=60000.0,
                            code="post_release_storage_latency_threshold_invalid",
                        ),
                        max_queue_depth=_positive_int(
                            environ.get("NICO_MAX_NOTIFICATION_QUEUE_DEPTH"),
                            default=100,
                            minimum=0,
                            maximum=1_000_000,
                            code="post_release_queue_threshold_invalid",
                        ),
                        max_provider_failures=_positive_int(
                            environ.get("NICO_MAX_PROVIDER_FAILURES"),
                            default=5,
                            minimum=0,
                            maximum=1_000_000,
                            code="post_release_provider_failure_threshold_invalid",
                        ),
                        max_report_failures=_positive_int(
                            environ.get("NICO_MAX_REPORT_FAILURES"),
                            default=1,
                            minimum=0,
                            maximum=1_000_000,
                            code="post_release_report_failure_threshold_invalid",
                        ),
                        max_delivery_failures=_positive_int(
                            environ.get("NICO_MAX_DELIVERY_FAILURES"),
                            default=1,
                            minimum=0,
                            maximum=1_000_000,
                            code="post_release_delivery_failure_threshold_invalid",
                        ),
                        max_stale_runs=_positive_int(
                            environ.get("NICO_MAX_STALE_RUNS"),
                            default=0,
                            minimum=0,
                            maximum=1_000_000,
                            code="post_release_stale_run_threshold_invalid",
                        ),
                    ),
                )
                register_operational_routes(target, runtime=runtime)
                status["operational_api"] = {
                    "enabled": True,
                    "status": "ready",
                    "reason": "",
                    **metadata,
                    "exact_sha_present": True,
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                }

    return status, closeables


__all__ = ["VERSION", "install_post_release_extensions"]
