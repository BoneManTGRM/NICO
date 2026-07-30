from __future__ import annotations

from typing import Any, Mapping

from nico.v2_authoritative_premium_report import VERSION, install_pipeline_projection
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_dark_branded_cover import apply_dark_branded_cover
from nico.v2_pdf_control_character_guard import install_pdf_control_character_guard
from nico.v2_single_pass_premium_report import rebuild_single_pass_premium_artifacts

# Install canonical truth and review-gate projection before the sole report
# compiler runs. The PDF guard remains bound for compatibility with existing
# tests and internal exports, while the final exact client PDF is validated
# after the mature premium layout and branded cover are assembled.
install_pipeline_projection()
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def _is_spanish(package: Mapping[str, Any]) -> bool:
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = str(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    ).strip().casefold()
    return language.startswith("es")


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render canonical truth through the mature report and approved cover.

    The English client PDF receives the restored decision-grade dark cover. The
    localized Spanish renderer remains intact until its equivalent dark cover is
    validated independently, preventing the cover replacement from discarding its
    localized human-review and acceptance gate.
    """
    rendered = rebuild_single_pass_premium_artifacts(package)
    if _is_spanish(rendered):
        return rendered
    return apply_dark_branded_cover(rendered)


__all__ = [
    "VERSION",
    "_PDF_CONTROL_CHARACTER_GUARD",
    "rebuild_client_artifacts",
]
