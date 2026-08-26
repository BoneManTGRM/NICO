from __future__ import annotations

import base64
import io
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive_bilingual_navigation_validation.v1"
_MARKER = "__nico_bilingual_navigation_validation_v1__"


def install_bilingual_navigation_validation_v1() -> dict[str, Any]:
    """Accept the es-MX TOC label without weakening final-package validation.

    The existing validator correctly checks manifest metadata and continuous physical
    page labels before checking for the literal English phrase ``Table of Contents``.
    The localized final PDF must instead contain ``Tabla de contenido`` and no NICO-
    authored English TOC label. Catch only that exact legacy validation failure, then
    require the localized semantic TOC and non-empty bookmarks. Every earlier validation
    condition remains enforced by the original validator.
    """

    from nico import comprehensive_manifest_navigation_v1 as navigation

    current = navigation._validate_final_package
    if getattr(current, _MARKER, False):
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "english_toc_validation_preserved": True,
            "mexican_spanish_toc_validation_supported": True,
            "bookmarks_still_required": True,
        }

    @wraps(current)
    def validate_bilingual_final_package(result: Mapping[str, Any]) -> None:
        try:
            current(result)
            return
        except ValueError as exc:
            if "does not retain a table of contents" not in str(exc):
                raise

        encoded = result.get("pdf_base64")
        try:
            pdf = base64.b64decode(str(encoded or ""), validate=True)
            reader = PdfReader(io.BytesIO(pdf))
            extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError("final Comprehensive artifact has no valid PDF") from exc
        if "Tabla de contenido" not in extracted:
            raise ValueError("final PDF does not retain a localized table of contents")
        if "Table of Contents" in extracted:
            raise ValueError("Mexican-Spanish final PDF retained NICO-authored English TOC copy")
        if not reader.outline:
            raise ValueError("final PDF does not retain navigation bookmarks")

    setattr(validate_bilingual_final_package, _MARKER, True)
    setattr(validate_bilingual_final_package, "_nico_previous", current)
    navigation._validate_final_package = validate_bilingual_final_package
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "english_toc_validation_preserved": True,
        "mexican_spanish_toc_validation_supported": True,
        "bookmarks_still_required": True,
        "unknown_validation_failures_still_raise": True,
    }


__all__ = ["VERSION", "install_bilingual_navigation_validation_v1"]
