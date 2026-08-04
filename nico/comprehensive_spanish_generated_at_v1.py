from __future__ import annotations

import re
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-spanish-generated-at.v1"
_MARKER = "__nico_comprehensive_spanish_generated_at_v1__"
_TIMESTAMP = re.compile(r"^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _generated_at(canonical: Mapping[str, Any]) -> str:
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    value = _text(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp")
    )
    if not _TIMESTAMP.fullmatch(value):
        raise ValueError("Spanish Comprehensive renderer requires one canonical generated_at")
    return value


def _insert_generated_label(markdown: str, generated_at: str) -> str:
    if re.search(r"(?im)^Generado\s*:", markdown):
        return markdown
    lines = str(markdown or "").splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        lines[1:1] = ["", f"Generado: {generated_at}"]
    else:
        lines = [f"Generado: {generated_at}", "", *lines]
    return "\n".join(lines).rstrip() + "\n"


def install_comprehensive_spanish_generated_at_v1() -> dict[str, Any]:
    from nico import comprehensive_client_truth_canonical_v2 as truth
    from nico import v2_premium_report_renderer as renderer

    current = renderer._spanish_markdown
    if not getattr(current, _MARKER, False):

        @wraps(current)
        def _spanish_markdown(canonical: Mapping[str, Any]) -> str:
            generated_at = _generated_at(canonical)
            markdown = current(canonical)
            markdown = markdown.replace(
                "NICO completó una Evaluación Técnica Integral autorizada para",
                "NICO generó un borrador automatizado de Evaluación Técnica Integral para",
            ).replace(
                "NICO completó una evaluación técnica integral autorizada para",
                "NICO generó un borrador automatizado de evaluación técnica integral para",
            )
            return _insert_generated_label(markdown, generated_at)

        setattr(_spanish_markdown, _MARKER, True)
        setattr(_spanish_markdown, "_nico_previous", current)
        renderer._spanish_markdown = _spanish_markdown
        status = "installed"
    else:
        status = "already_installed"

    truth._GENERATED_LABEL = re.compile(
        r"\b(?:Generated(?:\s+at)?|Generado)\s*:?[\s<>&a-zA-Z0-9;/=\"'-]{0,80}?"
        r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)",
        re.IGNORECASE,
    )
    return {
        "status": status,
        "version": VERSION,
        "spanish_generated_label_bound": True,
        "canonical_timestamp_required": True,
        "authorized_automation_claims_removed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_spanish_generated_at_v1",
]
