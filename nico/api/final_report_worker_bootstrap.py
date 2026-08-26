from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_canonical_truth_hash_compat_v1 import (
    install_canonical_truth_hash_compat,
)
from nico.comprehensive_final_worker_pdf_reflow_v1 import (
    install_comprehensive_final_worker_pdf_reflow_v1,
)
from nico.comprehensive_report_review_integrity_v1 import (
    install_comprehensive_report_review_integrity_v1,
)
from nico.comprehensive_spanish_assessment_scope_v97 import (
    install_comprehensive_spanish_assessment_scope_v97,
)
from nico.comprehensive_spanish_canonical_acceptance_normalization_v96 import (
    install_comprehensive_spanish_canonical_acceptance_normalization_v96,
)
from nico.comprehensive_spanish_canonical_evidence_literals_v95 import (
    install_comprehensive_spanish_canonical_evidence_literals_v95,
)
from nico.comprehensive_spanish_current_copy_worker_v98 import (
    install_comprehensive_spanish_current_copy_worker_v98,
)
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
)

VERSION = "nico.api.final_report_worker_bootstrap.v8.1"

# This module is the isolated final-report renderer entry point. Parent-process monkey
# patches do not cross the subprocess boundary. Install the report/review integrity
# projection here as well so the renderer that actually creates the final PDF receives
# persisted client/project display metadata and Primary Technical Contact. The binding
# remains presentation/review only: scores are unchanged, human review remains required,
# and client delivery remains blocked.
REPORT_REVIEW_INTEGRITY = install_comprehensive_report_review_integrity_v1()
setattr(app.state, "nico_worker_report_review_integrity", REPORT_REVIEW_INTEGRITY)
if REPORT_REVIEW_INTEGRITY.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError("Renderer worker report/review integrity binding did not install")
for key in (
    "final_report_context_carries_display_metadata",
    "canonical_report_identity_carries_display_metadata",
    "primary_technical_contact_projected_from_human_evidence",
    "client_evidence_summary_surfaces_display_metadata",
    "server_side_approval_readiness_remains_authoritative",
):
    if REPORT_REVIEW_INTEGRITY.get(key) is not True:
        raise RuntimeError(f"Renderer worker report/review integrity requirement missing: {key}")
if REPORT_REVIEW_INTEGRITY.get("canonical_scores_unchanged") is not True:
    raise RuntimeError("Renderer worker report/review integrity must not recompute scores")
if REPORT_REVIEW_INTEGRITY.get("human_review_required") is not True:
    raise RuntimeError("Renderer worker must preserve human review")
if REPORT_REVIEW_INTEGRITY.get("client_delivery_allowed") is not False:
    raise RuntimeError("Renderer worker must block unapproved client delivery")

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

# The current-report parity validator added new approved presentation phrases after the
# isolated renderer/cache architecture already existed. Bind those phrases inside this
# child process before v94 captures the final translators. Otherwise the parent can know
# the translations while the detached renderer still fails closed on the old English.
SPANISH_CURRENT_REPORT_COPY = install_comprehensive_spanish_current_copy_worker_v98()
setattr(app.state, "nico_spanish_current_report_copy", SPANISH_CURRENT_REPORT_COPY)
if SPANISH_CURRENT_REPORT_COPY.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError(
        "Spanish current-report copy contract did not install in renderer worker: "
        f"{SPANISH_CURRENT_REPORT_COPY}"
    )
if SPANISH_CURRENT_REPORT_COPY.get("bound") is not True:
    raise RuntimeError("Spanish current-report copy contract is not bound")
if SPANISH_CURRENT_REPORT_COPY.get("current_report_copy_contract_bound") is not True:
    raise RuntimeError("Spanish renderer cannot localize current report presentation copy")
if SPANISH_CURRENT_REPORT_COPY.get("unknown_prose_still_delegates_fail_closed") is not True:
    raise RuntimeError("Spanish current-report copy contract weakened fail-closed behavior")

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

# Final report generation happens in this child process. The parent commercial reflow
# cannot cross the subprocess boundary, and source-language PDFs are frozen once this
# worker returns them. Bind the sparse-page reflow here before canonical hash finalization
# so the generated source PDF is compacted before final TOC, page labels and bookmarks
# are rebuilt. This is presentation-only and does not mutate canonical truth.
FINAL_WORKER_PDF_REFLOW = install_comprehensive_final_worker_pdf_reflow_v1()
setattr(app.state, "nico_final_worker_pdf_reflow", FINAL_WORKER_PDF_REFLOW)
if FINAL_WORKER_PDF_REFLOW.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError("Final renderer sparse-page reflow did not install")
if FINAL_WORKER_PDF_REFLOW.get("bound") is not True:
    raise RuntimeError("Final renderer sparse-page reflow is not bound")
if FINAL_WORKER_PDF_REFLOW.get("reflow_before_final_navigation") is not True:
    raise RuntimeError("Final PDF reflow must run before final navigation assembly")
if FINAL_WORKER_PDF_REFLOW.get("bilingual_source_headers_supported") is not True:
    raise RuntimeError("Final PDF reflow must recognize English and Mexican-Spanish source headers")
if FINAL_WORKER_PDF_REFLOW.get("toc_page_labels_and_bookmarks_rebuilt_after_reflow") is not True:
    raise RuntimeError("Final PDF navigation must be rebuilt after sparse-page reflow")
if FINAL_WORKER_PDF_REFLOW.get("canonical_truth_mutated") is not False:
    raise RuntimeError("Final PDF reflow must not mutate canonical truth")
if FINAL_WORKER_PDF_REFLOW.get("human_review_required") is not True:
    raise RuntimeError("Final PDF reflow must preserve human review")
if FINAL_WORKER_PDF_REFLOW.get("client_delivery_allowed") is not False:
    raise RuntimeError("Final PDF reflow must block unapproved client delivery")

# The renderer worker is a separate process, so parent-process monkey patches do not
# automatically cross this boundary. Bind the canonical truth hash only after every
# worker-local report wrapper above has been installed. This makes the hash describe the
# final canonical JSON actually returned to and persisted by the parent, preventing new
# terminal runs from being born with a stale pre-normalization hash.
CANONICAL_TRUTH_HASH_COMPAT = install_canonical_truth_hash_compat()
setattr(app.state, "nico_worker_canonical_truth_hash_compat", CANONICAL_TRUTH_HASH_COMPAT)
if CANONICAL_TRUTH_HASH_COMPAT.get("builder_hash_sync_bound") is not True:
    raise RuntimeError("Renderer worker did not bind canonical truth hash synchronization")
if CANONICAL_TRUTH_HASH_COMPAT.get("unknown_hash_mismatch_fails_closed") is not True:
    raise RuntimeError("Renderer worker weakened unknown canonical hash mismatches")

FINAL_REPORT_WORKER_RUNTIME = {
    "artifact_schema": VERSION,
    "status": "ready",
    "same_terminal_report_authority_as_production": True,
    "report_review_integrity_bound": True,
    "final_worker_pdf_reflow_bound": True,
    "final_worker_pdf_reflow_bilingual": True,
    "spanish_canonical_acceptance_normalization_bound": True,
    "spanish_assessment_scope_contract_bound": True,
    "spanish_canonical_evidence_literals_bound": True,
    "spanish_current_report_copy_contract_bound": True,
    "spanish_final_report_runtime_cache_bound": True,
    "canonical_truth_hash_sync_bound": True,
    "canonical_acceptance_terminal_period_loss_supported": True,
    "production_assessment_scope_translation_supported": True,
    "canonical_evidence_literals_preserved": True,
    "current_report_copy_worker_safe": True,
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
    "CANONICAL_TRUTH_HASH_COMPAT",
    "FINAL_REPORT_WORKER_RUNTIME",
    "FINAL_WORKER_PDF_REFLOW",
    "REPORT_REVIEW_INTEGRITY",
    "SPANISH_ASSESSMENT_SCOPE",
    "SPANISH_CANONICAL_ACCEPTANCE_NORMALIZATION",
    "SPANISH_CANONICAL_EVIDENCE_LITERALS",
    "SPANISH_CURRENT_REPORT_COPY",
    "SPANISH_FINAL_REPORT_RUNTIME_CACHE",
    "VERSION",
    "app",
]
