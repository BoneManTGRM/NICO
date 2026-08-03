from __future__ import annotations

import io
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.client-pdf-status-sanitizer.v1"

_REPLACEMENTS = (
    ("FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED", "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"),
    ("FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED", "AUTOMATED DRAFT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED"),
    ("FINAL REPORT PENDING HUMAN APPROVAL", "AUTOMATED DRAFT PENDING HUMAN APPROVAL"),
    ("INFORME FINAL · APROBACIÓN HUMANA PENDIENTE", "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE"),
    ("INFORME FINAL PENDIENTE DE APROBACIÓN", "BORRADOR AUTOMATIZADO PENDIENTE DE APROBACIÓN"),
    (" · FINAL Page", " · AUTOMATED DRAFT Page"),
    (" · FINAL Página", " · BORRADOR AUTOMATIZADO Página"),
    ("final automated assessment", "automated draft assessment"),
    ("final automated report", "automated draft report"),
    ("a final automated assessment", "an automated draft assessment"),
)


def _replace_text(value: str) -> str:
    output = str(value or "")
    for old, new in _REPLACEMENTS:
        output = output.replace(old, new)
    return output


def _replace_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        replaced = _replace_text(original)
        return TextStringObject(replaced), replaced != original
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        replaced = original
        for old, new in _REPLACEMENTS:
            replaced = replaced.replace(old.encode("utf-8"), new.encode("utf-8"))
            replaced = replaced.replace(old.encode("latin-1", "ignore"), new.encode("latin-1", "ignore"))
        return ByteStringObject(replaced), replaced != original
    return value, False


def sanitize_client_pdf_status(pdf: bytes) -> bytes:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client PDF status sanitizer requires a valid PDF")
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], operand_changed = _replace_operand(operands[0])
                changed = changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], operand_changed = _replace_operand(value)
                    changed = changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                operands[-1], operand_changed = _replace_operand(operands[-1])
                changed = changed or operand_changed
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


__all__ = ["VERSION", "sanitize_client_pdf_status"]
