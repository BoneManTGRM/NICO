from __future__ import annotations

import base64
import html
import io
import re
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-truth-diagnostics.v1.1"
_MARKER = "__nico_comprehensive_truth_diagnostics_v1__"
_FORBIDDEN = (
    "completed an authorized Comprehensive Technical Assessment",
    "completó una evaluación técnica integral autorizada",
    "Six-Month Roadmap · COMPLETE",
    "Stage ID: six_month_roadmap · Status: COMPLETE",
    "Platform Parity: Complete",
    "Decision-Grade Technical Assessment",
)
_FENCED_CODE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_HTML_CODE = re.compile(
    r"<(?:pre|code)\b[^>]*>.*?</(?:pre|code)>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG = re.compile(r"<[^>]+>")


def _markdown_semantic_text(value: str) -> str:
    """Return prose assertions while excluding quoted literal code evidence.

    Exact commit messages, source excerpts, commands, and other immutable evidence
    are intentionally rendered in Markdown code spans or fenced blocks. A forbidden
    phrase inside those literal records is not itself a report assertion. Plain
    prose remains searchable and therefore still fails closed.
    """

    source = str(value or "")
    source = _FENCED_CODE.sub(" ", source)
    source = _INLINE_CODE.sub(" ", source)
    return " ".join(source.split())


def _visible_html(value: str) -> str:
    """Return visible prose excluding code/pre literal evidence containers."""

    source = _HTML_CODE.sub(" ", str(value or ""))
    return " ".join(html.unescape(_HTML_TAG.sub(" ", source)).split())


def _pdf_text(package: Mapping[str, Any]) -> str:
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
        return " ".join(
            "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages).split()
        )
    except Exception:
        return ""


def _excerpt(value: str, marker: str, radius: int = 180) -> str:
    position = value.casefold().find(marker.casefold())
    if position < 0:
        return ""
    start = max(0, position - radius)
    end = min(len(value), position + len(marker) + radius)
    return value[start:end]


def _semantic_surfaces(package: Mapping[str, Any]) -> dict[str, str]:
    return {
        "Markdown": _markdown_semantic_text(str(package.get("markdown") or "")),
        "HTML": _visible_html(str(package.get("html") or "")),
        "PDF": _pdf_text(package),
    }


def install_comprehensive_truth_diagnostics_v1() -> dict[str, Any]:
    from nico import comprehensive_client_truth_final_v1 as truth

    current = truth._validate_surfaces
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _validate_surfaces(package: Mapping[str, Any]) -> None:
        surfaces = _semantic_surfaces(package)
        retained: list[str] = []
        for marker in _FORBIDDEN:
            for surface_name, value in surfaces.items():
                excerpt = _excerpt(value, marker)
                if excerpt:
                    retained.append(f"{surface_name}:{marker}::{excerpt}")
        if retained:
            raise ValueError(
                "Comprehensive truth diagnostic located contradictory rendered language: "
                + " || ".join(retained)
            )
        current(package)

    setattr(_validate_surfaces, _MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    truth._validate_surfaces = _validate_surfaces
    return {
        "status": "installed",
        "version": VERSION,
        "surface_specific_truth_diagnostics": True,
        "literal_code_evidence_excluded_from_semantic_claims": True,
        "plain_prose_contradictions_fail_closed": True,
        "pdf_semantic_scan_unchanged": True,
        "fail_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_FORBIDDEN",
    "_excerpt",
    "_markdown_semantic_text",
    "_pdf_text",
    "_semantic_surfaces",
    "_visible_html",
    "install_comprehensive_truth_diagnostics_v1",
]
