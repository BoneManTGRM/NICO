from __future__ import annotations

import contextvars
import time
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive-final-report-compact-base.v1"
_BUILD_MARKER = "__nico_final_report_compact_build_v1__"
_PDF_MARKER = "__nico_final_report_compact_pdf_v1__"

_COMPACT_FINAL_PDF: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "nico_compact_final_pdf_projection",
    default=False,
)


def _compact_pdf_call(
    original: Callable[..., tuple[str | None, str | None, int]],
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    generated_at: str,
) -> tuple[str | None, str | None, int]:
    """Render only the decision-oriented base PDF for the final package.

    The final client composer immediately removes the raw stage appendix and appends
    the substantive review companion, compact exact-source register, and evidence
    gate. Rendering every stage appendix page before removing it duplicates the most
    expensive ReportLab work and caused real production runs to exceed the 240-second
    atomic publication boundary.

    Markdown, HTML, canonical JSON, stage summaries, and the durable run record retain
    the complete structured stage evidence. Only the disposable intermediate PDF
    projection is compacted.
    """

    if not _COMPACT_FINAL_PDF.get():
        return original(identity, assessment, stages, generated_at)
    return original(identity, assessment, [], generated_at)


def install_comprehensive_final_report_compact_base_v1() -> dict[str, Any]:
    from nico import comprehensive_native_providers as native
    from nico import comprehensive_report_package as report_module

    pdf_current = report_module._pdf
    if not getattr(pdf_current, _PDF_MARKER, False):

        @wraps(pdf_current)
        def _pdf(
            identity: dict[str, Any],
            assessment: dict[str, Any],
            stages: list[dict[str, Any]],
            generated_at: str,
        ) -> tuple[str | None, str | None, int]:
            return _compact_pdf_call(
                pdf_current,
                identity,
                assessment,
                stages,
                generated_at,
            )

        setattr(_pdf, _PDF_MARKER, True)
        setattr(_pdf, "_nico_previous", pdf_current)
        report_module._pdf = _pdf

    build_current = native._build_report
    if not getattr(build_current, _BUILD_MARKER, False):

        @wraps(build_current)
        def _build_report(
            context: dict[str, Any],
            final: bool,
        ) -> dict[str, Any]:
            token = _COMPACT_FINAL_PDF.set(bool(final))
            started = time.perf_counter()
            try:
                result = build_current(context, final)
            finally:
                _COMPACT_FINAL_PDF.reset(token)
            if not final or not isinstance(result, dict):
                return result

            elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
            output = dict(result)
            projection = {
                "artifact_schema": VERSION,
                "status": "complete",
                "projection": "decision_oriented_base_pdf",
                "raw_stage_appendix_rendered_in_intermediate_pdf": False,
                "full_stage_evidence_retained_in_canonical_json": True,
                "full_stage_evidence_retained_in_durable_run": True,
                "substantive_review_companion_required": True,
                "compact_exact_source_register_required": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "elapsed_ms": elapsed_ms,
            }
            output["final_report_compact_base"] = projection
            evidence = (
                dict(output.get("evidence"))
                if isinstance(output.get("evidence"), dict)
                else {}
            )
            evidence["final_report_compact_base"] = projection
            output["evidence"] = evidence
            return output

        setattr(_build_report, _BUILD_MARKER, True)
        setattr(_build_report, "_nico_previous", build_current)
        native._build_report = _build_report

    return {
        "status": "installed",
        "version": VERSION,
        "final_intermediate_pdf_is_decision_oriented": True,
        "raw_stage_appendix_rendered_in_intermediate_pdf": False,
        "full_stage_evidence_retained_outside_client_pdf": True,
        "report_design_changed": False,
        "score_contract_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_compact_pdf_call",
    "install_comprehensive_final_report_compact_base_v1",
]
