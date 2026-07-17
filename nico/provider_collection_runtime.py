from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping

from nico.provider_neutral_contract import Capability, ProviderKind, normalize_provider


class CollectionMode(str, Enum):
    API = "api"
    POLL = "poll"
    WEBHOOK = "webhook"
    GIT = "git"
    ARCHIVE = "archive"


class CollectionState(str, Enum):
    READY = "ready"
    PARTIAL = "partial"
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class PaginationCursor:
    token: str = ""
    page: int = 1
    complete: bool = False


@dataclass(frozen=True)
class RateLimitWindow:
    remaining: int | None = None
    reset_at: str = ""
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class CollectionRequest:
    provider: ProviderKind
    mode: CollectionMode
    repository_id: str
    requested_capabilities: tuple[Capability, ...]
    read_only: bool = True
    cursor: PaginationCursor = PaginationCursor()


@dataclass(frozen=True)
class CollectionResult:
    state: CollectionState
    provider: ProviderKind
    repository_id: str
    revision: str
    collected_capabilities: tuple[Capability, ...]
    missing_capabilities: tuple[Capability, ...] = ()
    cursor: PaginationCursor = PaginationCursor(complete=True)
    rate_limit: RateLimitWindow = RateLimitWindow()
    limitation_reason: str = ""
    collected_at: str = ""


def _text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_collection_mode(value: Any) -> CollectionMode:
    token = _text(value).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "rest": CollectionMode.API,
        "graphql": CollectionMode.API,
        "scheduled_poll": CollectionMode.POLL,
        "event": CollectionMode.WEBHOOK,
        "ssh": CollectionMode.GIT,
        "https": CollectionMode.GIT,
        "upload": CollectionMode.ARCHIVE,
    }
    if token in aliases:
        return aliases[token]
    return CollectionMode(token)


def pagination_from_mapping(data: Mapping[str, Any]) -> PaginationCursor:
    page_value = data.get("page", 1)
    try:
        page = max(1, int(page_value))
    except (TypeError, ValueError):
        page = 1
    return PaginationCursor(
        token=_text(data.get("token") or data.get("cursor") or data.get("next")),
        page=page,
        complete=bool(data.get("complete", False)),
    )


def rate_limit_from_mapping(data: Mapping[str, Any]) -> RateLimitWindow:
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    return RateLimitWindow(
        remaining=_int_or_none(data.get("remaining")),
        reset_at=_text(data.get("reset_at") or data.get("reset")),
        retry_after_seconds=_int_or_none(data.get("retry_after_seconds") or data.get("retry_after")),
    )


def build_collection_request(
    *,
    provider: Any,
    mode: Any,
    repository_id: Any,
    requested_capabilities: Iterable[Capability | str],
    read_only: bool = True,
    cursor: PaginationCursor | None = None,
) -> CollectionRequest:
    capabilities: list[Capability] = []
    seen: set[Capability] = set()
    for item in requested_capabilities:
        capability = item if isinstance(item, Capability) else Capability(_text(item).lower())
        if capability not in seen:
            seen.add(capability)
            capabilities.append(capability)
    return CollectionRequest(
        provider=provider if isinstance(provider, ProviderKind) else normalize_provider(provider),
        mode=mode if isinstance(mode, CollectionMode) else normalize_collection_mode(mode),
        repository_id=_text(repository_id),
        requested_capabilities=tuple(capabilities),
        read_only=bool(read_only),
        cursor=cursor or PaginationCursor(),
    )


def validate_collection_request(request: CollectionRequest) -> list[str]:
    issues: list[str] = []
    if not request.read_only:
        issues.append("collection_must_be_read_only")
    if not request.repository_id:
        issues.append("collection_repository_id_required")
    if Capability.REPOSITORY not in request.requested_capabilities:
        issues.append("collection_repository_capability_required")
    if request.provider is ProviderKind.ARCHIVE and request.mode is not CollectionMode.ARCHIVE:
        issues.append("archive_provider_requires_archive_mode")
    if request.provider is ProviderKind.GENERIC_GIT and request.mode is not CollectionMode.GIT:
        issues.append("generic_git_provider_requires_git_mode")
    return issues


def build_collection_result(
    *,
    request: CollectionRequest,
    revision: Any,
    collected_capabilities: Iterable[Capability | str],
    cursor: PaginationCursor | None = None,
    rate_limit: RateLimitWindow | None = None,
    auth_failed: bool = False,
    unavailable: bool = False,
    limitation_reason: Any = "",
    collected_at: Any = "",
) -> CollectionResult:
    collected: list[Capability] = []
    seen: set[Capability] = set()
    for item in collected_capabilities:
        capability = item if isinstance(item, Capability) else Capability(_text(item).lower())
        if capability not in seen:
            seen.add(capability)
            collected.append(capability)
    missing = tuple(item for item in request.requested_capabilities if item not in seen)
    limit = rate_limit or RateLimitWindow()
    reason = _text(limitation_reason)
    if auth_failed:
        state = CollectionState.AUTH_FAILED
    elif unavailable:
        state = CollectionState.UNAVAILABLE
    elif limit.remaining == 0 or (limit.retry_after_seconds is not None and limit.retry_after_seconds > 0):
        state = CollectionState.RATE_LIMITED
    elif not _text(revision):
        state = CollectionState.INVALID
    elif missing or not (cursor or PaginationCursor(complete=True)).complete:
        state = CollectionState.PARTIAL
    else:
        state = CollectionState.READY
    if state is not CollectionState.READY and not reason:
        reason = {
            CollectionState.AUTH_FAILED: "Provider authentication failed or expired.",
            CollectionState.UNAVAILABLE: "Provider service was unavailable during collection.",
            CollectionState.RATE_LIMITED: "Provider rate limit prevented complete collection.",
            CollectionState.INVALID: "An immutable repository revision was not supplied.",
            CollectionState.PARTIAL: "Requested provider evidence was only partially collected.",
        }.get(state, "")
    return CollectionResult(
        state=state,
        provider=request.provider,
        repository_id=request.repository_id,
        revision=_text(revision),
        collected_capabilities=tuple(collected),
        missing_capabilities=missing,
        cursor=cursor or PaginationCursor(complete=True),
        rate_limit=limit,
        limitation_reason=reason,
        collected_at=_text(collected_at) or _utc_now(),
    )


def validate_collection_result(request: CollectionRequest, result: CollectionResult) -> list[str]:
    issues: list[str] = []
    if result.provider != request.provider:
        issues.append("collection_provider_mismatch")
    if result.repository_id != request.repository_id:
        issues.append("collection_repository_mismatch")
    if result.state is CollectionState.READY:
        if not result.revision:
            issues.append("ready_collection_revision_required")
        if result.missing_capabilities:
            issues.append("ready_collection_cannot_have_missing_capabilities")
        if not result.cursor.complete:
            issues.append("ready_collection_pagination_must_be_complete")
    if result.state is not CollectionState.READY and not result.limitation_reason:
        issues.append("non_ready_collection_requires_limitation_reason")
    return issues


__all__ = [
    "CollectionMode",
    "CollectionRequest",
    "CollectionResult",
    "CollectionState",
    "PaginationCursor",
    "RateLimitWindow",
    "build_collection_request",
    "build_collection_result",
    "normalize_collection_mode",
    "pagination_from_mapping",
    "rate_limit_from_mapping",
    "validate_collection_request",
    "validate_collection_result",
]
