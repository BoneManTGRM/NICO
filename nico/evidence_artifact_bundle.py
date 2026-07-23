from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable


MAX_EMBEDDED_VALUE_BYTES = 96 * 1024
MAX_RAW_EVIDENCE_BYTES = 256 * 1024
MAX_SCANNER_OUTPUTS_BYTES = 384 * 1024
MAX_EXPORT_BYTES = 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_chunks(value: Any) -> Iterable[bytes]:
    encoder = json.JSONEncoder(sort_keys=True, separators=(",", ":"), default=str)
    for chunk in encoder.iterencode(value):
        yield chunk.encode("utf-8")


def _json_digest_size(value: Any, *, capture_limit: int = 0) -> tuple[int, str, bytes | None]:
    digest = hashlib.sha256()
    total = 0
    captured = bytearray()
    capturing = capture_limit > 0
    for chunk in _json_chunks(value):
        total += len(chunk)
        digest.update(chunk)
        if capturing:
            if len(captured) + len(chunk) <= capture_limit:
                captured.extend(chunk)
            else:
                capturing = False
                captured.clear()
    return total, digest.hexdigest(), bytes(captured) if capturing else None


def _json_bytes(value: Any) -> bytes:
    _size, _digest, captured = _json_digest_size(value, capture_limit=MAX_EXPORT_BYTES * 8)
    if captured is None:
        raise ValueError("JSON payload exceeds the safe in-memory serialization boundary")
    return captured


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_copy(value: Any) -> Any:
    return deepcopy(value)


def _structural_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        summary: dict[str, Any] = {
            "type": "object",
            "key_count": len(value),
            "keys": sorted(str(key) for key in value.keys())[:40],
        }
        for key in (
            "status",
            "state",
            "phase",
            "completed",
            "current_run",
            "verified_for_this_report",
            "finding_count",
            "findings_count",
            "total_findings",
            "files_analyzed",
            "tool_count",
        ):
            item = value.get(key)
            if isinstance(item, (str, int, float, bool)) or item is None:
                if key in value:
                    summary[key] = item
        tools = value.get("tools")
        if isinstance(tools, dict):
            tool_rows: dict[str, Any] = {}
            for name, payload in sorted(tools.items(), key=lambda pair: str(pair[0]))[:80]:
                item = payload if isinstance(payload, dict) else {"value_type": type(payload).__name__}
                size, sha256, _captured = _json_digest_size(payload)
                tool_rows[str(name)] = {
                    "status": item.get("status") or ("completed" if item.get("completed") else "unknown"),
                    "finding_count": int(item.get("finding_count") or item.get("findings_count") or 0),
                    "bytes": size,
                    "sha256": sha256,
                }
            summary["tools"] = tool_rows
            summary["tool_count"] = len(tools)
        return summary
    if isinstance(value, list):
        return {"type": "array", "item_count": len(value)}
    return {"type": type(value).__name__, "value": value if isinstance(value, (str, int, float, bool)) else str(value)}


def _bounded_json_value(value: Any, label: str, *, limit: int = MAX_EMBEDDED_VALUE_BYTES) -> Any:
    size, sha256, captured = _json_digest_size(value, capture_limit=limit)
    if captured is not None:
        return json.loads(captured.decode("utf-8"))
    return {
        "bounded_payload": True,
        "embedded": False,
        "label": label,
        "reason": "payload_exceeds_embedded_limit",
        "original_bytes": size,
        "sha256": sha256,
        "summary": _structural_summary(value),
    }


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
    return rows[:2000]


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
                refs.append(text[:2000])
    return refs[:50]


def _scanner_outputs(result: dict[str, Any]) -> dict[str, Any]:
    values = {
        "scanner_worker_artifact": result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {},
        "complexity_engine": result.get("complexity_engine") if isinstance(result.get("complexity_engine"), dict) else {},
        "complexity_engine_summary": result.get("complexity_engine_summary") if isinstance(result.get("complexity_engine_summary"), dict) else {},
        "bandit_triage": result.get("bandit_triage") if isinstance(result.get("bandit_triage"), dict) else {},
        "bandit_triage_summary": result.get("bandit_triage_summary") if isinstance(result.get("bandit_triage_summary"), dict) else {},
        "secret_history_scan": result.get("secret_history_scan") if isinstance(result.get("secret_history_scan"), dict) else {},
    }
    compact = {
        key: _bounded_json_value(value, key)
        for key, value in values.items()
    }
    return _bounded_json_value(compact, "scanner_outputs", limit=MAX_SCANNER_OUTPUTS_BYTES)


def _report_digests(reports: dict[str, Any]) -> dict[str, Any]:
    markdown = reports.get("markdown") if isinstance(reports.get("markdown"), str) else ""
    html = reports.get("html") if isinstance(reports.get("html"), str) else ""
    pdf_info = _pdf_digest(reports.get("pdf_base64") if isinstance(reports.get("pdf_base64"), str) else None)
    return {
        "markdown": {"available": bool(markdown), "bytes": len(markdown.encode("utf-8")), "sha256": _sha256_text(markdown) if markdown else ""},
        "html": {"available": bool(html), "bytes": len(html.encode("utf-8")), "sha256": _sha256_text(html) if html else ""},
        "pdf": pdf_info or {"available": False},
    }


def _raw_evidence_json(result: dict[str, Any], scanner_outputs: dict[str, Any]) -> dict[str, Any]:
    raw = {
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "assessment_mode": result.get("assessment_mode"),
        "timeframe_days": result.get("timeframe_days"),
        "repository_metadata": _bounded_json_value(result.get("repository_metadata") or {}, "repository_metadata"),
        "maturity_signal": _bounded_json_value(result.get("maturity_signal") or {}, "maturity_signal"),
        "maturity_semaphore": _bounded_json_value(result.get("maturity_semaphore") or {}, "maturity_semaphore"),
        "sections": _bounded_json_value(result.get("sections") or [], "sections"),
        "findings": _bounded_json_value(result.get("findings") or [], "findings"),
        "repairs": _bounded_json_value(result.get("repairs") or [], "repairs"),
        "quick_wins": _bounded_json_value(result.get("quick_wins") or [], "quick_wins"),
        "medium_term_plan": _bounded_json_value(result.get("medium_term_plan") or [], "medium_term_plan"),
        "resourcing_recommendation": _bounded_json_value(result.get("resourcing_recommendation") or [], "resourcing_recommendation"),
        "risk_register": _bounded_json_value(result.get("risk_register") or [], "risk_register"),
        "verification_checklist": _bounded_json_value(result.get("verification_checklist") or [], "verification_checklist"),
        "unavailable_data_notes": _bounded_json_value(result.get("unavailable_data_notes") or [], "unavailable_data_notes"),
        "scanner_outputs": scanner_outputs,
        "human_review_required": bool(result.get("human_review_required", True)),
        "safety_boundary": result.get("safety_boundary"),
    }
    return _bounded_json_value(raw, "raw_evidence_json", limit=MAX_RAW_EVIDENCE_BYTES)


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
        evidence_bytes, evidence_hash, _ = _json_digest_size(evidence)
        findings_bytes, findings_hash, _ = _json_digest_size(findings)
        unavailable_bytes, unavailable_hash, _ = _json_digest_size(unavailable)
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
            "evidence_bytes": evidence_bytes,
            "evidence_hash": evidence_hash,
            "findings_bytes": findings_bytes,
            "findings_hash": findings_hash,
            "unavailable_bytes": unavailable_bytes,
            "unavailable_hash": unavailable_hash,
        }
        _bytes, row_hash, _ = _json_digest_size(row)
        row["entry_hash"] = row_hash
        rows.append(row)
    return rows


def _tool_ledger_entries(result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    worker = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else {}
    tools = worker.get("tools") if isinstance(worker.get("tools"), dict) else {}
    for name, payload in sorted(tools.items()):
        tool_payload = payload if isinstance(payload, dict) else {"raw_type": type(payload).__name__}
        finding_count = int(tool_payload.get("finding_count") or tool_payload.get("findings_count") or 0)
        status = str(tool_payload.get("status") or ("completed" if tool_payload.get("completed") else "unavailable"))
        current_run = bool(tool_payload.get("current_run") or tool_payload.get("verified_for_this_report"))
        verified = bool(tool_payload.get("verified_for_this_report") or tool_payload.get("completed") or status in {"completed", "success", "ok", "passed"})
        payload_bytes, payload_hash, _ = _json_digest_size(payload)
        row = {
            "entry_type": "scanner_tool",
            "scope": str(name),
            "status": status,
            "current_run": current_run,
            "verified_for_this_report": verified,
            "finding_count": finding_count,
            "verification_state": "findings_present" if finding_count else ("verified" if verified else "unavailable"),
            "payload_bytes": payload_bytes,
            "payload_hash": payload_hash,
        }
        _bytes, row_hash, _ = _json_digest_size(row)
        row["entry_hash"] = row_hash
        rows.append(row)

    for key in ("complexity_engine_summary", "bandit_triage_summary", "secret_history_scan"):
        payload = result.get(key) if isinstance(result.get(key), dict) else {}
        if not payload:
            continue
        verified = bool(payload.get("verified_for_this_report") or payload.get("full_history_verified") or payload.get("history_aware") or payload.get("status") == "completed")
        payload_bytes, payload_hash, _ = _json_digest_size(payload)
        row = {
            "entry_type": "artifact_summary",
            "scope": key,
            "status": payload.get("status") or "attached",
            "current_run": bool(payload.get("current_run") or verified),
            "verified_for_this_report": verified,
            "finding_count": int(payload.get("finding_count") or payload.get("findings_count") or payload.get("total_findings") or 0),
            "verification_state": "verified" if verified else "partial",
            "payload_bytes": payload_bytes,
            "payload_hash": payload_hash,
        }
        _bytes, row_hash, _ = _json_digest_size(row)
        row["entry_hash"] = row_hash
        rows.append(row)
    return rows


def build_hardened_evidence_ledger(result: dict[str, Any]) -> dict[str, Any]:
    entries = _section_ledger_entries(result) + _tool_ledger_entries(result)
    unavailable_entries = [item for item in entries if item.get("verification_state") == "unavailable"]
    partial_entries = [item for item in entries if item.get("verification_state") == "partial"]
    finding_entries = [item for item in entries if item.get("verification_state") == "findings_present"]
    verified_entries = [item for item in entries if item.get("verification_state") == "verified"]
    ledger = {
        "artifact_schema": "nico.evidence_ledger.v2",
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "entry_count": len(entries),
        "verified_entry_count": len(verified_entries),
        "partial_entry_count": len(partial_entries),
        "unavailable_entry_count": len(unavailable_entries),
        "finding_entry_count": len(finding_entries),
        "human_review_required": bool(result.get("human_review_required", True) or unavailable_entries or partial_entries or finding_entries),
        "entries": entries,
        "guardrail": "Evidence rows are hash-addressed and classified as verified, partial, unavailable, findings_present, or not_attached. Oversized raw payloads are represented by byte counts, SHA-256 digests, and explicit bounded-payload summaries; missing evidence never becomes clean proof.",
    }
    _bytes, ledger_hash, _ = _json_digest_size({**ledger, "ledger_hash": ""})
    ledger["ledger_hash"] = ledger_hash
    return ledger


def build_evidence_artifact_bundle(result: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded, defensible artifact manifest for a hosted assessment.

    Report contents are represented by hashes and sizes. Large scanner and raw
    evidence objects are embedded only below explicit byte limits; otherwise NICO
    records their SHA-256 digest, original size, structural summary, and omission
    reason. This keeps the final truth gate deterministic without fabricating or
    silently dropping evidence.
    """

    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    scanner_outputs = _scanner_outputs(result)
    raw_evidence = _raw_evidence_json(result, scanner_outputs)
    raw_evidence_bytes, raw_evidence_sha, _ = _json_digest_size(raw_evidence)
    unavailable_inventory = _collect_unavailable(result)
    evidence_ledger = build_hardened_evidence_ledger(result)
    report_digests = _report_digests(reports)
    bundle = {
        "artifact_schema": "nico.evidence_bundle.v2",
        "created_at": _now_iso(),
        "repository": result.get("repository"),
        "generated_at": result.get("generated_at"),
        "human_review_required": bool(result.get("human_review_required", True)),
        "bundle_limits": {
            "max_embedded_value_bytes": MAX_EMBEDDED_VALUE_BYTES,
            "max_raw_evidence_bytes": MAX_RAW_EVIDENCE_BYTES,
            "max_scanner_outputs_bytes": MAX_SCANNER_OUTPUTS_BYTES,
            "max_export_bytes": MAX_EXPORT_BYTES,
            "oversized_payload_policy": "digest_size_summary_without_raw_embedding",
        },
        "artifacts": {
            "markdown": {"filename": "report.md", **report_digests["markdown"]},
            "html": {"filename": "report.html", **report_digests["html"]},
            "pdf": {"filename": reports.get("pdf_filename") or "report.pdf", **report_digests["pdf"]},
            "raw_evidence_json": {"filename": "raw-evidence.json", "available": True, "bytes": raw_evidence_bytes, "sha256": raw_evidence_sha},
            "scanner_outputs_json": {"filename": "scanner-outputs.json", "available": bool(scanner_outputs), **dict(zip(("bytes", "sha256"), _json_digest_size(scanner_outputs)[:2]))},
            "unavailable_inventory_json": {"filename": "unavailable-inventory.json", "available": True, **dict(zip(("bytes", "sha256"), _json_digest_size(unavailable_inventory)[:2]))},
            "evidence_ledger_json": {"filename": "evidence-ledger.json", "available": True, **dict(zip(("bytes", "sha256"), _json_digest_size(evidence_ledger)[:2]))},
        },
        "raw_evidence_json": raw_evidence,
        "scanner_outputs": scanner_outputs,
        "ci_references": _collect_ci_references(result),
        "unavailable_inventory": unavailable_inventory,
        "evidence_ledger": evidence_ledger,
        "hash_algorithm": "sha256",
        "bundle_hash": "",
    }
    _bytes, bundle_hash, _ = _json_digest_size({**bundle, "bundle_hash": ""})
    bundle["bundle_hash"] = bundle_hash
    return bundle


def attach_evidence_artifact_bundle(result: dict[str, Any]) -> dict[str, Any]:
    # A shallow top-level copy avoids cloning report PDF bytes and raw scanner trees.
    # Nested values remain immutable here; only a copied reports mapping is extended.
    output = dict(result)
    bundle = build_evidence_artifact_bundle(result)
    output["evidence_artifact_bundle"] = bundle
    output["evidence_ledger"] = bundle["evidence_ledger"]
    reports = dict(result.get("reports") or {}) if isinstance(result.get("reports"), dict) else {}
    bundle_bytes, _bundle_hash, captured = _json_digest_size(bundle, capture_limit=MAX_EXPORT_BYTES)
    if captured is not None:
        reports["evidence_bundle_json"] = json.dumps(json.loads(captured.decode("utf-8")), indent=2, sort_keys=True)
        reports["evidence_bundle_export_status"] = "complete"
    else:
        reports["evidence_bundle_json"] = json.dumps(
            {
                "artifact_schema": bundle["artifact_schema"],
                "repository": bundle.get("repository"),
                "bundle_hash": bundle["bundle_hash"],
                "full_export_embedded": False,
                "original_bytes": bundle_bytes,
                "reason": "bundle_exceeds_export_limit",
                "bundle_limits": bundle["bundle_limits"],
                "artifacts": bundle["artifacts"],
                "evidence_ledger": bundle["evidence_ledger"],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        reports["evidence_bundle_export_status"] = "bounded_manifest"
    repository_name = str(output.get("repository") or "assessment").replace("/", "-")
    reports["evidence_bundle_filename"] = f"nico-evidence-bundle-{repository_name}.json"
    reports["evidence_ledger_json"] = json.dumps(bundle["evidence_ledger"], indent=2, sort_keys=True, default=str)
    reports["evidence_ledger_filename"] = f"nico-evidence-ledger-{repository_name}.json"
    output["reports"] = reports
    output["evidence_bundle_runtime"] = {
        "status": "complete",
        "bounded": True,
        "bundle_bytes": bundle_bytes,
        "raw_payloads_embedded_only_within_limits": True,
        "oversized_payloads_hash_addressed": True,
    }
    return output
