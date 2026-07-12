from __future__ import annotations

from typing import Any, Callable

import nico.assessment_score_integrity as score_integrity
import nico.exact_snapshot_secret_history as secret_history
import nico.mid_assessment_handlers as mid_handlers
import nico.snapshot_assessment_handlers as snapshot_handlers


BRIDGE_VERSION = "nico-static-triage-evidence-bridge-v1"
STATIC_SCANNERS = {"bandit", "semgrep"}
SAFE_TRIAGE_FIELDS = (
    "execution_status",
    "execution_completed",
    "finding_count",
    "material_finding_count",
    "review_finding_count",
    "excluded_test_finding_count",
    "severity_counts",
    "confidence_counts",
    "triage_version",
)

_DELEGATE_HANDLER: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _raw_static_results(outputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scanner_step = _dict(outputs.get("scanner_worker"))
    scan = _dict(scanner_step.get("scan"))
    results: dict[str, dict[str, Any]] = {}
    for item in _list(scan.get("scanner_results")):
        if not isinstance(item, dict):
            continue
        scanner = str(item.get("scanner") or "").lower()
        if scanner in STATIC_SCANNERS:
            results[scanner] = item
    return results


def _merge_safe_triage_fields(
    sanitized_results: list[Any],
    raw_results: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in sanitized_results:
        if not isinstance(item, dict):
            continue
        output = dict(item)
        scanner = str(output.get("scanner") or "").lower()
        raw = raw_results.get(scanner)
        if raw:
            for key in SAFE_TRIAGE_FIELDS:
                if key in raw:
                    value = raw.get(key)
                    if isinstance(value, dict):
                        output[key] = {str(name): count for name, count in value.items()}
                    elif isinstance(value, (str, int, float, bool)) or value is None:
                        output[key] = value
        merged.append(output)
    return merged


def preserve_static_triage_attachment(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    delegate = _DELEGATE_HANDLER
    if delegate is None:
        raise RuntimeError("Static triage evidence bridge was not installed before attachment handling.")

    result = delegate(context, outputs)
    if not isinstance(result, dict) or result.get("status") != "complete":
        return result

    evidence = _dict(result.get("scanner_evidence") or result.get("evidence"))
    sanitized_results = _list(evidence.get("scanner_results"))
    raw_results = _raw_static_results(outputs)
    if not raw_results:
        return result

    bridged = dict(evidence)
    bridged["scanner_results"] = _merge_safe_triage_fields(sanitized_results, raw_results)
    bridged["static_triage_evidence_bridge_version"] = BRIDGE_VERSION
    bridged["static_triage_evidence_fields"] = list(SAFE_TRIAGE_FIELDS)

    output = dict(result)
    output["scanner_evidence"] = bridged
    output["evidence"] = bridged
    return output


def _patch_rebinding_sources() -> None:
    """Keep later idempotent installer calls from bypassing the final bridge."""

    score_integrity.calibrated_attachment_handler = preserve_static_triage_attachment
    if secret_history._ATTACHMENT_DELEGATE is not None:
        secret_history.history_attachment_handler = preserve_static_triage_attachment


def install_static_triage_evidence_bridge() -> dict[str, Any]:
    global _DELEGATE_HANDLER

    installed = bool(getattr(snapshot_handlers, "_nico_static_triage_evidence_bridge_installed", False))
    if not installed:
        _DELEGATE_HANDLER = snapshot_handlers._snapshot_evidence_attachment_handler

    _patch_rebinding_sources()
    snapshot_handlers._snapshot_evidence_attachment_handler = preserve_static_triage_attachment
    mid_handlers._snapshot_evidence_attachment_handler = preserve_static_triage_attachment
    snapshot_handlers._nico_static_triage_evidence_bridge_installed = True

    return {
        "status": "already_installed" if installed else "installed",
        "version": BRIDGE_VERSION,
        "scanners": sorted(STATIC_SCANNERS),
        "preserved_fields": list(SAFE_TRIAGE_FIELDS),
        "privacy_rule": "Only structured counts, execution state, severity/confidence aggregates, and triage version cross the evidence boundary; raw findings and source snippets remain excluded.",
        "rebind_rule": "Later score-integrity or secret-history installer calls retain the final evidence bridge instead of restoring an inner handler.",
    }


__all__ = [
    "BRIDGE_VERSION",
    "SAFE_TRIAGE_FIELDS",
    "install_static_triage_evidence_bridge",
    "preserve_static_triage_attachment",
]
