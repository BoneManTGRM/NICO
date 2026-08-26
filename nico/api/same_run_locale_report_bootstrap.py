from __future__ import annotations

from nico.api.spanish_final_report_bootstrap import app as spanish_final_report_app
from nico.comprehensive_canonical_truth_hash_compat_v1 import (
    VERSION as CANONICAL_TRUTH_HASH_COMPAT_VERSION,
    install_canonical_truth_hash_compat,
)
from nico.comprehensive_commercial_ship_projection_v3 import (
    install_comprehensive_commercial_ship_projection_v3,
)
from nico.comprehensive_report_review_integrity_v1 import (
    VERSION as REPORT_REVIEW_INTEGRITY_VERSION,
    install_comprehensive_report_review_integrity_v1,
)
from nico.comprehensive_same_run_locale_report_v1 import (
    PDF_ROUTE,
    ROUTE,
    VERSION as SAME_RUN_REPORT_VERSION,
    install_same_run_locale_report,
)


VERSION = "nico.api.same_run_locale_report_bootstrap.v6"

app = spanish_final_report_app
# This is the actual Railway production entrypoint. Install the intake/report-review
# integrity binding here, after the established production chain has loaded but before
# localized report/export routes are registered. Earlier fixes existed in source but
# were not installed by the process that accepted real Comprehensive intake requests,
# which allowed client/project display metadata and Primary Technical Contact to be
# omitted from the durable run/report even though Access Method and Authorized Scope
# survived through strategic human evidence.
REPORT_REVIEW_INTEGRITY = install_comprehensive_report_review_integrity_v1()
CANONICAL_TRUTH_HASH_COMPAT = install_canonical_truth_hash_compat()
COMMERCIAL_SHIP_PROJECTION = install_comprehensive_commercial_ship_projection_v3()
SAME_RUN_LOCALE_REPORT = install_same_run_locale_report(app)

if REPORT_REVIEW_INTEGRITY.get("status") not in {"installed", "already_installed"}:
    raise RuntimeError("Comprehensive report/review integrity binding did not install")
for key in (
    "intake_display_metadata_bound",
    "direct_start_display_metadata_bound",
    "display_metadata_persisted_in_initial_canonical_write",
    "final_report_context_carries_display_metadata",
    "canonical_report_identity_carries_display_metadata",
    "primary_technical_contact_projected_from_human_evidence",
    "client_evidence_summary_surfaces_display_metadata",
    "server_side_approval_readiness_remains_authoritative",
):
    if REPORT_REVIEW_INTEGRITY.get(key) is not True:
        raise RuntimeError(f"Comprehensive report/review integrity requirement missing: {key}")
if REPORT_REVIEW_INTEGRITY.get("canonical_scope_ids_unchanged") is not True:
    raise RuntimeError("Client/project display metadata must not replace canonical scope IDs")
if REPORT_REVIEW_INTEGRITY.get("canonical_scores_unchanged") is not True:
    raise RuntimeError("Report/review integrity binding must not recompute canonical scores")
if REPORT_REVIEW_INTEGRITY.get("human_review_required") is not True:
    raise RuntimeError("Report/review integrity binding must preserve human review")
if REPORT_REVIEW_INTEGRITY.get("client_delivery_allowed") is not False:
    raise RuntimeError("Report/review integrity binding must block unapproved delivery")

if CANONICAL_TRUTH_HASH_COMPAT.get("builder_hash_sync_bound") is not True:
    raise RuntimeError(
        "Final Comprehensive report packages must bind their hash to persisted canonical JSON"
    )
if CANONICAL_TRUTH_HASH_COMPAT.get("same_run_legacy_recovery_bound") is not True:
    raise RuntimeError(
        "Known historical post-render canonical hash drift must be recoverable"
    )
if CANONICAL_TRUTH_HASH_COMPAT.get("unknown_hash_mismatch_fails_closed") is not True:
    raise RuntimeError("Unknown canonical truth hash mismatches must remain fail-closed")
if COMMERCIAL_SHIP_PROJECTION.get("bound") is not True:
    raise RuntimeError("Commercial ship presentation projection must be bound")
if COMMERCIAL_SHIP_PROJECTION.get("deployment_metric_detection_order_independent") is not True:
    raise RuntimeError("Deployment taxonomy projection must recognize canonical metric aliases regardless of word order")
if COMMERCIAL_SHIP_PROJECTION.get("final_assembled_source_pdf_preserved") is not True:
    raise RuntimeError("Commercial ship projection must preserve the final assembled source PDF")
if COMMERCIAL_SHIP_PROJECTION.get("toc_page_labels_and_bookmarks_rebuilt_after_compaction") is not True:
    raise RuntimeError("Pagination compaction must run before final TOC/page-label/bookmark generation")
if COMMERCIAL_SHIP_PROJECTION.get("canonical_truth_mutated") is not False:
    raise RuntimeError("Commercial ship presentation projection must not mutate canonical truth")
if COMMERCIAL_SHIP_PROJECTION.get("assessment_rerun") is not False:
    raise RuntimeError("Commercial ship presentation projection must not rerun the assessment")
if COMMERCIAL_SHIP_PROJECTION.get("human_review_required") is not True:
    raise RuntimeError("Commercial ship presentation projection must preserve human review")
if COMMERCIAL_SHIP_PROJECTION.get("client_delivery_allowed") is not False:
    raise RuntimeError("Commercial ship presentation projection must block unapproved delivery")
if SAME_RUN_LOCALE_REPORT.get("route_count") != 1:
    raise RuntimeError(
        "Same-run localized Comprehensive report route must be registered exactly once"
    )
if SAME_RUN_LOCALE_REPORT.get("pdf_route_count") != 1:
    raise RuntimeError(
        "Same-run localized Comprehensive PDF route must be registered exactly once"
    )
if SAME_RUN_LOCALE_REPORT.get("same_canonical_run") is not True:
    raise RuntimeError("Same-run localized report export must preserve one canonical run")
if SAME_RUN_LOCALE_REPORT.get("assessment_rerun") is not False:
    raise RuntimeError("Same-run localized report export must not rerun the assessment")
if SAME_RUN_LOCALE_REPORT.get("canonical_truth_preserved") is not True:
    raise RuntimeError("Same-run localized report export must preserve canonical truth")
if SAME_RUN_LOCALE_REPORT.get("human_review_required") is not True:
    raise RuntimeError("Same-run localized report export must preserve human review")
if SAME_RUN_LOCALE_REPORT.get("client_delivery_allowed") is not False:
    raise RuntimeError("Same-run localized report export must not authorize client delivery")


__all__ = [
    "app",
    "CANONICAL_TRUTH_HASH_COMPAT",
    "CANONICAL_TRUTH_HASH_COMPAT_VERSION",
    "COMMERCIAL_SHIP_PROJECTION",
    "PDF_ROUTE",
    "REPORT_REVIEW_INTEGRITY",
    "REPORT_REVIEW_INTEGRITY_VERSION",
    "ROUTE",
    "SAME_RUN_LOCALE_REPORT",
    "SAME_RUN_REPORT_VERSION",
    "VERSION",
]
