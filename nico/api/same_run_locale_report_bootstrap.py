from __future__ import annotations

from nico.api.spanish_final_report_bootstrap import app as spanish_final_report_app
from nico.comprehensive_same_run_locale_report_v1 import (
    ROUTE,
    VERSION as SAME_RUN_REPORT_VERSION,
    install_same_run_locale_report,
)


VERSION = "nico.api.same_run_locale_report_bootstrap.v1"

app = spanish_final_report_app
SAME_RUN_LOCALE_REPORT = install_same_run_locale_report(app)

if SAME_RUN_LOCALE_REPORT.get("route_count") != 1:
    raise RuntimeError(
        "Same-run localized Comprehensive report route must be registered exactly once"
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
    "ROUTE",
    "SAME_RUN_LOCALE_REPORT",
    "SAME_RUN_REPORT_VERSION",
    "VERSION",
]
