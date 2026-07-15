from __future__ import annotations

from typing import Any, Callable

PATCH_VERSION = "nico.report_intelligence_final_pdf_binding.v1"
_MARKER = "_nico_report_intelligence_final_pdf_binding_v1"


def install_report_intelligence_final_pdf_binding() -> dict[str, Any]:
    """Make every final intelligence export overwrite the raw Markdown PDF.

    Markdown and HTML remain full-detail formats. The PDF is regenerated through
    NICO's professional structured renderer after quality and repair intelligence are
    finalized, so Markdown markers and code fences are never used as visual layout.
    """

    from nico import assessment_quality
    from nico import report_intelligence_accuracy_patch as accuracy

    current: Callable[[Any, dict[str, Any]], dict[str, Any]] = accuracy.rebuild_enriched_reports
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "professional_pdf_after_final_rebuild": True,
        }
    original = current

    def rebuild_with_professional_pdf(hosted: Any, result: dict[str, Any]) -> dict[str, Any]:
        rebuilt = original(hosted, result)
        if (
            isinstance(rebuilt, dict)
            and rebuilt.get("status") == "complete"
            and (
                isinstance(rebuilt.get("repository_quality_signals"), dict)
                or isinstance(rebuilt.get("repair_intelligence"), dict)
            )
        ):
            assessment_quality._polish_pdf_report(rebuilt)
            reports = rebuilt.get("reports") if isinstance(rebuilt.get("reports"), dict) else {}
            pdf_meta = rebuilt.get("report_intelligence_pdf") if isinstance(rebuilt.get("report_intelligence_pdf"), dict) else {}
            rebuilt["professional_report_intelligence_export"] = {
                "status": "complete" if reports.get("pdf_base64") and pdf_meta.get("structured_appendix") else "incomplete",
                "pdf_style": reports.get("pdf_style") or assessment_quality.PDF_STYLE_VERSION,
                "structured_appendix": bool(pdf_meta.get("structured_appendix")),
                "raw_markdown_rendered": bool(pdf_meta.get("raw_markdown_rendered", True)),
                "candidate_count": pdf_meta.get("candidate_count"),
                "code_suggestion_count": pdf_meta.get("code_suggestion_count"),
                "report_only": True,
                "code_changes_applied": False,
                "automatic_application_allowed": False,
                "human_review_required": True,
            }
        return rebuilt

    setattr(rebuild_with_professional_pdf, _MARKER, True)
    setattr(rebuild_with_professional_pdf, "_nico_previous", original)
    accuracy.rebuild_enriched_reports = rebuild_with_professional_pdf
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "professional_pdf_after_final_rebuild": True,
        "raw_markdown_rendered": False,
        "automatic_application_allowed": False,
    }


__all__ = ["PATCH_VERSION", "install_report_intelligence_final_pdf_binding"]
