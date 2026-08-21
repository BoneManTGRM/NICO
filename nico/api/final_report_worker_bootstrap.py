from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_spanish_assessment_scope_v97 import (
    install_comprehensive_spanish_assessment_scope_v97,
)
from nico.comprehensive_spanish_canonical_acceptance_normalization_v96 import (
    install_comprehensive_spanish_canonical_acceptance_normalization_v96,
)
from nico.comprehensive_spanish_canonical_evidence_literals_v95 import (
    install_comprehensive_spanish_canonical_evidence_literals_v95,
)
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
)

VERSION = "nico.api.final_report_worker_bootstrap.v4"

# This module is the isolated final-report renderer entry point. It deliberately starts
# from the same terminal report/language authority used by production, then adds only
# child-process presentation/runtime controls required by the final renderer. Parent
# process worker orchestration, physical-exit hardening, and synthetic production-proof
# lifecycle remain outside this child.
#
# Canonical finding deduplication can remove terminal punctuation from semantically
# equivalent acceptance criteria. Install the bounded v96 contract normalization before
# the later Spanish field guards and before v94 caches the final field translator. This
# keeps approved generator contracts translatable without weakening unknown-prose
# fail-closed behavior.
SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION = (
    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
)
setattr(
    app.state,
    "nico_spanish_canonical_acceptance_normalization",
    SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION,
)

if SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION.get("status") not in {
    "installed",
    "already_installed",
}:
    raise RuntimeError(
        "Spanish canonical acceptance normalization did not install in renderer worker: "
        f"{SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION}"
    )
if SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION.get("bound") is not True:
    raise RuntimeError("Spanish canonical acceptance normalization is not bound")
if (
    SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION.get(
        "production_complexity_acceptance_without_period_supported"
    )
    is not True
):
    raise RuntimeError(
        "Spanish renderer cannot translate normalized complexity acceptance criteria"
    )
if (
    SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION.get(
        "unknown_presentation_prose_still_fail_closed"
    )
    is not True
):
    raise RuntimeError(
        "Spanish acceptance normalization weakened unknown-prose fail-closed behavior"
    )

# The production scoring record contributes one report-owned assessment-scope sentence.
# Bind its exact es-MX presentation contract before v94 captures the final translator.
# Unknown scope prose remains owned by the existing fail-closed canonical boundary.
SPANISH_ASSESSMENT_SCOPE = install_comprehensive_spanish_assessment_scope_v97()
setattr(
    app.state,
    "nico_spanish_assessment_scope",
    SPANISH_ASSESSMENT_SCOPE,
)

if SPANISH_ASSESSMENT_SCOPE.get("status") not in {
    "installed",
    "already_installed",
}:
    raise RuntimeError(
        "Spanish assessment-scope contract did not install in renderer worker: "
        f"{SPANISH_ASSESSMENT_SCOPE}"
    )
if SPANISH_ASSESSMENT_SCOPE.get("bound") is not True:
    raise RuntimeError("Spanish assessment-scope contract is not bound")
if (
    SPANISH_ASSESSMENT_SCOPE.get(
        "production_assessment_scope_translation_supported"
    )
    is not True
):
    raise RuntimeError("Spanish renderer cannot translate the production assessment scope")
if (
    SPANISH_ASSESSMENT_SCOPE.get(
        "unknown_assessment_scope_contract_unregistered"
    )
    is not True
):
    raise RuntimeError("Spanish assessment-scope contract registered unapproved prose")

# Install the canonical-evidence guard before v94 wraps the field translator in its
# process-local cache. This preserves exact repository/scanner evidence flattened under
# an ``evidence`` presentation field while leaving real report-owned prose fail-closed.
SPANISH_CANONICAL_EVIDENCE_LITERALS = (
    install_comprehensive_spanish_canonical_evidence_literals_v95()
)
setattr(
    app.state,
    "nico_spanish_canonical_evidence_literals",
    SPANISH_CANONICAL_EVIDENCE_LITERALS,
)

if SPANISH_CANONICAL_EVIDENCE_LITERALS.get("status") not in {
    "installed",
    "already_installed",
}:
    raise RuntimeError(
        "Spanish canonical-evidence literal guard did not install in renderer worker: "
        f"{SPANISH_CANONICAL_EVIDENCE_LITERALS}"
    )
if SPANISH_CANONICAL_EVIDENCE_LITERALS.get("bound") is not True:
    raise RuntimeError("Spanish canonical-evidence literal guard is not bound")
if (
    SPANISH_CANONICAL_EVIDENCE_LITERALS.get(
        "report_owned_presentation_prose_still_fail_closed"
    )
    is not True
):
    raise RuntimeError("Spanish renderer no longer fails closed on presentation prose")
if (
    SPANISH_CANONICAL_EVIDENCE_LITERALS.get("canonical_evidence_byte_preserving")
    is not True
):
    raise RuntimeError("Spanish renderer does not preserve canonical evidence literals")

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
    "spanish_canonical_acceptance_normalization_bound": True,
    "spanish_assessment_scope_contract_bound": True,
    "spanish_canonical_evidence_literals_bound": True,
    "spanish_final_report_runtime_cache_bound": True,
    "canonical_acceptance_terminal_period_loss_supported": True,
    "production_assessment_scope_translation_supported": True,
    "canonical_evidence_literals_preserved": True,
    "presentation_prose_still_fail_closed": True,
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
    "SPANISH_ASSESSMENT_SCOPE",
    "SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION",
    "SPANISH_CANONICAL_EVIDENCE_LITERALS",
    "SPANISH_FINAL_REPORT_RUNTIME_CACHE",
    "VERSION",
    "app",
]
