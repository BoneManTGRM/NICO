from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive_post_readiness_maturity_truth.v3"
_MARKER = "__nico_post_readiness_maturity_truth_v3__"
_LABEL_FIELDS = frozenset(
    {
        "maturity",
        "maturity_label",
        "maturity_level",
        "maturity_rating",
        "maturity_tier",
    }
)
_HEAVY_FIELDS = frozenset({"pdf_base64", "markdown", "html", "report_package"})
_EXPLICIT_TEXT_PATTERNS = (
    re.compile(
        r"(?P<prefix>\bmaturity_(?:level|label|rating|tier)\s*[:=]\s*)"
        r"(?P<value>[^\n,;|}\]]+)",
        re.I,
    ),
    re.compile(
        r"(?P<prefix>\bmaturity\s+(?:level|label|rating|tier)\s*[:=]\s*)"
        r"(?P<value>[^\n,;|}\]]+)",
        re.I,
    ),
)


def _text(value: Any, limit: int = 240) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _label(output: Mapping[str, Any]) -> str:
    contract = _mapping(output.get("client_readiness_contract"))
    label = _text(contract.get("maturity_label"), 100)
    if label and label.casefold() not in {
        "not scored",
        "not assessed",
        "unknown",
        "unavailable",
        "none",
        "n/a",
    }:
        return label
    return ""


def _maturity_context(path: str) -> bool:
    lowered = path.casefold()
    return (
        "maturity_signal" in lowered
        or ".maturity" in lowered
        or lowered.endswith("maturity")
    )


def synchronize_explicit_maturity_text(value: str, canonical_label: str) -> str:
    """Replace only explicit maturity-label text aliases.

    General seniority prose, role labels, and ordinary uses of words such as ``Senior``
    are intentionally outside this contract.
    """

    label = _text(canonical_label, 100)
    if not label or label.casefold() == "not scored":
        return value
    output = value
    for pattern in _EXPLICIT_TEXT_PATTERNS:
        output = pattern.sub(
            lambda match: (
                match.group(0)
                if _text(match.group("value"), 100).casefold() == label.casefold()
                else f"{match.group('prefix')}{label}"
            ),
            output,
        )
    return output


def _synchronize(
    node: Any,
    *,
    canonical_label: str,
    path: str,
    replacements: list[dict[str, str]],
) -> Any:
    if isinstance(node, str):
        updated = synchronize_explicit_maturity_text(node, canonical_label)
        if updated != node:
            # Never retain the stale client-visible sentence in the canonical manifest.
            # The path, replacement type, and canonical label are sufficient audit data.
            replacements.append(
                {
                    "path": path,
                    "canonical": canonical_label,
                    "kind": "explicit_text_alias",
                    "original_text_retained": "false",
                }
            )
        return updated
    if isinstance(node, list):
        return [
            _synchronize(
                value,
                canonical_label=canonical_label,
                path=f"{path}[{index}]",
                replacements=replacements,
            )
            for index, value in enumerate(node)
        ]
    if isinstance(node, tuple):
        return tuple(
            _synchronize(
                value,
                canonical_label=canonical_label,
                path=f"{path}[{index}]",
                replacements=replacements,
            )
            for index, value in enumerate(node)
        )
    if not isinstance(node, Mapping):
        return deepcopy(node)

    output: dict[str, Any] = {}
    for raw_key, raw_value in node.items():
        key = str(raw_key)
        lowered = key.casefold()
        current_path = f"{path}.{key}" if path else key
        if lowered in _HEAVY_FIELDS:
            output[key] = raw_value
            continue

        is_label = lowered in _LABEL_FIELDS
        nested_label = lowered in {"level", "label"} and _maturity_context(path)
        if (is_label or nested_label) and isinstance(raw_value, str):
            observed = _text(raw_value, 100)
            if observed and observed.casefold() != canonical_label.casefold():
                replacements.append(
                    {
                        "path": current_path,
                        "observed_label": observed,
                        "canonical": canonical_label,
                        "kind": "structured_alias",
                    }
                )
            output[key] = canonical_label
            continue

        output[key] = _synchronize(
            raw_value,
            canonical_label=canonical_label,
            path=current_path,
            replacements=replacements,
        )
    return output


def synchronize_post_readiness_maturity_truth(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    label = _label(canonical)
    if not label:
        return deepcopy(dict(canonical)), {
            "status": "not_applied",
            "version": VERSION,
            "reason": "canonical_client_readiness_maturity_label_unavailable",
            "canonical_label": "",
            "replacement_count": 0,
            "replacements": [],
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    replacements: list[dict[str, str]] = []
    synchronized = _synchronize(
        canonical,
        canonical_label=label,
        path="canonical",
        replacements=replacements,
    )
    if not isinstance(synchronized, dict):
        raise TypeError("post_readiness_maturity_truth_must_be_mapping")
    manifest = {
        "status": "applied",
        "version": VERSION,
        "canonical_label": label,
        "canonical_source": "client_readiness_contract.maturity_label",
        "replacement_count": len(replacements),
        "replacements": replacements[:100],
        "post_readiness_boundary": True,
        "explicit_maturity_aliases_only": True,
        "stale_client_text_retained_in_manifest": False,
        "unrelated_seniority_preserved": True,
        "scores_changed": False,
        "scanner_results_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    synchronized["post_readiness_maturity_truth"] = deepcopy(manifest)
    assessment = synchronized.get("assessment")
    if isinstance(assessment, Mapping):
        assessment_copy = dict(assessment)
        assessment_copy["post_readiness_maturity_truth"] = deepcopy(manifest)
        synchronized["assessment"] = assessment_copy
    return synchronized, manifest


def install_post_readiness_maturity_truth() -> dict[str, Any]:
    """Wrap the readiness reconciler after it has created its maturity contract."""

    from nico import comprehensive_client_readiness_v59 as readiness

    current = readiness.reconcile_client_readiness
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
        }

    @wraps(current)
    def reconcile(canonical: Mapping[str, Any]) -> dict[str, Any]:
        ready = current(canonical)
        synchronized, manifest = synchronize_post_readiness_maturity_truth(ready)
        synchronized["post_readiness_maturity_truth"] = deepcopy(manifest)
        synchronized["human_review_required"] = True
        synchronized["client_delivery_allowed"] = False
        return synchronized

    setattr(reconcile, _MARKER, True)
    setattr(reconcile, "_nico_previous", current)
    readiness.reconcile_client_readiness = reconcile
    return {
        "status": "installed",
        "version": VERSION,
        "bound": readiness.reconcile_client_readiness is reconcile,
        "post_readiness_boundary": True,
        "explicit_maturity_aliases_only": True,
        "stale_client_text_retained_in_manifest": False,
        "strict_semantic_validation_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_post_readiness_maturity_truth",
    "synchronize_explicit_maturity_text",
    "synchronize_post_readiness_maturity_truth",
]
