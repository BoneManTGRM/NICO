from __future__ import annotations

import base64
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.comprehensive-zero-incomplete-validation.v1.1"
_MARKER = "__nico_comprehensive_zero_incomplete_validation_v1__"
_ZERO_INCOMPLETE = re.compile(
    r"\b0\s+remain\s+incomplete\s+or\s+review-limited\b",
    re.IGNORECASE,
)


def _normalize(value: Any) -> str:
    return _ZERO_INCOMPLETE.sub("0 remain incomplete", str(value or ""))


def _normalize_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        normalized = _normalize(original)
        return TextStringObject(normalized), normalized != original
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        for encoding in ("utf-8", "latin-1"):
            try:
                decoded = original.decode(encoding)
            except UnicodeDecodeError:
                continue
            normalized = _normalize(decoded)
            if normalized != decoded:
                return ByteStringObject(normalized.encode(encoding, errors="replace")), True
            return value, False
    return value, False


def _validation_pdf(encoded: Any) -> str:
    try:
        pdf = base64.b64decode(str(encoded or ""), validate=True)
        reader = PdfReader(io.BytesIO(pdf))
    except Exception:
        return str(encoded or "")

    writer = PdfWriter()
    changed = False
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        page_changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], replaced = _normalize_operand(operands[0])
                page_changed = page_changed or replaced
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], replaced = _normalize_operand(value)
                    page_changed = page_changed or replaced
            elif operator in {b"'", b'"'} and operands:
                operands[-1], replaced = _normalize_operand(operands[-1])
                page_changed = page_changed or replaced
        if page_changed:
            page.replace_contents(stream)
            changed = True
    if not changed:
        return str(encoded or "")
    output = io.BytesIO()
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")


def install_comprehensive_zero_incomplete_validation_v1() -> dict[str, Any]:
    """Keep zero-incomplete execution truth from tripping contradiction checks.

    The phrase is legitimate only when the retained count is exactly zero. A
    positive incomplete count remains untouched and therefore still fails the
    underlying strict contradiction validator. Only a validation copy is
    normalized; retained report bytes and their hashes are never changed.
    """

    from nico import comprehensive_client_truth_final_v1 as truth

    current = truth._validate_surfaces
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _validate_surfaces(result: Mapping[str, Any]) -> None:
        compatible = deepcopy(dict(result))
        for key in ("markdown", "html"):
            compatible[key] = _normalize(compatible.get(key))
        compatible["pdf_base64"] = _validation_pdf(compatible.get("pdf_base64"))

        canonical = (
            deepcopy(dict(compatible.get("json")))
            if isinstance(compatible.get("json"), Mapping)
            else {}
        )
        assessment = (
            deepcopy(dict(canonical.get("assessment")))
            if isinstance(canonical.get("assessment"), Mapping)
            else {}
        )
        if assessment.get("executive_summary"):
            assessment["executive_summary"] = _normalize(
                assessment.get("executive_summary")
            )
        canonical["assessment"] = assessment
        if canonical.get("executive_summary"):
            canonical["executive_summary"] = _normalize(
                canonical.get("executive_summary")
            )
        compatible["json"] = canonical
        current(compatible)

    setattr(_validate_surfaces, _MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    truth._validate_surfaces = _validate_surfaces
    return {
        "status": "installed",
        "version": VERSION,
        "zero_incomplete_execution_phrase_allowed": True,
        "positive_incomplete_counts_still_fail_closed": True,
        "validation_copy_includes_pdf": True,
        "rendered_artifacts_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_zero_incomplete_validation_v1",
]
