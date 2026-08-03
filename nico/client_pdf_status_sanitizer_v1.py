from __future__ import annotations

import io
import unicodedata
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.client-pdf-status-sanitizer.v4"

_EN_BOUNDARY = "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
_ES_BOUNDARY = "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE · ENTREGA AL CLIENTE BLOQUEADA"
_REPLACEMENTS = (
    ("FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED", _EN_BOUNDARY),
    ("FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED", "AUTOMATED DRAFT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED"),
    ("FINAL REPORT PENDING HUMAN APPROVAL", "AUTOMATED DRAFT PENDING HUMAN APPROVAL"),
    ("AUTOMATED FINAL · PENDING HUMAN APPROVAL", "AUTOMATED DRAFT · PENDING HUMAN APPROVAL"),
    ("AUTOMATED FINAL — PENDING HUMAN APPROVAL", "AUTOMATED DRAFT — PENDING HUMAN APPROVAL"),
    ("AUTOMATED FINAL", "AUTOMATED DRAFT"),
    ("INFORME FINAL · APROBACIÓN HUMANA PENDIENTE", "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE"),
    ("INFORME FINAL PENDIENTE DE APROBACIÓN", "BORRADOR AUTOMATIZADO PENDIENTE DE APROBACIÓN"),
    (" · FINAL Page", " · AUTOMATED DRAFT Page"),
    (" · FINAL Página", " · BORRADOR AUTOMATIZADO Página"),
    (" · FINAL", " · AUTOMATED DRAFT"),
    ("final automated assessment", "automated draft assessment"),
    ("final automated report", "automated draft report"),
    ("a final automated assessment", "an automated draft assessment"),
)
_PRESERVED_CLIENT_MARKERS = (
    "compact finding and remediation register",
    "complete exact-source index",
    "client evidence summary",
    "human review and acceptance gate",
    "registro compacto de hallazgos y remediacion",
    "indice completo de ubicaciones",
    "resumen de evidencia para revision",
    "puerta de revision humana y aceptacion",
)
_RAW_INTERNAL_MARKERS = (
    "retained evidence",
    "stage_execution.",
    "artifact_schema",
    "human_evidence_",
    "human_evidence_summary.",
    "report_contract_reason",
    "comprehensive_final_report_semantic_contract_failed",
    "scanner_triage.",
    "technical_analysis.",
    "complexity_evidence.",
    "pre_render_scanner_truth.",
    "configuration_controls.",
    "snapshot.",
    "roadmap[",
    "staffing_plan[",
    "scanner_execution_records[",
)


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.casefold().split())


def _drop_internal_page(text: str) -> bool:
    normalized = _normalized(text)
    if any(marker in normalized for marker in _PRESERVED_CLIENT_MARKERS):
        return False
    if "evidence appendix" in normalized or "apendice de evidencia" in normalized:
        return True
    if "report_contract_reason" in normalized or "comprehensive_final_report_semantic_contract_failed" in normalized:
        return True
    marker_count = sum(marker in normalized for marker in _RAW_INTERNAL_MARKERS)
    return marker_count >= 2


def _replace_text(value: str) -> str:
    output = str(value or "")
    for old, new in _REPLACEMENTS:
        output = output.replace(old, new)
    return output


def _replace_operand(value: Any) -> tuple[Any, bool, str | None]:
    if isinstance(value, TextStringObject):
        original = str(value)
        replaced = _replace_text(original)
        return TextStringObject(replaced), replaced != original, replaced
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        replaced = original
        for old, new in _REPLACEMENTS:
            replaced = replaced.replace(old.encode("utf-8"), new.encode("utf-8"))
            replaced = replaced.replace(old.encode("latin-1", "ignore"), new.encode("latin-1", "ignore"))
        decoded: str | None = None
        for encoding in ("utf-8", "latin-1"):
            try:
                decoded = replaced.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        return ByteStringObject(replaced), replaced != original, decoded
    return value, False, None


def _dedupe_boundary(value: Any, seen: set[str]) -> tuple[Any, bool]:
    replaced, changed, text = _replace_operand(value)
    if text in {_EN_BOUNDARY, _ES_BOUNDARY}:
        if text in seen:
            if isinstance(replaced, ByteStringObject):
                return ByteStringObject(b""), True
            return TextStringObject(""), True
        seen.add(text)
    return replaced, changed


def sanitize_client_pdf_status(pdf: bytes) -> bytes:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client PDF status sanitizer requires a valid PDF")
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        if _drop_internal_page(source_page.extract_text() or ""):
            continue
        writer.add_page(source_page)
        page = writer.pages[-1]
        contents = page.get_contents()
        if contents is None:
            continue
        stream = ContentStream(contents, writer)
        changed = False
        seen_boundaries: set[str] = set()
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], operand_changed = _dedupe_boundary(operands[0], seen_boundaries)
                changed = changed or operand_changed
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], operand_changed = _dedupe_boundary(value, seen_boundaries)
                    changed = changed or operand_changed
            elif operator in {b"'", b'"'} and operands:
                operands[-1], operand_changed = _dedupe_boundary(operands[-1], seen_boundaries)
                changed = changed or operand_changed
        if changed:
            page.replace_contents(stream)
    if not writer.pages:
        raise ValueError("client PDF sanitization removed every page")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


__all__ = ["VERSION", "sanitize_client_pdf_status"]
