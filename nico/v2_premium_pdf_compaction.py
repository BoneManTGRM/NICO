from __future__ import annotations

import io
import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.v2.premium-pdf-compaction.v1"
_MARKER = "__nico_v2_premium_pdf_compaction_v1__"


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def compact_metadata_only_pages(pdf: bytes) -> bytes:
    """Remove only the renderer-created metadata-only spacer page.

    The dark cover already retains repository, run, and exact commit identity,
    while canonical JSON retains the full identity object. Evidence and chapter
    pages are never removed by this compactor.
    """

    if not pdf.startswith(b"%PDF"):
        return pdf
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf))
    writer = PdfWriter()
    removed = 0
    for index, page in enumerate(reader.pages):
        text = _normalized(page.extract_text() or "")
        lowered = text.casefold()
        metadata_markers = (
            ("generated:" in lowered or "generado:" in lowered)
            and ("service id:" in lowered or "id de servicio:" in lowered)
            and ("run id:" in lowered or "id de ejecución:" in lowered or "id de ejecucion:" in lowered)
            and ("commit" in lowered)
        )
        substantive_heading = any(
            heading in lowered
            for heading in (
                "executive decision brief",
                "resumen ejecutivo",
                "technical scorecard",
                "panel ejecutivo",
                "evidence foundation",
                "fundamento de evidencia",
            )
        )
        # Never remove the cover or dashboard. Only remove the isolated metadata
        # page created before the first substantive report chapter.
        if index >= 2 and metadata_markers and not substantive_heading and len(text) < 700:
            removed += 1
            continue
        writer.add_page(page)
    if not removed:
        return pdf
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_premium_pdf_compaction() -> dict[str, Any]:
    from nico import v2_premium_report_renderer as renderer

    current: Callable[..., bytes] = renderer._pdf
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION, "bound": True}

    @wraps(current)
    def compacted(markdown: str, canonical: dict[str, Any], *, spanish: bool) -> bytes:
        return compact_metadata_only_pages(current(markdown, canonical, spanish=spanish))

    setattr(compacted, _MARKER, True)
    setattr(compacted, "_nico_previous", current)
    renderer._pdf = compacted
    return {
        "status": "installed",
        "version": VERSION,
        "bound": renderer._pdf is compacted,
        "metadata_only_pages_removed": True,
        "evidence_pages_preserved": True,
    }


__all__ = ["VERSION", "compact_metadata_only_pages", "install_premium_pdf_compaction"]
