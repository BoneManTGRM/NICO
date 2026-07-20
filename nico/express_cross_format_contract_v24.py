from __future__ import annotations

import hashlib
import json
import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_cross_format_contract.v24"
_PATCH_MARKER = "_nico_express_cross_format_contract_v24"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _canonical_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"))
        status = _text(section.get("status")).casefold() or "unknown"
        supplemental = section_id.casefold() == "scanner_worker_evidence" or status == "supplemental"
        score = None if supplemental else section.get("presented_score", section.get("score"))
        records.append(
            {
                "section_id": section_id,
                "label": _text(section.get("label") or section.get("title") or section_id),
                "status": "supplemental" if supplemental else status,
                "score": score,
                "confidence": _text(section.get("confidence") or "unknown").casefold(),
                "directly_scored": not supplemental,
            }
        )
    return records


def _fingerprint(result: dict[str, Any], records: list[dict[str, Any]]) -> str:
    payload = {
        "repository": _text(result.get("repository")),
        "commit_sha": _text(result.get("commit_sha") or result.get("snapshot_sha") or result.get("assessed_commit_sha")),
        "records": records,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains_status(markdown: str, label: str, status: str) -> bool:
    if not markdown or not label:
        return False
    if status == "supplemental":
        pattern = rf"###\s+{re.escape(label)}\s+—\s+SUPPLEMENTAL\s+\(NOT SCORED\)"
    else:
        pattern = rf"###\s+{re.escape(label)}\s+—\s+{re.escape(status.upper())}\b"
    return bool(re.search(pattern, markdown, re.I))


def build_cross_format_contract(result: dict[str, Any]) -> dict[str, Any]:
    records = _canonical_records(result)
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    markdown = str(reports.get("markdown") or "")
    html = str(reports.get("html") or "")

    markdown_missing = [
        item["section_id"]
        for item in records
        if markdown and not _contains_status(markdown, item["label"], item["status"])
    ]
    html_missing = [
        item["section_id"]
        for item in records
        if html and item["label"].casefold() not in html.casefold()
    ]
    scanner = next((item for item in records if item["section_id"].casefold() == "scanner_worker_evidence"), None)
    scanner_valid = scanner is None or (
        scanner["status"] == "supplemental"
        and scanner["score"] is None
        and scanner["directly_scored"] is False
    )

    contract = {
        "status": "complete" if not markdown_missing and not html_missing and scanner_valid else "degraded",
        "version": VERSION,
        "canonical_records": records,
        "record_count": len(records),
        "truth_fingerprint": _fingerprint(result, records),
        "markdown_present": bool(markdown),
        "html_present": bool(html),
        "markdown_status_mismatches": markdown_missing,
        "html_section_mismatches": html_missing,
        "scanner_supplemental_not_scored": scanner_valid,
        "pdf_uses_same_result_object": True,
        "json_contract_embedded": True,
        "human_review_required": True,
    }
    result["express_cross_format_contract"] = contract
    return contract


def install_express_cross_format_contract_v24() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        build_cross_format_contract(result)
        pdf, error = current(result)
        build_cross_format_contract(result)
        return pdf, error

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "production_renderer_bound": True,
        "deterministic_truth_fingerprint": True,
        "scanner_supplemental_contract": True,
    }


__all__ = ["VERSION", "build_cross_format_contract", "install_express_cross_format_contract_v24"]
