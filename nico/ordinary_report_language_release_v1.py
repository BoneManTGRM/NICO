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
    identity = canonical.get("identity") if isinstance(canonical, Mapping) else None
    if (not isinstance(identity, Mapping) or identity.get("report_language") != "es-MX"
            or not isinstance(reports.get("pdf_base64"), str) or not reports.get("pdf_base64")):
        require_new_report_language(target_language)
