from __future__ import annotations

VERSION = "nico.client-text-status-sanitizer.v1.4"

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
    ("AUTOMATED AUTOMATED DRAFT", "AUTOMATED DRAFT"),
    ("AUTOMATED FINAL", "AUTOMATED DRAFT"),
    ("INFORME FINAL PENDIENTE DE APROBACIÓN", "BORRADOR AUTOMATIZADO PENDIENTE DE APROBACIÓN"),
    (
        "not human approval or client-delivery authorization",
        "not client approval or delivery authorization",
    ),
    (
        "NICO completed an authorized Comprehensive Technical Assessment for ",
        "NICO generated an automated Comprehensive Technical Assessment draft for ",
    ),
    (
        "The package combines repository health, exact-location findings, architecture evidence, a six-month roadmap, and actionable remediation guidance for engineering and executive review.",
        "The evidence-bound package retains repository health, exact-location findings, architecture evidence, a roadmap framework, and structured exports for human review; it is not approval or client-delivery authorization.",
    ),
    (
        "No structured item was retained.",
        "No additional structured finding detail was retained for this section.",
    ),
)


def sanitize_client_text_status(value: str) -> str:
    output = str(value or "")
    for old, new in _REPLACEMENTS:
        output = output.replace(old, new)
    return output


__all__ = ["VERSION", "sanitize_client_text_status"]
