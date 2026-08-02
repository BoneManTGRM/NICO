from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records

VERSION = "nico.comprehensive_scanner_stage_retention.v1"
_MARKER = "__nico_comprehensive_scanner_stage_retention_v1__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def wrap_scanner_suite_provider(provider):
    if getattr(provider, _MARKER, False):
        return provider

    @wraps(provider)
    def wrapped(context: dict[str, Any]) -> dict[str, Any]:
        result = provider(context)
        if not isinstance(result, dict):
            return result
        if _text(result.get("status")).casefold() != "complete":
            return result

        from nico import comprehensive_native_providers as native

        scan = native._scan(context)
        records = compact_scanner_records(
            scan if isinstance(scan, Mapping) else {},
            commit_sha=_text(context.get("commit_sha")).casefold(),
        )
        output = dict(result)
        output["scanner_execution_records"] = records
        output["scanner_artifact_retention"] = {
            "version": VERSION,
            "scan_id": _text(scan.get("scan_id")) if isinstance(scan, Mapping) else "",
            "record_count": len(records),
            "verified_record_count": sum(
                item.get("verified_complete") is True for item in records
            ),
            "compact_records_only": True,
            "raw_findings_embedded": False,
            "raw_output_previews_embedded": False,
            "raw_artifact_store_reference_retained": True,
            "available_to_final_report_without_scanner_store_read": bool(records),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        evidence = (
            deepcopy(dict(output.get("evidence")))
            if isinstance(output.get("evidence"), Mapping)
            else {}
        )
        evidence["scanner_artifact_retention"] = deepcopy(
            output["scanner_artifact_retention"]
        )
        output["evidence"] = evidence
        output["human_review_required"] = True
        output["client_delivery_allowed"] = False
        return output

    setattr(wrapped, _MARKER, True)
    setattr(wrapped, "_nico_previous", provider)
    return wrapped


def install_scanner_stage_retention(app: FastAPI) -> dict[str, Any]:
    raw = getattr(app.state, PROVIDER_STATE_KEY, None)
    if not isinstance(raw, dict):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "comprehensive_provider_registry_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    current = raw.get("scanner_suite")
    if not callable(current):
        return {
            "status": "blocked",
            "version": VERSION,
            "bound": False,
            "reason": "scanner_suite_provider_unavailable",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    wrapped = wrap_scanner_suite_provider(current)
    raw["scanner_suite"] = wrapped
    setattr(app.state, PROVIDER_STATE_KEY, raw)
    bound = raw.get("scanner_suite") is wrapped
    return {
        "status": "installed" if wrapped is not current else "already_installed",
        "version": VERSION,
        "bound": bound,
        "compact_exact_sha_records_retained": True,
        "raw_scanner_outputs_excluded_from_run_record": True,
        "final_report_scanner_store_read_required": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_scanner_stage_retention",
    "wrap_scanner_suite_provider",
]
