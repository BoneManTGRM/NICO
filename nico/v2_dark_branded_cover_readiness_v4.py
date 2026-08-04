from __future__ import annotations

import io
from typing import Any, Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ByteStringObject, ContentStream, TextStringObject

VERSION = "nico.v2.dark-branded-cover-readiness.v4"
_MARKER = "__nico_dark_cover_readiness_v4__"

_TEXT_REPLACEMENTS = {
    "INTERNAL REVIEW": "HUMAN APPROVAL",
    "REVISIÓN INTERNA": "APROBACIÓN HUMANA",
    "Required": "Pending",
    "Obligatoria": "Pendiente",
    "CLIENT-READY": "REVIEW PACKAGE",
    "LISTO PARA CLIENTE": "PAQUETE DE REVISIÓN",
    "No": "Ready",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _truthful_executive_posture(
    canonical: Mapping[str, Any],
    technical: str,
    adjusted: str,
    *,
    spanish: bool,
) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    repository = _text(identity.get("repository"))
    if spanish:
        return (
            f"NICO completó una evaluación técnica integral autorizada para {repository}. "
            f"La madurez técnica ponderada es {technical} y la preparación ajustada por evidencia es {adjusted}. "
            "El paquete combina salud del repositorio, hallazgos con ubicación exacta, evidencia de arquitectura, "
            "un marco de hoja de ruta de seis meses pendiente de validación y exportaciones estructuradas para revisión humana."
        )
    return (
        f"NICO completed an authorized Comprehensive Technical Assessment for {repository}. "
        f"Weighted technical maturity is {technical}; independently evidence-adjusted readiness is {adjusted}. "
        "The package combines repository health, exact-location findings, architecture evidence, "
        "a six-month roadmap framework pending stakeholder validation, and structured exports for human review."
    )


def _replace_operand(value: Any) -> tuple[Any, bool]:
    if isinstance(value, TextStringObject):
        original = str(value)
        replacement = _TEXT_REPLACEMENTS.get(original)
        if replacement is not None:
            return TextStringObject(replacement), True
        return value, False
    if isinstance(value, ByteStringObject):
        original = bytes(value)
        try:
            decoded = original.decode("latin-1")
        except Exception:
            return value, False
        replacement = _TEXT_REPLACEMENTS.get(decoded)
        if replacement is not None:
            return ByteStringObject(replacement.encode("latin-1", errors="replace")), True
    return value, False


def _replace_cover_readiness_text(pdf: bytes) -> bytes:
    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    for source_page in reader.pages:
        writer.add_page(source_page)
        page = writer.pages[-1]
        stream = ContentStream(page.get_contents(), writer)
        changed = False
        for operands, operator in stream.operations:
            if operator == b"Tj" and operands:
                operands[0], replaced = _replace_operand(operands[0])
                changed = changed or replaced
            elif operator == b"TJ" and operands:
                for index, value in enumerate(operands[0]):
                    operands[0][index], replaced = _replace_operand(value)
                    changed = changed or replaced
            elif operator in {b"'", b'"'} and operands:
                operands[-1], replaced = _replace_operand(operands[-1])
                changed = changed or replaced
        if changed:
            page.replace_contents(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_dark_branded_cover_readiness_v4() -> dict[str, Any]:
    from nico import v2_dark_branded_cover as cover

    current_cover = cover._cover
    if getattr(current_cover, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
        }

    cover._executive_posture = _truthful_executive_posture

    def _cover(canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
        return _replace_cover_readiness_text(current_cover(canonical, spanish=spanish))

    setattr(_cover, _MARKER, True)
    setattr(_cover, "_nico_previous", current_cover)
    cover._cover = _cover
    return {
        "status": "installed",
        "version": VERSION,
        "premium_design_preserved": True,
        "review_package_ready": True,
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
        "roadmap_claim": "framework_pending_stakeholder_validation",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_dark_branded_cover_readiness_v4",
]
