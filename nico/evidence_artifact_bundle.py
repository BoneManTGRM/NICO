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
    complexity_summary = result.get("complexity_engine_summary") if isinstance(result.get("complexity_engine_summary"), dict) else {}
    bandit = result.get("bandit_triage") if isinstance(result.get("bandit_triage"), dict) else {}
    bandit_summary = result.get("bandit_triage_summary") if isinstance(result.get("bandit_triage_summary"), dict) else {}
    history = result.get("secret_history_scan") if isinstance(result.get("secret_history_scan"), dict) else {}
    return {
        "scanner_worker_artifact": _safe_copy(worker),
        "complexity_engine": _safe_copy(complexity),
        "complexity_engine_summary": _safe_copy(complexity_summary),
        "bandit_triage": _safe_copy(bandit),
        "bandit_triage_summary": _safe_copy(bandit_summary),
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


def _verification_state(evidence_count: int, finding_count: int, unavailable_count: int) -> str:
    if unavailable_count and not evidence_count:
        return "unavailable"
    if finding_count:
        return "findings_present"
    if unavailable_count and evidence_count:
        return "partial"
    if evidence_count:
        return "verified"
    return "not_attached"


def _section_ledger_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        evidence = section.get("evidence") if isinstance(section.get("evidence"), list) else []
        findings = section.get("findings") if isinstance(section.get("findings"), list) else []
        unavailable = section.get("unavailable") if isinstance(section.get("unavailable"), list) else []
        row = {
            "entry_type": "section",
            "scope": section.get("label") or section.get("id") or "section",
            "section_id": section.get("id"),
            "score": section.get("score"),
            "status": section.get("status"),
            "evidence_count": len(evidence),
            "finding_count": len(findings),
            "unavailable_count": len(unavailable),
            "verification_state": _verification_state(len(evidence), len(findings), len(unavailable)),
            "evidence_hash": _sha256_bytes(_json_bytes(evidence)),
            "findings_hash": _sha256_bytes(_json_bytes(findings)),
            "unavailable_hash": _sha256_bytes(_json_bytes(unavailable)),
        }
        row["entry_hash"] = _sha256_bytes(_json_bytes(row))
        rows.append(row)
    return rows


def _tool_ledger_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    worker = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    tools = worker.get("tools") if isinstance(worker.get("tools"), dict) else {}
    for name, payload in sorted(tools.items()):
        tool_payload = payload if isinstance(payload, dict) else {"raw": payload}
        finding_count = int(tool_payload.get("finding_count") or tool_payload.get("findings_count") or 0)
        status = str(tool_payload.get("status") or ("completed" if tool_payload.get("completed") else "unavailable"))
        current_run = bool(tool_payload.get("current_run") or tool_payload.get("verified_for_this_report"))
        verified = bool(tool_payload.get("verified_for_this_report") or tool_payload.get("completed") or status in {"completed", "success", "ok", "passed"})
        row = {
            "entry_type": "scanner_tool",
            "scope": str(name),
            "status": status,
            "current_run": current_run,
            "verified_for_this_report": verified,
            "finding_count": finding_count,
            "verification_state": "findings_present" if finding_count else ("verified" if verified else "unavailable"),
            "payload_hash": _sha256_bytes(_json_bytes(tool_payload)),
        }
        row["entry_hash"] = _sha256_bytes(_json_bytes(row))
        rows.append(row)

    for key in ("complexity_engine_summary", "bandit_triage_summary", "secret_history_scan"):
        payload = result.get(key) if isinstance(result.get(key), dict) else {}
        if not payload:
            continue
        verified = bool(payload.get("verified_for_this_report") or payload.get("full_history_verified") or payload.get("history_aware") or payload.get("status") == "completed")
        row = {
            "entry_type": "artifact_summary",
            "scope": key,
            "status": payload.get("status") or "attached",
            "current_run": bool(payload.get("current_run") or verified),
            "verified_for_this_report": verified,
            "finding_count": int(payload.get("finding_count") or payload.get("findings_count") or payload.get("total_findings") or 0),
            "verification_state": "verified" if verified else "partial",
            "payload_hash": _sha256_bytes(_json_bytes(payload)),
        }
        row["entry_hash"] = _sha256_bytes(_json_bytes(row))
        rows.append(row)
    return rows


def build_hardened_evidence_ledger(result: dict[str, Any]) -> dict[str, Any]:
    entries = _section_ledger_entries(result) + _tool_ledger_entries(result)
    unavailable_entries = [item for item in entries if item.get("verification_state") == "unavailable"]
    partial_entries = [item for item in entries if item.get("verification_state") == "partial"]
    finding_entries = [item for item in entries if item.get("verification_state") == "findings_present"]
    verified_entries = [item for item in entries if item.get("verification_state") == "verified"]
    ledger = {
        "artifact_schema": "nico.evidence_ledger.v1",
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "entry_count": len(entries),
        "verified_entry_count": len(verified_entries),
        "partial_entry_count": len(partial_entries),
        "unavailable_entry_count": len(unavailable_entries),
        "finding_entry_count": len(finding_entries),
        "human_review_required": bool(result.get("human_review_required", True) or unavailable_entries or partial_entries or finding_entries),
        "entries": entries,
        "guardrail": "Evidence rows are hash-addressed and classified as verified, partial, unavailable, findings_present, or not_attached. Missing evidence remains explicit and does not become clean proof.",
    }
    ledger["ledger_hash"] = _sha256_bytes(_json_bytes({**ledger, "ledger_hash": ""}))
    return ledger


def build_evidence_artifact_bundle(result: dict[str, Any]) -> dict[str, Any]:
    """Build a defensible artifact manifest for a hosted NICO assessment.

    The bundle is JSON-native so it can be returned through the hosted API without
    needing filesystem access. It records hashes for rendered artifacts and embeds a
    raw evidence JSON object for auditability.
    """
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    raw_evidence = _raw_evidence_json(result)
    raw_evidence_sha = _sha256_bytes(_json_bytes(raw_evidence))
    scanner_outputs = _scanner_outputs(result)
    unavailable_inventory = _collect_unavailable(result)
    evidence_ledger = build_hardened_evidence_ledger(result)
    report_digests = _report_digests(reports)
    bundle = {
        "artifact_schema": "nico.evidence_bundle.v1",
        "created_at": _now_iso(),
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "human_review_required": bool(result.get("human_review_required", True)),
        "artifacts": {
            "markdown": {"filename": "report.md", **report_digests["markdown"]},
            "html": {"filename": "report.html", **report_digests["html"]},
            "pdf": {"filename": reports.get("pdf_filename") or "report.pdf", **report_digests["pdf"]},
            "raw_evidence_json": {"filename": "raw-evidence.json", "available": True, "sha256": raw_evidence_sha},
            "scanner_outputs_json": {"filename": "scanner-outputs.json", "available": bool(scanner_outputs), "sha256": _sha256_bytes(_json_bytes(scanner_outputs))},
            "unavailable_inventory_json": {"filename": "unavailable-inventory.json", "available": True, "sha256": _sha256_bytes(_json_bytes(unavailable_inventory))},
            "evidence_ledger_json": {"filename": "evidence-ledger.json", "available": True, "sha256": _sha256_bytes(_json_bytes(evidence_ledger))},
        },
        "raw_evidence_json": raw_evidence,
        "scanner_outputs": scanner_outputs,
        "ci_references": _collect_ci_references(result),
        "unavailable_inventory": unavailable_inventory,
        "evidence_ledger": evidence_ledger,
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
    output["evidence_ledger"] = bundle["evidence_ledger"]
    reports = output.setdefault("reports", {})
    reports["evidence_bundle_json"] = json.dumps(bundle, indent=2, sort_keys=True, default=str)
    reports["evidence_bundle_filename"] = f"nico-evidence-bundle-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    reports["evidence_ledger_json"] = json.dumps(bundle["evidence_ledger"], indent=2, sort_keys=True, default=str)
    reports["evidence_ledger_filename"] = f"nico-evidence-ledger-{str(output.get('repository') or 'assessment').replace('/', '-')}.json"
    return output
