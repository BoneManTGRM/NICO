from __future__ import annotations

VERSION = "nico.client-text-status-sanitizer.v1"

_REPLACEMENTS = (
    ("a final automated assessment", "an automated draft assessment"),
    ("a final automated report", "an automated draft report"),
    ("final automated assessment", "automated draft assessment"),
    ("final automated report", "automated draft report"),
    ("a automated draft assessment", "an automated draft assessment"),
    ("a automated draft report", "an automated draft report"),
    ("The report is a automated draft", "The report is an automated draft"),
    ("The package is a automated draft", "The package is an automated draft"),
    ("FINAL REPORT · PENDING HUMAN APPROVAL", "AUTOMATED DRAFT · PENDING HUMAN APPROVAL"),
    ("FINAL REPORT — PENDING HUMAN APPROVAL", "AUTOMATED DRAFT — PENDING HUMAN APPROVAL"),
    ("AUTOMATED FINAL", "AUTOMATED DRAFT"),
    ("INFORME FINAL PENDIENTE DE APROBACIÓN", "BORRADOR AUTOMATIZADO PENDIENTE DE APROBACIÓN"),
)


def sanitize_client_text_status(value: str) -> str:
    output = str(value or "")
    for old, new in _REPLACEMENTS:
        output = output.replace(old, new)
    return output


__all__ = ["VERSION", "sanitize_client_text_status"]
