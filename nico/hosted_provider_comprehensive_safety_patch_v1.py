from __future__ import annotations

import re
from typing import Any

from nico import hosted_provider_comprehensive_runtime_v1 as runtime

VERSION = "nico.hosted-provider-comprehensive-safety-patch.v1"
_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_MARKER = "_nico_hosted_provider_strict_path_v1"


def strict_safe_path(value: Any, *, minimum_parts: int = 2) -> str:
    raw = str(value or "").strip()
    if not raw or raw.startswith("/") or raw.endswith("/"):
        raise ValueError("provider_repository_invalid")
    if "\\" in raw or "\x00" in raw or "\r" in raw or "\n" in raw:
        raise ValueError("provider_repository_invalid")
    parts = raw.split("/")
    if len(parts) < minimum_parts:
        raise ValueError("provider_repository_invalid")
    if any(
        part in {"", ".", ".."}
        or not _SAFE_SEGMENT_RE.fullmatch(part)
        for part in parts
    ):
        raise ValueError("provider_repository_invalid")
    return "/".join(parts)


def install_hosted_provider_comprehensive_safety_patch() -> dict[str, Any]:
    current = runtime._safe_path
    if not getattr(current, _MARKER, False):
        setattr(strict_safe_path, _MARKER, True)
        setattr(strict_safe_path, "_nico_previous", current)
        runtime._safe_path = strict_safe_path
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "strict_repository_coordinates": True,
        "dot_segments_rejected": True,
        "backslash_rejected": True,
        "control_characters_rejected": True,
        "arbitrary_urls_rejected": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_hosted_provider_comprehensive_safety_patch",
    "strict_safe_path",
]
