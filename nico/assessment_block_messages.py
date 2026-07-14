from __future__ import annotations

import re
from typing import Any, Callable

from fastapi import HTTPException

from nico.express_async_api import register_express_async_routes

SAFE_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_CODE_RE = re.compile(r"^[a-z0-9_]{1,80}$")
_PATCH_MARKER = "_nico_actionable_assessment_blocks_v1"

_BLOCK_MESSAGES: dict[str, tuple[str, str | None]] = {
    "authorization_required": (
        "Confirm that you own this repository or have explicit permission to assess it, then try again.",
        "authorization",
    ),
    "invalid_repository": (
        "Enter the repository as owner/name or paste a complete GitHub repository URL.",
        "repository",
    ),
    "repository_not_found_or_inaccessible": (
        "The repository could not be found or accessed. Check the owner/repository spelling. For a private repository, verify that NICO's backend GitHub authorization can access it.",
        "repository",
    ),
    "github_temporarily_unavailable": (
        "NICO could not complete the GitHub repository check within the bounded request window. Wait briefly and try again; for a private repository, also verify backend GitHub access.",
        "repository",
    ),
}


def _safe_code(value: Any) -> str:
    code = str(value or "").strip().lower().replace("-", "_")
    return code if SAFE_CODE_RE.fullmatch(code) else ""


def classify_assessment_block(result: dict[str, Any]) -> str:
    explicit = _safe_code(result.get("code"))
    if explicit in _BLOCK_MESSAGES and explicit != "authorization_required":
        return explicit

    error = str(result.get("error") or result.get("reason") or "").strip().lower()
    if "explicit authorization is required before nico assesses a repository" in error:
        return "authorization_required"
    if "repository must be owner/name" in error or "github repository url" in error:
        return "invalid_repository"
    if "repository metadata unavailable" in error:
        if any(marker in error for marker in ("http 404", "http 401", "http 403")):
            return "repository_not_found_or_inaccessible"
        if any(marker in error for marker in ("time budget", "bounded collection", "did not complete", "http 429", "http 5")):
            return "github_temporarily_unavailable"
        return "repository_not_found_or_inaccessible"
    return "blocked" if explicit == "authorization_required" else explicit or "blocked"


def assessment_block_detail(result: dict[str, Any]) -> dict[str, Any]:
    code = classify_assessment_block(result)
    message, field = _BLOCK_MESSAGES.get(
        code,
        ("Request blocked by NICO safety, authorization, or review policy.", None),
    )
    detail: dict[str, Any] = {
        "status": "blocked",
        "code": code,
        "message": message,
    }
    if field:
        detail["field"] = field
    repository = str(result.get("repository") or "").strip()
    if field == "repository" and SAFE_REPOSITORY_RE.fullmatch(repository):
        detail["repository"] = repository
        if code == "repository_not_found_or_inaccessible":
            detail["message"] = (
                f"Repository '{repository}' could not be found or accessed. "
                "Check the owner/repository spelling. For a private repository, verify that NICO's backend GitHub authorization can access it."
            )
    return detail


def actionable_blocked_exception(result: dict[str, Any]) -> HTTPException:
    return HTTPException(status_code=400, detail=assessment_block_detail(result))


def install_assessment_block_messages() -> dict[str, Any]:
    """Install actionable public block messages and the quick Express lifecycle."""

    import nico.api.main as api_main

    current: Callable[[dict[str, Any]], HTTPException] = api_main.safe_blocked_exception
    already_installed = bool(getattr(current, _PATCH_MARKER, False))
    if not already_installed:
        setattr(actionable_blocked_exception, _PATCH_MARKER, True)
        setattr(actionable_blocked_exception, "_nico_blocked_exception_fallback", current)
        api_main.safe_blocked_exception = actionable_blocked_exception
    express_async = register_express_async_routes(api_main.app)
    return {
        "status": "already_installed" if already_installed else "installed",
        "raw_provider_detail_exposed": False,
        "classified_codes": sorted(_BLOCK_MESSAGES),
        "express_async": express_async,
    }


__all__ = [
    "actionable_blocked_exception",
    "assessment_block_detail",
    "classify_assessment_block",
    "install_assessment_block_messages",
]
