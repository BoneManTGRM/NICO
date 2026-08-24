from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.provider-locale-semantic-parity.v1"

_LOCALE_ONLY_KEYS = frozenset(
    {
        "locale",
        "report_language",
        "requested_report_language",
        "ui_locale",
        "language",
    }
)


def locale_neutral_canonical(value: Mapping[str, Any]) -> dict[str, Any]:
    """Remove presentation-locale selectors while preserving assessment truth exactly."""

    def normalize(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                str(key): normalize(child)
                for key, child in item.items()
                if str(key) not in _LOCALE_ONLY_KEYS
            }
        if isinstance(item, list):
            return [normalize(child) for child in item]
        if isinstance(item, tuple):
            return [normalize(child) for child in item]
        return deepcopy(item)

    return normalize(value)


def locale_neutral_truth_sha256(value: Mapping[str, Any]) -> str:
    normalized = locale_neutral_canonical(value)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_locale_semantic_parity(
    english_canonical: Mapping[str, Any],
    spanish_canonical: Mapping[str, Any],
) -> str:
    english_digest = locale_neutral_truth_sha256(english_canonical)
    spanish_digest = locale_neutral_truth_sha256(spanish_canonical)
    if english_digest != spanish_digest:
        raise ValueError(
            "locale_canonical_semantic_mismatch:"
            f"en={english_digest}:es={spanish_digest}"
        )
    return english_digest


__all__ = [
    "VERSION",
    "assert_locale_semantic_parity",
    "locale_neutral_canonical",
    "locale_neutral_truth_sha256",
]
