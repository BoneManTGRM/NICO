from __future__ import annotations

import re
from typing import Callable

import nico.hosted_assessment as hosted


_SEPARATOR_WHITESPACE = re.compile(r"\s*/\s*")
_GITHUB_PREFIX_WHITESPACE = re.compile(
    r"^(?P<prefix>(?:https?://github\.com/|git@github\.com:))\s+",
    re.IGNORECASE,
)


def canonical_repository_input(value: str) -> str:
    """Normalize only presentation whitespace around a GitHub owner/repo separator.

    Repository segment contents are deliberately untouched. The existing strict
    hosted parser remains authoritative and still rejects spaces or unsafe
    characters inside owner and repository names.
    """

    text = str(value or "").strip()
    text = _GITHUB_PREFIX_WHITESPACE.sub(lambda match: match.group("prefix"), text)
    return _SEPARATOR_WHITESPACE.sub("/", text)


def install_repository_input_normalization() -> dict[str, object]:
    if getattr(hosted, "_nico_repository_input_normalization_installed", False):
        return {
            "status": "already_installed",
            "version": "nico-repository-input-normalization-v1",
            "separator_whitespace_only": True,
            "strict_segment_validation_preserved": True,
        }

    original: Callable[[str], str] = hosted.normalize_repository

    def normalize_repository_with_separator_whitespace(value: str) -> str:
        return original(canonical_repository_input(value))

    hosted._nico_original_normalize_repository = original
    hosted.normalize_repository = normalize_repository_with_separator_whitespace
    hosted._nico_repository_input_normalization_installed = True
    return {
        "status": "installed",
        "version": "nico-repository-input-normalization-v1",
        "separator_whitespace_only": True,
        "strict_segment_validation_preserved": True,
        "truth_boundary": (
            "Only whitespace adjacent to the owner/repository separator is removed. "
            "Internal segment whitespace and all other invalid repository targets remain blocked."
        ),
    }


__all__ = ["canonical_repository_input", "install_repository_input_normalization"]
