from __future__ import annotations

import base64
import hashlib
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_final_report_semantics.v47"
_PATCH_MARKER = "_nico_comprehensive_final_report_semantics_v47"
_CANONICAL_TITLE = "NICO Comprehensive Technical Assessment"
_FINAL_STATUS = "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
_STALE_RE = re.compile(
    r"\bDRAFT\b|DRAFT ONLY|COMPLETE ONLY AS A DRAFT|NOT APPROVED FOR CLIENT DELIVERY",
    re.IGNORECASE,
)

_VALUE_REPLACEMENTS = (
    ("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", _FINAL_STATUS),
    ("DRAFT - HUMAN REVIEW REQUIRED - CLIENT DELIVERY NOT AUTHORIZED", _FINAL_STATUS),
    ("DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED", _FINAL_STATUS),
    ("DRAFT · HUMAN REVIEW REQUIRED", "FINAL REPORT · PENDING HUMAN APPROVAL"),
    ("DRAFT - HUMAN REVIEW REQUIRED", "FINAL REPORT - PENDING HUMAN APPROVAL"),
    ("Draft only", "Pending approval"),
    ("draft only", "pending approval"),
    ("complete only as a draft", "complete as a final report pending human approval"),
    ("The automated assessment is complete only as a draft.", "The final report is complete pending human approval."),
    ("Not approved for client delivery", "Delivery blocked pending human approval"),
    ("not approved for client delivery", "delivery blocked pending human approval"),
    ("CLIENT DELIVERY NOT AUTHORIZED", "CLIENT DELIVERY BLOCKED PENDING HUMAN APPROVAL"),
    ("Client delivery", "Client delivery"),
)

_PDF_REPLACEMENTS = (
    ("DRAFT", "FINAL"),
    ("Draft only", "Pending"),
    ("draft only", "pending"),
    ("Not approved for client delivery", "Delivery blocked pending approval"),
    ("not approved for client delivery", "delivery blocked pending approval"),
    ("The automated assessment is complete only as a draft.", "The final report is complete pending human approval."),
)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clean_string(value: str) -> str:
    output = value
    for previous, replacement in _VALUE_REPLACEMENTS:
        output = output.replace(previous, replacement)
    output = output.replace("-DRAFT.pdf", "-FINAL-PENDING-APPROVAL.pdf")
    output = output.replace("-draft.pdf", "-final-pending-approval.pdf")
    return output


def _recursive_clean(value: Any) -> Any:
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, list):
        return [_recursive_clean(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_recursive_clean(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _recursive_clean(item) for key, item in value.items()}
    return value


def _replace_pdf_string(value: str) -> str:
    output = value
    for previous, replacement in _PDF_REPLACEMENTS:
        output = output.replace(previous, replacement)
    return output


def _rewrite_pdf_content_streams(reader: Any) -> int:
    from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

    replacements = 0
    for page in reader.pages:
        stream = ContentStream(page.get_contents(), reader)
        for operands, operator in stream.operations:
            if operator in {b"Tj", b"'", b'"'}:
                targets = operands
            elif operator == b"TJ" and operands:
                targets = operands[0]
            else:
                continue
            for index, operand in enumerate(targets):
                if isinstance(operand, TextStringObject):
                    original = str(operand)
                elif isinstance(operand, ByteStringObject):
                    original = bytes(operand).decode("latin-1", errors="ignore")
                else:
                    continue
                updated = _replace_pdf_string(original)
                if updated == original:
                    continue
                targets[index] = TextStringObject(updated)
                replacements += 1
        page.replace_contents(stream)
    return replacements


def _semantic_cover_overlay() -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    page.setFillColor(colors.HexColor("#7dd3fc"))
    page.setFont("Helvetica-Bold", 8.4)
    page.drawString(42, 632, _CANONICAL_TITLE)
    page.setFillColor(colors.HexColor("#fbbf24"))
    page.setFont("Helvetica-Bold", 7.4)
    page.drawString(42, 616, _FINAL_STATUS)
    page.save()
    return buffer.getvalue()


def rewrite_comprehensive_pdf_semantics(pdf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    from pypdf import PdfReader, PdfWriter

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Comprehensive final report did not contain a valid PDF signature.")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    replacements = _rewrite_pdf_content_streams(reader)
    if reader.pages:
        overlay = PdfReader(io.BytesIO(_semantic_cover_overlay()))
        reader.pages[0].merge_page(overlay.pages[0], over=True)

    writer = PdfWriter()
    writer.append(reader, import_outline=True)
    writer.add_metadata(
        {
            "/Title": _CANONICAL_TITLE,
            "/Author": "NICO",
            "/Subject": "Final report pending required human approval",
        }
    )
    output = io.BytesIO()
    writer.write(output)
    finalized = output.getvalue()

    verified = PdfReader(io.BytesIO(finalized))
    extracted = "\n".join(page.extract_text() or "" for page in verified.pages)
    normalized = " ".join(extracted.split())
    stale = sorted({match.group(0) for match in _STALE_RE.finditer(extracted)})
    contract = {
        "status": "passed" if not stale and _CANONICAL_TITLE in extracted and "FINAL REPORT" in extracted.upper() and "PENDING HUMAN APPROVAL" in extracted.upper() else "failed",
        "version": VERSION,
        "page_count": len(verified.pages),
        "content_stream_replacements": replacements,
        "canonical_title_present": _CANONICAL_TITLE in extracted or _CANONICAL_TITLE in normalized,
        "final_report_language_present": "FINAL REPORT" in extracted.upper(),
        "pending_approval_language_present": "PENDING HUMAN APPROVAL" in extracted.upper(),
        "stale_draft_language_absent": not stale,
        "stale_matches": stale,
    }
    return finalized, contract


def _set_finality(value: Any) -> None:
    if not isinstance(value, dict):
        return
    value["report_finality"] = "final"
    value["approval_status"] = "pending_human_approval"
    value["delivery_status"] = "blocked_pending_human_approval"
    value["human_review_required"] = True
    value["client_delivery_allowed"] = False


def finalize_comprehensive_report_result(result: dict[str, Any]) -> dict[str, Any]:
    output = _recursive_clean(deepcopy(result))
    package = output.get("report_package") if isinstance(output.get("report_package"), dict) else {}
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    encoded = str(package.get("pdf_base64") or "")

    pdf_contract: dict[str, Any]
    try:
        source_pdf = base64.b64decode(encoded, validate=True)
        final_pdf, pdf_contract = rewrite_comprehensive_pdf_semantics(source_pdf)
    except Exception as exc:
        final_pdf = b""
        pdf_contract = {
            "status": "failed",
            "version": VERSION,
            "error": f"{type(exc).__name__}: {exc}",
            "canonical_title_present": False,
            "final_report_language_present": False,
            "pending_approval_language_present": False,
            "stale_draft_language_absent": False,
        }

    _set_finality(canonical)
    _set_finality(package)
    _set_finality(output)
    package["json"] = canonical
    package["markdown"] = markdown
    package["html"] = rendered_html
    package["pdf_base64"] = base64.b64encode(final_pdf).decode("ascii") if final_pdf else ""
    package["pdf_filename"] = re.sub(
        r"(?:-DRAFT)?\.pdf$",
        "-FINAL-PENDING-APPROVAL.pdf",
        str(package.get("pdf_filename") or "nico-comprehensive-final-report.pdf"),
        flags=re.IGNORECASE,
    )
    package["pdf_sha256"] = hashlib.sha256(final_pdf).hexdigest() if final_pdf else ""
    package["pdf_page_count"] = int(pdf_contract.get("page_count") or 0)
    package["final_package_page_count"] = package["pdf_page_count"]
    package["markdown_sha256"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    package["html_sha256"] = hashlib.sha256(rendered_html.encode("utf-8")).hexdigest()
    canonical_hash = _canonical_hash(canonical)
    package["canonical_truth_sha256"] = canonical_hash
    output["canonical_truth_sha256"] = canonical_hash

    quality = package.get("report_quality_contract") if isinstance(package.get("report_quality_contract"), dict) else {}
    quality.update(
        {
            "final_report_semantics_version": VERSION,
            "canonical_comprehensive_title_present": bool(pdf_contract.get("canonical_title_present")),
            "final_report_language_present": bool(pdf_contract.get("final_report_language_present")),
            "pending_human_approval_language_present": bool(pdf_contract.get("pending_approval_language_present")),
            "stale_draft_language_absent": bool(pdf_contract.get("stale_draft_language_absent")),
            "final_report_semantic_contract": pdf_contract,
            "report_finality": "final",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    package["report_quality_contract"] = quality
    output["report_quality_contract"] = dict(quality)
    output["report_package"] = package

    semantic_passed = bool(
        pdf_contract.get("status") == "passed"
        and _CANONICAL_TITLE in markdown
        and not _STALE_RE.search(markdown)
        and not _STALE_RE.search(rendered_html)
        and "FINAL REPORT" in markdown.upper()
        and "PENDING HUMAN APPROVAL" in markdown.upper()
    )
    if output.get("status") == "complete" and semantic_passed:
        output["reason"] = ""
    else:
        output["status"] = "blocked"
        output["reason"] = "comprehensive_final_report_semantic_contract_failed"
    return output


def install_comprehensive_final_report_semantics_v47() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report_module

    current: Callable[..., dict[str, Any]] = report_module.build_comprehensive_report_package
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def build_final_report(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return finalize_comprehensive_report_result(current(*args, **kwargs))

    setattr(build_final_report, _PATCH_MARKER, True)
    setattr(build_final_report, "_nico_previous", current)
    report_module.build_comprehensive_report_package = build_final_report
    return {
        "status": "installed",
        "version": VERSION,
        "bound": report_module.build_comprehensive_report_package is build_final_report,
        "canonical_title": _CANONICAL_TITLE,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "stale_draft_language_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "finalize_comprehensive_report_result",
    "install_comprehensive_final_report_semantics_v47",
    "rewrite_comprehensive_pdf_semantics",
]
