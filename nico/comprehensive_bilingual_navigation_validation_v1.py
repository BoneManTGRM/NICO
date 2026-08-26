from __future__ import annotations

import base64
import io
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive_bilingual_navigation_validation.v1.2"
_MARKER = "__nico_bilingual_navigation_validation_v1__"
_LOCALIZABLE_LEGACY_FAILURES = (
    "final PDF does not retain continuous physical page labels",
    "final PDF does not retain a table of contents",
    "el PDF final no conserva etiquetas continuas de página física",
    "el PDF final no conserva un índice",
)


def _text(value: Any, limit: int = 300) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _reported_locale(result: Mapping[str, Any]) -> str:
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    return _text(
        identity.get("report_language")
        or identity.get("locale")
        or canonical.get("report_language")
        or canonical.get("locale"),
        40,
    ).casefold()


def _pdf_reader(result: Mapping[str, Any]) -> tuple[PdfReader, str]:
    encoded = result.get("pdf_base64")
    try:
        pdf = base64.b64decode(str(encoded or ""), validate=True)
        reader = PdfReader(io.BytesIO(pdf))
        extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise ValueError("final Comprehensive artifact has no valid PDF") from exc
    return reader, extracted


def _spanish_artifact(result: Mapping[str, Any], extracted: str) -> bool:
    locale = _reported_locale(result)
    if locale in {"es", "es-mx", "es_mx", "es-mexico", "spanish"}:
        return True
    upper = extracted.upper()
    return any(
        marker in upper
        for marker in (
            "BORRADOR AUTOMATIZADO",
            "TABLA DE CONTENIDO",
            "PÁGINA DEL DOCUMENTO",
        )
    )


def _validate_spanish_navigation(reader: PdfReader, extracted: str) -> None:
    total = len(reader.pages)
    for index in range(1, total + 1):
        expected = f"Página del documento {index} de {total}"
        if expected not in extracted:
            raise ValueError(
                "final es-MX PDF does not retain localized continuous physical page labels"
            )
    if "Document page " in extracted:
        raise ValueError(
            "Mexican-Spanish final PDF retained NICO-authored English physical page labels"
        )
    if "Tabla de contenido" not in extracted:
        raise ValueError("final es-MX PDF does not retain a localized table of contents")
    if "Table of Contents" in extracted:
        raise ValueError(
            "Mexican-Spanish final PDF retained NICO-authored English TOC copy"
        )
    if not reader.outline:
        raise ValueError("final PDF does not retain navigation bookmarks")


def install_bilingual_navigation_validation_v1() -> dict[str, Any]:
    """Keep final-package validation strict while permitting localized navigation.

    English artifacts continue through the installed validator unchanged. es-MX
    artifacts may bypass only literal legacy navigation-string failures, then must
    satisfy stricter localized page-label/TOC checks and contain no NICO-authored English
    navigation chrome. Manifest, integrity, score, finding and approval validation remain
    fail-closed.
    """

    from nico import comprehensive_manifest_navigation_v1 as navigation

    current = navigation._validate_final_package
    if getattr(current, _MARKER, False):
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "english_validation_preserved": True,
            "mexican_spanish_toc_validation_supported": True,
            "mexican_spanish_physical_page_labels_required": True,
            "english_navigation_rejected_in_es_mx": True,
            "bookmarks_still_required": True,
        }

    @wraps(current)
    def validate_bilingual_final_package(result: Mapping[str, Any]) -> None:
        legacy_error: ValueError | None = None
        try:
            current(result)
        except ValueError as exc:
            legacy_error = exc

        reader, extracted = _pdf_reader(result)
        spanish = _spanish_artifact(result, extracted)

        if not spanish:
            if legacy_error is not None:
                raise legacy_error
            return

        if legacy_error is not None and not any(
            marker in str(legacy_error) for marker in _LOCALIZABLE_LEGACY_FAILURES
        ):
            raise legacy_error

        _validate_spanish_navigation(reader, extracted)

    setattr(validate_bilingual_final_package, _MARKER, True)
    setattr(validate_bilingual_final_package, "_nico_previous", current)
    navigation._validate_final_package = validate_bilingual_final_package
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "english_validation_preserved": True,
        "mexican_spanish_toc_validation_supported": True,
        "mexican_spanish_physical_page_labels_required": True,
        "english_navigation_rejected_in_es_mx": True,
        "bookmarks_still_required": True,
        "unknown_validation_failures_still_raise": True,
    }


__all__ = ["VERSION", "install_bilingual_navigation_validation_v1"]
