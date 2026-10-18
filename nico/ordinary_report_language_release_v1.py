"""Temporary ordinary-release boundary; does not alter frozen artifact authority."""
from collections.abc import Mapping

SPANISH_UNAVAILABLE = "spanish_report_generation_unavailable"


def require_new_report_language(language: object) -> None:
    token = str(language or "en").strip().lower().replace("_", "-")
    if token == "es" or token.startswith("es-"):
        raise ValueError(SPANISH_UNAVAILABLE)


def require_available_projection(status: Mapping, target_language: str) -> None:
    """Early admission only; existing validators still prove frozen integrity."""
    if target_language != "es-MX":
        return
    reports = status.get("reports")
    canonical = reports.get("json") if isinstance(reports, Mapping) else None
    if (not isinstance(canonical, Mapping)
            or not isinstance(reports.get("pdf_base64"), str) or not reports.get("pdf_base64")):
        require_new_report_language(target_language)
    # Use the same alias normalization, canonical locale locations, and identity
    # consistency checks as frozen delivery. Hash/lifecycle validation follows.
    from nico.comprehensive_same_run_locale_report_v1 import _validate_status_canonical_identity
    source = _validate_status_canonical_identity(status, canonical)
    if source["report_language"] != target_language:
        require_new_report_language(target_language)
