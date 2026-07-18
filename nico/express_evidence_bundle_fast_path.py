from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

PATCH_VERSION = "nico.express_evidence_bundle_fast_path.v1"
_PATCH_MARKER = "_nico_express_evidence_bundle_fast_path_v1"
_MAX_LEDGER_ITEMS = 250
_MAX_TEXT_BYTES = 2_000_000


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _report_digest(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else ""
    encoded = text.encode("utf-8")
    return {
        "available": bool(text.strip()),
        "bytes": len(encoded),
        "sha256": _sha256_bytes(encoded) if text else "",
    }


def _pdf_digest(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else ""
    if not text.strip():
        return {"available": False, "bytes": 0, "sha256": "", "structurally_valid": False}
    try:
        raw = base64.b64decode(text, validate=True)
    except Exception:
        return {"available": False, "bytes": 0, "sha256": "", "structurally_valid": False}
    return {
        "available": True,
        "bytes": len(raw),
        "sha256": _sha256_bytes(raw),
        "structurally_valid": raw.startswith(b"%PDF-") and b"%%EOF" in raw[-2048:],
    }


def _count(value: Any) -> int:
    return len(value) if isinstance(value, (list, dict, tuple, set)) else 0


def _bounded_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"available": False, "type": type(value).__name__}
    summary: dict[str, Any] = {"available": bool(value), "keys": sorted(str(key) for key in value.keys())[:100]}
    for key in (
        "status",
        "current_run",
        "verified_for_this_report",
        "finding_count",
        "findings_count",
        "total_findings",
        "completed",
        "full_history_verified",
        "history_aware",
    ):
        if key in value and isinstance(value[key], (str, int, float, bool, type(None))):
            summary[key] = value[key]
    summary["sha256"] = _sha256_bytes(_json_bytes(summary))
    return summary


def _section_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        evidence = section.get("evidence") if isinstance(section.get("evidence"), list) else []
        findings = section.get("findings") if isinstance(section.get("findings"), list) else []
        unavailable = section.get("unavailable") if isinstance(section.get("unavailable"), list) else []
        entry = {
            "entry_type": "section",
            "scope": section.get("label") or section.get("id") or "section",
            "section_id": section.get("id"),
            "score": section.get("score"),
            "status": section.get("status"),
            "evidence_count": len(evidence),
            "finding_count": len(findings),
            "unavailable_count": len(unavailable),
        }
        entry["entry_hash"] = _sha256_bytes(_json_bytes(entry))
        entries.append(entry)
        if len(entries) >= _MAX_LEDGER_ITEMS:
            break
    return entries


def _scanner_entries(result: dict[str, Any], remaining: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    worker = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    tools = worker.get("tools") if isinstance(worker.get("tools"), dict) else {}
    for name, payload in sorted(tools.items(), key=lambda item: str(item[0])):
        summary = _bounded_summary(payload)
        entry = {"entry_type": "scanner_tool", "scope": str(name), **summary}
        entry["entry_hash"] = _sha256_bytes(_json_bytes(entry))
        entries.append(entry)
        if len(entries) >= remaining:
            return entries
    for key in ("complexity_engine_summary", "bandit_triage_summary", "secret_history_scan"):
        payload = result.get(key)
        if not isinstance(payload, dict) or not payload:
            continue
        entry = {"entry_type": "artifact_summary", "scope": key, **_bounded_summary(payload)}
        entry["entry_hash"] = _sha256_bytes(_json_bytes(entry))
        entries.append(entry)
        if len(entries) >= remaining:
            break
    return entries


def build_express_evidence_bundle(result: dict[str, Any]) -> dict[str, Any]:
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    markdown = _report_digest(reports.get("markdown"))
    html = _report_digest(reports.get("html"))
    pdf = _pdf_digest(reports.get("pdf_base64"))
    entries = _section_entries(result)
    entries.extend(_scanner_entries(result, max(0, _MAX_LEDGER_ITEMS - len(entries))))
    ledger = {
        "artifact_schema": "nico.evidence_ledger.v2",
        "repository": result.get("repository"),
        "entry_count": len(entries),
        "entries": entries,
        "truncated": len(entries) >= _MAX_LEDGER_ITEMS,
        "human_review_required": True,
        "guardrail": "Evidence metadata is hash-addressed and bounded. Full scanner payloads remain in the assessment record and are not recursively embedded into the final evidence bundle.",
    }
    ledger["ledger_hash"] = _sha256_bytes(_json_bytes({**ledger, "ledger_hash": ""}))
    raw_summary = {
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "assessment_mode": result.get("assessment_mode") or result.get("assessment_type") or "express",
        "timeframe_days": result.get("timeframe_days"),
        "section_count": _count(result.get("sections")),
        "finding_count": _count(result.get("findings")),
        "repair_count": _count(result.get("repairs")),
        "unavailable_note_count": _count(result.get("unavailable_data_notes")),
        "maturity_signal": deepcopy(result.get("maturity_signal")) if isinstance(result.get("maturity_signal"), dict) else {},
        "human_review_required": True,
    }
    bundle = {
        "artifact_schema": "nico.evidence_bundle.v2",
        "patch_version": PATCH_VERSION,
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "human_review_required": True,
        "bounded": True,
        "artifacts": {
            "markdown": {"filename": "report.md", **markdown},
            "html": {"filename": "report.html", **html},
            "pdf": {"filename": reports.get("pdf_filename") or "report.pdf", **pdf},
            "raw_evidence_summary_json": {"filename": "raw-evidence-summary.json", "available": True},
            "evidence_ledger_json": {"filename": "evidence-ledger.json", "available": True, "sha256": ledger["ledger_hash"]},
        },
        "raw_evidence_summary": raw_summary,
        "scanner_output_summaries": {
            "scanner_worker_artifact": _bounded_summary(result.get("scanner_worker_artifact")),
            "complexity_engine": _bounded_summary(result.get("complexity_engine")),
            "bandit_triage": _bounded_summary(result.get("bandit_triage")),
            "secret_history_scan": _bounded_summary(result.get("secret_history_scan")),
        },
        "evidence_ledger": ledger,
        "hash_algorithm": "sha256",
        "bundle_hash": "",
    }
    bundle["bundle_hash"] = _sha256_bytes(_json_bytes({**bundle, "bundle_hash": ""}))
    return bundle


def attach_express_evidence_bundle(result: dict[str, Any]) -> dict[str, Any]:
    output = dict(result)
    bundle = build_express_evidence_bundle(output)
    output["evidence_artifact_bundle"] = bundle
    output["evidence_ledger"] = bundle["evidence_ledger"]
    reports = dict(output.get("reports")) if isinstance(output.get("reports"), dict) else {}
    bundle_json = json.dumps(bundle, indent=2, sort_keys=True, default=str)
    if len(bundle_json.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ValueError("Express evidence bundle exceeded bounded serialization limit")
    reports["evidence_bundle_json"] = bundle_json
    reports["evidence_bundle_filename"] = f"nico-evidence-bundle-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    reports["evidence_ledger_json"] = json.dumps(bundle["evidence_ledger"], indent=2, sort_keys=True, default=str)
    reports["evidence_ledger_filename"] = f"nico-evidence-ledger-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    output["reports"] = reports
    return output


def install_express_evidence_bundle_fast_path() -> dict[str, Any]:
    from nico import evidence_artifact_bundle
    from nico.api import main as api_main

    current: Callable[[dict[str, Any]], dict[str, Any]] = api_main.attach_evidence_artifact_bundle
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": PATCH_VERSION}

    @wraps(current)
    def bounded_attach(result: dict[str, Any]) -> dict[str, Any]:
        tier = str(result.get("assessment_type") or result.get("service_tier") or result.get("assessment_mode") or "").lower()
        if tier == "express":
            return attach_express_evidence_bundle(result)
        return current(result)

    setattr(bounded_attach, _PATCH_MARKER, True)
    setattr(bounded_attach, "_nico_previous", current)
    api_main.attach_evidence_artifact_bundle = bounded_attach
    evidence_artifact_bundle.attach_evidence_artifact_bundle = bounded_attach
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "express_only": True,
        "bounded_serialization": True,
        "recursive_scanner_embedding_removed": True,
    }


__all__ = [
    "PATCH_VERSION",
    "attach_express_evidence_bundle",
    "build_express_evidence_bundle",
    "install_express_evidence_bundle_fast_path",
]
