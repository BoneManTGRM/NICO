from __future__ import annotations

import io
import re
from collections import Counter
from typing import Any

from pypdf import PdfReader


VERSION = "express_visual_qa_v16"
_PLACEHOLDER_RE = re.compile(r"<[^>]*(?:version|package|minimum|maximum|verified|todo|tbd)[^>]*>", re.I)
_RAW_MARKUP_RE = re.compile(r"```|<script\b|<style\b|\{\s*\"[A-Za-z0-9_]+\"\s*:")


def validate_express_pdf(pdf_bytes: bytes, result: dict[str, Any]) -> dict[str, Any]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    full_text = "\n".join(page_text)
    dossier_ids = re.findall(r"FND-[A-F0-9]{12}", full_text)
    duplicate_ids = sorted(item for item, count in Counter(dossier_ids).items() if count > 1)
    blank_pages = [index + 1 for index, text in enumerate(page_text) if len(text) < 40]
    issues: list[str] = []

    if not 15 <= len(reader.pages) <= 20:
        issues.append(f"Express page count {len(reader.pages)} is outside 15-20.")
    if blank_pages:
        issues.append(f"Blank or near-blank pages detected: {blank_pages}.")
    if _PLACEHOLDER_RE.search(full_text):
        issues.append("Unresolved placeholder token detected.")
    if _RAW_MARKUP_RE.search(full_text):
        issues.append("Raw markup or serialized object text detected.")
    if duplicate_ids:
        issues.append(f"Duplicate finding IDs detected: {duplicate_ids}.")
    if "human review required" not in full_text.lower() and "se requiere revisión humana" not in full_text.lower():
        issues.append("Human-review boundary is missing.")

    score_meta = result.get("express_score_transparency") if isinstance(result.get("express_score_transparency"), dict) else {}
    for record in score_meta.get("records", []):
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "").lower() == "green" and record.get("deductions"):
            issues.append(f"Score/status contradiction for {record.get('section_id') or 'unknown section'}.")

    locale = str(
        result.get("report_language")
        or result.get("language")
        or result.get("locale")
        or "en"
    ).lower().replace("_", "-")
    locale = "es" if locale.startswith("es") else "en"
    required = {
        "en": ["Executive Decision Brief", "Transparent Technical Score", "Finding Dossier"],
        "es": ["Evaluación Express de Salud Técnica NICO", "Expediente del Hallazgo", "Se requiere revisión humana"],
    }[locale]
    for label in required:
        if label not in full_text:
            issues.append(f"Required {locale} report label missing: {label}.")

    return {
        "status": "pass" if not issues else "fail",
        "version": VERSION,
        "locale": locale,
        "page_count": len(reader.pages),
        "blank_pages": blank_pages,
        "dossier_count": len(set(dossier_ids)),
        "duplicate_finding_ids": duplicate_ids,
        "issues": issues,
        "client_delivery_allowed": not issues and not bool(result.get("human_review_required", True)),
        "human_review_required": bool(result.get("human_review_required", True)),
    }


def assert_bilingual_structure(english: dict[str, Any], spanish: dict[str, Any]) -> dict[str, Any]:
    en_records = english.get("express_score_transparency", {}).get("records", [])
    es_records = spanish.get("express_score_transparency", {}).get("records", [])
    en_dossiers = english.get("express_finding_dossier_export", {}).get("dossier_count")
    es_dossiers = spanish.get("express_finding_dossier_export", {}).get("dossier_count")
    issues: list[str] = []
    if len(en_records) != len(es_records):
        issues.append("Score-record count differs between English and Spanish.")
    if en_dossiers != es_dossiers:
        issues.append("Finding-dossier count differs between English and Spanish.")
    return {
        "status": "pass" if not issues else "fail",
        "version": VERSION,
        "score_record_count": len(en_records),
        "dossier_count": en_dossiers,
        "issues": issues,
    }


__all__ = ["VERSION", "assert_bilingual_structure", "validate_express_pdf"]
