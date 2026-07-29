from __future__ import annotations

from typing import Any, Mapping

from nico import v2_assessment_pipeline as _assessment_pipeline
from nico.v2_canonical_premium_truth import repair_canonical_premium_truth
from nico.v2_canonical_surface_sync import synchronize_canonical_finding_surfaces
from nico.v2_premium_pdf_finality import install_v2_premium_pdf_finality

# This must run before v2_premium_report_renderer imports the production PDF
# function by value. It binds final pending-approval language and footers into
# the same premium renderer that owns the dark cover and executive dashboard.
install_v2_premium_pdf_finality()

from nico.v2_premium_evidence_appendix import (  # noqa: E402
    VERSION,
    rebuild_premium_client_artifacts_with_appendix,
)

_BUILD_MARKER = "__nico_v2_canonical_premium_truth_v3__"


def _section_sources(value: Mapping[str, Any]) -> dict[str, Any]:
    assessment = value.get("assessment") if isinstance(value.get("assessment"), Mapping) else {}
    output: dict[str, Any] = {}
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        section_id = str(raw.get("id") or raw.get("section_id") or "")
        source = raw.get("source_score_before_disposition_gate")
        if source is None:
            source = raw.get("score_value", raw.get("presented_score", raw.get("score")))
        if section_id and source is not None:
            output[section_id] = source
    return output


def _preserve_section_sources(value: dict[str, Any], sources: Mapping[str, Any]) -> None:
    assessment = value.get("assessment") if isinstance(value.get("assessment"), Mapping) else {}
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    for raw in sections:
        if not isinstance(raw, dict):
            continue
        section_id = str(raw.get("id") or raw.get("section_id") or "")
        if section_id in sources and raw.get("source_score_before_disposition_gate") is None:
            raw["source_score_before_disposition_gate"] = sources[section_id]


def _repair(value: Mapping[str, Any]) -> dict[str, Any]:
    sources = _section_sources(value)
    repaired = repair_canonical_premium_truth(value)
    _preserve_section_sources(repaired, sources)
    return synchronize_canonical_finding_surfaces(repaired)


def _install_pre_hash_canonical_repair() -> None:
    current = _assessment_pipeline.build_canonical_assessment
    if getattr(current, _BUILD_MARKER, False):
        return

    def repaired_build(report: Mapping[str, Any]) -> dict[str, Any]:
        canonical = current(report)
        return _repair(canonical)

    setattr(repaired_build, _BUILD_MARKER, True)
    setattr(repaired_build, "_nico_previous", current)
    _assessment_pipeline.build_canonical_assessment = repaired_build


_install_pre_hash_canonical_repair()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render one repaired canonical truth through the premium report.

    The pre-hash binding ensures scores, scanner records, dependency dispositions,
    non-production observations, finality, JSON, Markdown, HTML, PDF, CSV, UI, and
    persisted lifecycle records all derive from the same canonical object before
    the v2 adapter calculates its immutable truth hash.
    """
    repaired_package = dict(package)
    canonical = repaired_package.get("json")
    if isinstance(canonical, Mapping):
        repaired_package["json"] = _repair(canonical)
    return rebuild_premium_client_artifacts_with_appendix(repaired_package)


__all__ = ["VERSION", "rebuild_client_artifacts"]
