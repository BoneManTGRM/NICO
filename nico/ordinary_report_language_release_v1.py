"""Validated ordinary report languages; does not alter frozen artifact authority."""
from collections.abc import Mapping

SPANISH_UNAVAILABLE = "spanish_report_generation_unavailable"


def normalize_new_report_language(language: object) -> str:
    """Normalize only new requests, never retained artifact identities."""
    if language is None:
        return "en"
    if not isinstance(language, str):
        raise ValueError("unsupported_report_language")
    token = language.strip().lower().replace("_", "-")
    aliases = {"en": "en", "en-us": "en", "es": "es-MX", "es-mx": "es-MX"}
    if token not in aliases:
        raise ValueError("unsupported_report_language")
    return aliases[token]


def require_new_report_language(language: object) -> None:
    normalize_new_report_language(language)


def require_available_projection(status: Mapping, target_language: str) -> None:
    """Early admission only; existing validators still prove frozen integrity."""
    require_new_report_language(target_language)
    if target_language != "es-MX":
        return
    reports = status.get("reports")
    canonical = reports.get("json") if isinstance(reports, Mapping) else None
    if (not isinstance(canonical, Mapping)
            or not isinstance(reports.get("pdf_base64"), str) or not reports.get("pdf_base64")):
        # The normal projection validators own missing/nonterminal artifacts.
        # Admission no longer throws for qualified Spanish generation.
        return
    # Use the same alias normalization, canonical locale locations, and identity
    # consistency checks as frozen delivery. Hash/lifecycle validation follows.
    from nico.comprehensive_same_run_locale_report_v1 import _validate_status_canonical_identity
    source = _validate_status_canonical_identity(status, canonical)
    if source["report_language"] != target_language:
        require_new_report_language(target_language)
