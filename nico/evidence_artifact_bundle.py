from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_copy(value: Any) -> Any:
    return deepcopy(value)


def _pdf_digest(pdf_base64: str | None) -> dict[str, Any] | None:
    if not pdf_base64:
        return None
    try:
        raw = base64.b64decode(pdf_base64.encode("ascii"), validate=True)
    except Exception:
        return {"available": False, "error": "PDF base64 could not be decoded for hashing."}
    return {"available": True, "bytes": len(raw), "sha256": _sha256_bytes(raw)}


def _collect_unavailable(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for item in section.get("unavailable", []) or []:
            rows.append({"scope": section.get("label") or section.get("id") or "section", "note": str(item)})
    for item in result.get("unavailable_data_notes", []) or []:
        rows.append({"scope": "global", "note": str(item)})
    return rows


def _collect_ci_references(result: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        label = str(section.get("label") or "")
        if "CI" not in label and "CD" not in label:
            continue
        for item in section.get("evidence", []) or []:
            text = str(item)
            if "workflow" in text.lower() or "actions" in text.lower() or "runs" in text.lower():
                refs.append(text)
    return refs[:50]


def _scanner_outputs(result: dict[str, Any]) -> dict[str, Any]:
    worker = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    complexity = result.get("complexity_engine") if isinstance(result.get("complexity_engine"), dict) else {}
    bandit = result.get("bandit_triage") if isinstance(result.get("bandit_triage"), dict) else {}
    history = result.get("secret_history_scan") if isinstance(result.get("secret_history_scan"), dict) else {}
    return {
        "scanner_worker_artifact": _safe_copy(worker),
        "complexity_engine": _safe_copy(complexity),
        "bandit_triage": _safe_copy(bandit),
        "secret_history_scan": _safe_copy(history),
    }


def _report_digests(reports: dict[str, Any]) -> dict[str, Any]:
    markdown = reports.get("markdown") if isinstance(reports.get("markdown"), str) else ""
    html = reports.get("html") if isinstance(reports.get("html"), str) else ""
    pdf_info = _pdf_digest(reports.get("pdf_base64") if isinstance(reports.get("pdf_base64"), str) else None)
    return {
        "markdown": {"available": bool(markdown), "bytes": len(markdown.encode("utf-8")), "sha256": _sha256_text(markdown) if markdown else ""},
        "html": {"available": bool(html), "bytes": len(html.encode("utf-8")), "sha256": _sha256_text(html) if html else ""},
        "pdf": pdf_info or {"available": False},
    }


def _raw_evidence_json(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "assessment_mode": result.get("assessment_mode"),
        "timeframe_days": result.get("timeframe_days"),
        "repository_metadata": _safe_copy(result.get("repository_metadata") or {}),
        "maturity_signal": _safe_copy(result.get("maturity_signal") or {}),
        "maturity_semaphore": _safe_copy(result.get("maturity_semaphore") or {}),
        "sections": _safe_copy(result.get("sections") or []),
        "findings": _safe_copy(result.get("findings") or []),
        "repairs": _safe_copy(result.get("repairs") or []),
        "quick_wins": _safe_copy(result.get("quick_wins") or []),
        "medium_term_plan": _safe_copy(result.get("medium_term_plan") or []),
        "resourcing_recommendation": _safe_copy(result.get("resourcing_recommendation") or []),
        "risk_register": _safe_copy(result.get("risk_register") or []),
        "verification_checklist": _safe_copy(result.get("verification_checklist") or []),
        "unavailable_data_notes": _safe_copy(result.get("unavailable_data_notes") or []),
        "scanner_outputs": _scanner_outputs(result),
        "human_review_required": bool(result.get("human_review_required", True)),
        "safety_boundary": result.get("safety_boundary"),
    }


def build_evidence_artifact_bundle(result: dict[str, Any]) -> dict[str, Any]:
    """Build a defensible artifact manifest for a hosted NICO assessment.

    The bundle is JSON-native so it can be returned through the hosted API without
    needing filesystem access. It records hashes for rendered artifacts and embeds a
    raw evidence JSON object for auditability.
    """
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    raw_evidence = _raw_evidence_json(result)
    raw_evidence_sha = _sha256_bytes(_json_bytes(raw_evidence))
    bundle = {
        "artifact_schema": "nico.evidence_bundle.v1",
        "created_at": _now_iso(),
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "human_review_required": bool(result.get("human_review_required", True)),
        "artifacts": {
            "markdown": {"filename": "report.md", **_report_digests(reports)["markdown"]},
            "html": {"filename": "report.html", **_report_digests(reports)["html"]},
            "pdf": {"filename": reports.get("pdf_filename") or "report.pdf", **_report_digests(reports)["pdf"]},
            "raw_evidence_json": {"filename": "raw-evidence.json", "available": True, "sha256": raw_evidence_sha},
            "scanner_outputs_json": {"filename": "scanner-outputs.json", "available": bool(_scanner_outputs(result)), "sha256": _sha256_bytes(_json_bytes(_scanner_outputs(result)))},
            "unavailable_inventory_json": {"filename": "unavailable-inventory.json", "available": True, "sha256": _sha256_bytes(_json_bytes(_collect_unavailable(result)))},
        },
        "raw_evidence_json": raw_evidence,
        "scanner_outputs": _scanner_outputs(result),
        "ci_references": _collect_ci_references(result),
        "unavailable_inventory": _collect_unavailable(result),
        "hash_algorithm": "sha256",
        "bundle_hash": "",
    }
    unsigned = dict(bundle)
    unsigned["bundle_hash"] = ""
    bundle["bundle_hash"] = _sha256_bytes(_json_bytes(unsigned))
    return bundle


def attach_evidence_artifact_bundle(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    bundle = build_evidence_artifact_bundle(output)
    output["evidence_artifact_bundle"] = bundle
    reports = output.setdefault("reports", {})
    reports["evidence_bundle_json"] = json.dumps(bundle, indent=2, sort_keys=True, default=str)
    reports["evidence_bundle_filename"] = f"nico-evidence-bundle-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    return output
