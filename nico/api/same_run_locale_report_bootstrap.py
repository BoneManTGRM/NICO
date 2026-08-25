from __future__ import annotations

from nico.api.spanish_final_report_bootstrap import app as spanish_final_report_app
from nico.comprehensive_canonical_truth_hash_compat_v1 import (
    VERSION as CANONICAL_TRUTH_HASH_COMPAT_VERSION,
    install_canonical_truth_hash_compat,
)
from nico.comprehensive_commercial_ship_projection_v2 import (
    install_comprehensive_commercial_ship_projection_v2,
)
from nico.comprehensive_same_run_locale_report_v1 import (
    PDF_ROUTE,
    ROUTE,
    VERSION as SAME_RUN_REPORT_VERSION,
    install_same_run_locale_report,
)


VERSION = "nico.api.same_run_locale_report_bootstrap.v4"

app = spanish_final_report_app
CANONICAL_TRUTH_HASH_COMPAT = install_canonical_truth_hash_compat()
COMMERCIAL_SHIP_PROJECTION = install_comprehensive_commercial_ship_projection_v2()
SAME_RUN_LOCALE_REPORT = install_same_run_locale_report(app)

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
    "ROUTE",
    "SAME_RUN_LOCALE_REPORT",
    "SAME_RUN_REPORT_VERSION",
    "VERSION",
]
