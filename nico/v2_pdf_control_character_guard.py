from __future__ import annotations

import io
from functools import wraps
from typing import Any, Callable, Mapping

VERSION = "nico.v2.pdf-control-character-guard.v1"
_MARKER = "__nico_pdf_control_character_guard_v1__"


def _pdf_safe_markdown(markdown: str) -> str:
    """Keep list semantics visible without Helvetica bullet extraction corruption."""
    rows: list[str] = []
    for raw in str(markdown or "").splitlines():
        stripped = raw.lstrip()
        indent = raw[: len(raw) - len(stripped)]
        if stripped.startswith("- [ ] "):
            rows.append(f"{indent}[ ] {stripped[6:]}")
        elif stripped.startswith("- "):
            rows.append(f"{indent}* {stripped[2:]}")
        else:
            rows.append(raw)
    return "\n".join(rows)


def _assert_no_control_glyphs(pdf: bytes) -> None:
    from pypdf import PdfReader

    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    invalid = sorted(
        {
            ord(char)
            for char in text
            if (ord(char) < 32 and char not in "\n\r\t") or 0x7F <= ord(char) <= 0x9F
        }
    )
    if invalid:
        rendered = ", ".join(f"U+{value:04X}" for value in invalid)
        raise ValueError(f"Authoritative PDF contains control-character glyphs: {rendered}")


def install_pdf_control_character_guard() -> dict[str, Any]:
    from nico import v2_authoritative_premium_report as report

    current: Callable[..., tuple[bytes, int]] = report._pdf_from_markdown
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def wrapped(markdown: str, canonical: Mapping[str, Any], *, spanish: bool) -> tuple[bytes, int]:
        pdf, page_count = current(_pdf_safe_markdown(markdown), canonical, spanish=spanish)
        _assert_no_control_glyphs(pdf)
        return pdf, page_count

    setattr(wrapped, _MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    report._pdf_from_markdown = wrapped
    return {
        "status": "installed",
        "version": VERSION,
        "bound": report._pdf_from_markdown is wrapped,
        "pdf_control_glyph_validation": True,
        "markdown_and_html_unchanged": True,
    }


__all__ = [
    "VERSION",
    "_assert_no_control_glyphs",
    "_pdf_safe_markdown",
    "install_pdf_control_character_guard",
]
