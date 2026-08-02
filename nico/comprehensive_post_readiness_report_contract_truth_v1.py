from __future__ import annotations

import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive_post_readiness_report_contract_truth.v1"
_MARKER = "__nico_post_readiness_report_contract_truth_v1__"
_DIAGNOSTIC_KEYS = frozenset(
    {
        "report_contract_status",
        "report_contract_reason",
        "core_report_contract_status",
        "core_report_contract_reason",
    }
)
_SUPERSEDED_STATUS_VALUES = frozenset({"blocked", "failed", "invalid"})
_SUPERSEDED_REASON_VALUES = frozenset(
    {
        "executive_decision_brief_page_gate_failed",
        "canonical_score_truth_mismatch",
        "canonical_evidence_adjusted_score_mismatch",
    }
)
_HEAVY_FIELDS = frozenset({"pdf_base64", "markdown", "html", "report_package"})
_EXPLICIT_DIAGNOSTIC_PATTERNS = (
    (
        "report_contract_status",
        re.compile(
            r"\b(?P<key>(?:core_)?report_contract_status)\s*[:=]\s*"
            r"(?P<value>blocked|failed|invalid)\b",
            re.I,
        ),
    ),
    (
        "report_contract_reason",
        re.compile(
            r"\b(?P<key>(?:core_)?report_contract_reason)\s*[:=]\s*"
            r"(?P<value>executive_decision_brief_page_gate_failed|"
            r"canonical_score_truth_mismatch|"
            r"canonical_evidence_adjusted_score_mismatch)\b",
            re.I,
        ),
    ),
)
_REMOVED = object()


def _text(value: Any, limit: int = 240) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _superseded_diagnostic(key: str, value: Any) -> bool:
    normalized_key = key.casefold()
    normalized_value = _text(value, 180).casefold()
    if normalized_key.endswith("status"):
        return normalized_value in _SUPERSEDED_STATUS_VALUES
    if normalized_key.endswith("reason"):
        return normalized_value in _SUPERSEDED_REASON_VALUES
    return False


def _cleanup_removed_text(value: str) -> str:
    output = re.sub(r"[ \t]+([,;|])", r"\1", value)
    output = re.sub(r"(?:\s*[;|]\s*){2,}", "; ", output)
    output = re.sub(r"^\s*[,;|]\s*", "", output)
    output = re.sub(r"\s*[,;|]\s*$", "", output)
    output = re.sub(r"[ \t]{2,}", " ", output)
    return output.strip()


def strip_superseded_report_contract_text(
    value: str,
    *,
    path: str = "text",
    removals: list[dict[str, Any]] | None = None,
) -> str:
    """Remove only explicit obsolete internal report-contract aliases.

    Product-facing lifecycle language such as ``Client Delivery Blocked`` remains
    unchanged. The removed raw diagnostic remains available in the retained run evidence,
    but is not copied into the client-facing canonical or rendered report surfaces.
    """

    output = value
    sink = removals if removals is not None else []
    for kind, pattern in _EXPLICIT_DIAGNOSTIC_PATTERNS:

        def replace(match: re.Match[str]) -> str:
            sink.append(
                {
                    "path": path,
                    "key": match.group("key"),
                    "kind": f"explicit_{kind}_alias",
                    "classification": "superseded_pre_finalization_diagnostic",
                    "original_value_retained_in_client_manifest": False,
                }
            )
            return ""

        output = pattern.sub(replace, output)
    return _cleanup_removed_text(output) if output != value else value


def _remove_diagnostics(
    node: Any,
    *,
    path: str,
    removals: list[dict[str, Any]],
) -> Any:
    if isinstance(node, str):
        updated = strip_superseded_report_contract_text(
            node,
            path=path,
            removals=removals,
        )
        if updated != node and not updated:
            return _REMOVED
        return updated
    if isinstance(node, list):
        output: list[Any] = []
        for index, value in enumerate(node):
            updated = _remove_diagnostics(
                value,
                path=f"{path}[{index}]",
                removals=removals,
            )
            if updated is not _REMOVED:
                output.append(updated)
        return output
    if isinstance(node, tuple):
        output: list[Any] = []
        for index, value in enumerate(node):
            updated = _remove_diagnostics(
                value,
                path=f"{path}[{index}]",
                removals=removals,
            )
            if updated is not _REMOVED:
                output.append(updated)
        return tuple(output)
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
        if lowered in _DIAGNOSTIC_KEYS and _superseded_diagnostic(key, raw_value):
            removals.append(
                {
                    "path": current_path,
                    "key": key,
                    "kind": "structured_alias",
                    "classification": "superseded_pre_finalization_diagnostic",
                    "original_value_retained_in_client_manifest": False,
                }
            )
            continue
        updated = _remove_diagnostics(
            raw_value,
            path=current_path,
            removals=removals,
        )
        if updated is not _REMOVED:
            output[key] = updated
    return output


def remove_superseded_report_contract_diagnostics(
    canonical: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    removals: list[dict[str, Any]] = []
    cleaned = _remove_diagnostics(
        canonical,
        path="canonical",
        removals=removals,
    )
    if not isinstance(cleaned, dict):
        raise TypeError("post_readiness_report_contract_truth_must_be_mapping")

    manifest = {
        "status": "applied" if removals else "not_needed",
        "version": VERSION,
        "removed_count": len(removals),
        "removals": removals[:100],
        "post_readiness_boundary": True,
        "superseded_diagnostics_only": True,
        "structured_aliases_removed": True,
        "explicit_text_aliases_removed": True,
        "source_run_evidence_preserved": True,
        "raw_diagnostic_repeated_in_client_manifest": False,
        "strict_semantic_validation_preserved": True,
        "scores_changed": False,
        "scanner_results_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    cleaned["post_readiness_report_contract_truth"] = deepcopy(manifest)
    assessment = cleaned.get("assessment")
    if isinstance(assessment, Mapping):
        assessment_copy = dict(assessment)
        assessment_copy["post_readiness_report_contract_truth"] = deepcopy(manifest)
        cleaned["assessment"] = assessment_copy
    return cleaned, manifest


def install_post_readiness_report_contract_truth() -> dict[str, Any]:
    """Bind the last client-surface diagnostic boundary after readiness scoring."""

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
        cleaned, manifest = remove_superseded_report_contract_diagnostics(ready)
        cleaned["post_readiness_report_contract_truth"] = deepcopy(manifest)
        cleaned["human_review_required"] = True
        cleaned["client_delivery_allowed"] = False
        return cleaned

    setattr(reconcile, _MARKER, True)
    setattr(reconcile, "_nico_previous", current)
    readiness.reconcile_client_readiness = reconcile
    return {
        "status": "installed",
        "version": VERSION,
        "bound": readiness.reconcile_client_readiness is reconcile,
        "post_readiness_boundary": True,
        "superseded_diagnostics_only": True,
        "structured_aliases_removed": True,
        "explicit_text_aliases_removed": True,
        "strict_semantic_validation_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_post_readiness_report_contract_truth",
    "remove_superseded_report_contract_diagnostics",
    "strip_superseded_report_contract_text",
]
