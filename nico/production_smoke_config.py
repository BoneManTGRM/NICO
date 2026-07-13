from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import urlparse

CONFIRMATION_PHRASE = "AUTHORIZED_PRODUCTION_SMOKE"
SCHEMA_VERSION = 1
EVIDENCE_KIND = "authorized_live_production_smoke"
DEFAULT_POLL_ATTEMPTS = 200
DEFAULT_POLL_INTERVAL_SECONDS = 3.0
FULL_TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)
_FAILURE_STATUSES = {"blocked", "failed", "failure", "error", "rejected", "timed_out", "timeout"}
_REVIEW_KEYS = {"human_review_required", "human_approval_required"}
_CLIENT_READY_KEYS = {
    "client_ready",
    "client_delivery_allowed",
    "delivery_allowed",
    "approved_for_client_delivery",
}
_REPORT_ID_KEYS = ("report_id", "draft_report_id")
_REVIEW_ID_KEYS = ("approval_id", "review_request_id", "final_review_request_id")
_UNAVAILABLE_KEYS = {"unavailable_data_notes", "unavailable", "limitations"}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{1,119}$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SECRETISH_REFERENCE = re.compile(r"(?i)(?:^|[._:/-])(token|secret|password|bearer|credential|api[-_]?key)(?:$|[._:/-])")

class SmokeFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message

class Transport(Protocol):
    def request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        admin: bool = False,
    ) -> dict[str, Any]: ...

@dataclass(frozen=True)
class SmokeConfig:
    frontend_url: str
    backend_url: str
    repository: str
    customer_id: str
    project_id: str
    authorization_reference: str
    github_repository: str
    github_sha: str
    confirmation: str
    poll_attempts: int = DEFAULT_POLL_ATTEMPTS
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _csv_values(value: str) -> set[str]:
    return {item.strip().lower() for chunk in value.splitlines() for item in chunk.split(",") if item.strip()}

def normalize_repository(value: str) -> str:
    candidate = str(value or "").strip()
    if candidate.startswith("https://"):
        parsed = urlparse(candidate)
        if parsed.scheme != "https" or parsed.hostname != "github.com" or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise SmokeFailure("invalid_repository", "Repository must be an owner/name value or a clean HTTPS github.com URL.")
        candidate = parsed.path.strip("/")
        if candidate.endswith(".git"):
            candidate = candidate[:-4]
    candidate = candidate.strip("/")
    if not _REPOSITORY.fullmatch(candidate):
        raise SmokeFailure("invalid_repository", "Repository must contain exactly one owner/name pair.")
    return candidate

def validate_identifier(value: str, label: str) -> str:
    candidate = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(candidate):
        raise SmokeFailure("invalid_identifier", f"{label} must be a bounded non-secret identifier.")
    return candidate

def validate_authorization_reference(value: str) -> str:
    candidate = validate_identifier(value, "Authorization reference")
    if _SECRETISH_REFERENCE.search(candidate):
        raise SmokeFailure(
            "unsafe_authorization_reference",
            "Authorization reference must be a non-secret record identifier, not credential material.",
        )
    return candidate

def validate_sha(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if not _SHA.fullmatch(candidate):
        raise SmokeFailure("invalid_commit", "Workflow commit must be a full lowercase 40-character SHA.")
    return candidate

def validate_base_url(value: str, allowed_hosts: set[str], label: str) -> str:
    parsed = urlparse(str(value or "").strip())
    host = str(parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise SmokeFailure("invalid_url", f"{label} URL must use HTTPS.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SmokeFailure("unsafe_url", f"{label} URL must not contain credentials, query parameters, or fragments.")
    if parsed.path not in {"", "/"}:
        raise SmokeFailure("unsafe_url", f"{label} URL must be an origin without a path.")
    if parsed.port not in {None, 443}:
        raise SmokeFailure("unsafe_url", f"{label} URL must use the standard HTTPS port.")
    if host not in allowed_hosts:
        raise SmokeFailure("host_not_allowlisted", f"{label} host is not in the configured production allowlist.")
    return f"https://{host}"

def validate_config(config: SmokeConfig, environment: dict[str, str]) -> SmokeConfig:
    if config.confirmation != CONFIRMATION_PHRASE:
        raise SmokeFailure("confirmation_required", f"Operator confirmation must exactly equal {CONFIRMATION_PHRASE}.")
    allowed_repositories = _csv_values(environment.get("NICO_PRODUCTION_SMOKE_ALLOWLIST", ""))
    frontend_hosts = _csv_values(environment.get("NICO_PRODUCTION_SMOKE_FRONTEND_HOSTS", ""))
    backend_hosts = _csv_values(environment.get("NICO_PRODUCTION_SMOKE_BACKEND_HOSTS", ""))
    if not allowed_repositories or not frontend_hosts or not backend_hosts:
        raise SmokeFailure("allowlist_missing", "Production smoke repository and host allowlists must be configured before execution.")
    repository = normalize_repository(config.repository)
    if repository.lower() not in allowed_repositories:
        raise SmokeFailure("repository_not_allowlisted", "The requested repository is not in the authorized production-smoke allowlist.")
    if not environment.get("NICO_PRODUCTION_SMOKE_ADMIN_TOKEN", ""):
        raise SmokeFailure("admin_secret_missing", "The production-smoke admin secret is not configured.")
    if not environment.get("GITHUB_TOKEN", ""):
        raise SmokeFailure("github_token_missing", "The GitHub status token is not available to verify deployment checks.")
    poll_attempts = int(config.poll_attempts)
    poll_interval = float(config.poll_interval_seconds)
    if poll_attempts < 1 or poll_attempts > 400:
        raise SmokeFailure("invalid_poll_budget", "Poll attempts must be between 1 and 400.")
    if poll_interval < 0 or poll_interval > 30:
        raise SmokeFailure("invalid_poll_interval", "Poll interval must be between 0 and 30 seconds.")
    return SmokeConfig(
        frontend_url=validate_base_url(config.frontend_url, frontend_hosts, "Frontend"),
        backend_url=validate_base_url(config.backend_url, backend_hosts, "Backend"),
        repository=repository,
        customer_id=validate_identifier(config.customer_id, "Customer ID"),
        project_id=validate_identifier(config.project_id, "Project ID"),
        authorization_reference=validate_authorization_reference(config.authorization_reference),
        github_repository=normalize_repository(config.github_repository),
        github_sha=validate_sha(config.github_sha),
        confirmation=config.confirmation,
        poll_attempts=poll_attempts,
        poll_interval_seconds=poll_interval,
    )

