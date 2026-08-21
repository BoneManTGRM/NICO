from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
)

VERSION = "nico.api.final_report_worker_bootstrap.v1"

# This module is the isolated final-report renderer entry point. It deliberately starts
# from the same terminal report/language authority used by production, then adds only
# the bounded Spanish render cache needed by the final renderer. Parent-process worker
# orchestration, physical-exit hardening, and synthetic production-proof lifecycle are
# intentionally not installed in this child. Reinstalling those web-process concerns
# inside every renderer process duplicates app state and can create a self-referential
# final-report runtime around an already isolated renderer.
SPANISH_FINAL_REPORT_RUNTIME_CACHE = (
    install_comprehensive_spanish_final_report_runtime_cache_v94()
)
setattr(
    app.state,
    "nico_spanish_final_report_runtime_cache",
    SPANISH_FINAL_REPORT_RUNTIME_CACHE,
)

if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("status") not in {
    "installed",
    "already_installed",
}:
    raise RuntimeError(
        "Spanish final-report runtime cache did not install in renderer worker: "
        f"{SPANISH_FINAL_REPORT_RUNTIME_CACHE}"
    )
if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("bound") is not True:
    raise RuntimeError("Spanish final-report renderer cache is not bound")
if (
    SPANISH_FINAL_REPORT_RUNTIME_CACHE.get(
        "preflight_translation_results_reused_by_renderer"
    )
    is not True
):
    raise RuntimeError("Spanish renderer does not reuse translation results")
if (
    SPANISH_FINAL_REPORT_RUNTIME_CACHE.get(
        "markdown_pdf_localized_inputs_reused_for_same_canonical_object"
    )
    is not True
):
    raise RuntimeError("Spanish renderer does not reuse localized Markdown/PDF inputs")
if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("human_review_required") is not True:
    raise RuntimeError("Renderer worker must preserve human review")
if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("client_delivery_allowed") is not False:
    raise RuntimeError("Renderer worker must block unapproved client delivery")

FINAL_REPORT_WORKER_RUNTIME = {
    "artifact_schema": VERSION,
    "status": "ready",
    "same_terminal_report_authority_as_production": True,
    "spanish_final_report_runtime_cache_bound": True,
    "process_isolation_owned_by_parent": True,
    "physical_exit_hardening_owned_by_parent": True,
    "production_proof_lifecycle_owned_by_parent": True,
    "nested_renderer_orchestration_installed": False,
    "human_review_required": True,
    "client_delivery_allowed": False,
}
setattr(app.state, "nico_final_report_worker_runtime", FINAL_REPORT_WORKER_RUNTIME)


__all__ = [
    "FINAL_REPORT_WORKER_RUNTIME",
    "SPANISH_FINAL_REPORT_RUNTIME_CACHE",
    "VERSION",
    "app",
]
