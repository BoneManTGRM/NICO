from __future__ import annotations

from typing import Any, Mapping

from nico import v2_assessment_pipeline as _assessment_pipeline
from nico.v2_canonical_premium_truth import repair_canonical_premium_truth
from nico.v2_premium_pdf_finality import install_v2_premium_pdf_finality

# This must run before v2_premium_report_renderer imports the production PDF
# function by value. It binds final pending-approval language and footers into
# the same premium renderer that owns the dark cover and executive dashboard.
install_v2_premium_pdf_finality()

from nico.v2_premium_evidence_appendix import (  # noqa: E402
    VERSION,
    rebuild_premium_client_artifacts_with_appendix,
)

_BUILD_MARKER = "__nico_v2_canonical_premium_truth_v1__"


def _install_pre_hash_canonical_repair() -> None:
    current = _assessment_pipeline.build_canonical_assessment
    if getattr(current, _BUILD_MARKER, False):
        return

    def repaired_build(report: Mapping[str, Any]) -> dict[str, Any]:
        canonical = current(report)
        return repair_canonical_premium_truth(canonical)

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
        repaired_package["json"] = repair_canonical_premium_truth(canonical)
    return rebuild_premium_client_artifacts_with_appendix(repaired_package)


__all__ = ["VERSION", "rebuild_client_artifacts"]
