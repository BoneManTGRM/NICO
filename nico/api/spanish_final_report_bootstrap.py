from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_final_report_process_isolation_hardening_v2 import (
    install_comprehensive_final_report_process_isolation_hardening_v2,
)
from nico.comprehensive_final_report_process_isolation_v1 import (
    install_comprehensive_final_report_process_isolation_v1,
)
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
)

VERSION = "nico.api.spanish_final_report_bootstrap.v3"

# Install after terminal authority and every report/language compatibility layer so
# the live v88/v89/v90 Spanish translation surfaces all share the same bounded cache.
# This changes execution cost only; exact report truth, evidence, scoring, human review,
# and blocked pre-approval client delivery remain owned by the existing pipeline.
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
        "Spanish final-report runtime cache did not install: "
        f"{SPANISH_FINAL_REPORT_RUNTIME_CACHE}"
    )
if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("bound") is not True:
    raise RuntimeError("Spanish final-report runtime cache is not bound")
if (
    SPANISH_FINAL_REPORT_RUNTIME_CACHE.get(
        "preflight_translation_results_reused_by_renderer"
    )
    is not True
):
    raise RuntimeError("Spanish preflight translations are not reused by the renderer")
if (
    SPANISH_FINAL_REPORT_RUNTIME_CACHE.get(
        "markdown_pdf_localized_inputs_reused_for_same_canonical_object"
    )
    is not True
):
    raise RuntimeError("Spanish Markdown/PDF localized inputs are not reused")
if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("human_review_required") is not True:
    raise RuntimeError("Spanish final-report cache must preserve human review")
if SPANISH_FINAL_REPORT_RUNTIME_CACHE.get("client_delivery_allowed") is not False:
    raise RuntimeError("Spanish final-report cache must block unapproved client delivery")

# Final-report publication is now executed in a killable subprocess rather than an
# unkillable in-process renderer thread. Install after localization so the child imports
# the same authoritative Spanish/terminal bootstrap before rendering. The runtime patch
# also projects durable queue/render heartbeat state to the browser.
FINAL_REPORT_PROCESS_ISOLATION = install_comprehensive_final_report_process_isolation_v1(app)
setattr(
    app.state,
    "nico_final_report_process_isolation",
    FINAL_REPORT_PROCESS_ISOLATION,
)

if FINAL_REPORT_PROCESS_ISOLATION.get("bound") is not True:
    raise RuntimeError(
        "Final-report process isolation did not install: "
        f"{FINAL_REPORT_PROCESS_ISOLATION}"
    )
for required in (
    "isolated_subprocess_worker",
    "hard_termination_supported",
    "recovery_waits_for_worker_termination",
    "logical_capacity_released_only_after_worker_exit",
    "active_stage_execution_projection",
):
    if FINAL_REPORT_PROCESS_ISOLATION.get(required) is not True:
        raise RuntimeError(f"Final-report process isolation missing contract: {required}")
if FINAL_REPORT_PROCESS_ISOLATION.get("human_review_required") is not True:
    raise RuntimeError("Final-report process isolation must preserve human review")
if FINAL_REPORT_PROCESS_ISOLATION.get("client_delivery_allowed") is not False:
    raise RuntimeError("Final-report process isolation must block unapproved client delivery")

# Strengthen the physical-lifetime contract after v1 has installed the isolated worker.
# If OS termination cannot be confirmed, the single renderer slot remains reserved and
# no recovery renderer is allowed to overlap the still-live process.
FINAL_REPORT_PROCESS_ISOLATION_HARDENING = (
    install_comprehensive_final_report_process_isolation_hardening_v2(app)
)
setattr(
    app.state,
    "nico_final_report_process_isolation_hardening",
    FINAL_REPORT_PROCESS_ISOLATION_HARDENING,
)

if FINAL_REPORT_PROCESS_ISOLATION_HARDENING.get("bound") is not True:
    raise RuntimeError(
        "Final-report process isolation hardening did not install: "
        f"{FINAL_REPORT_PROCESS_ISOLATION_HARDENING}"
    )
for required in (
    "physical_worker_exit_required_before_capacity_release",
    "failed_termination_keeps_renderer_capacity_reserved",
    "process_group_descendant_cleanup_required",
    "private_transport_permissions_required",
):
    if FINAL_REPORT_PROCESS_ISOLATION_HARDENING.get(required) is not True:
        raise RuntimeError(
            f"Final-report process isolation hardening missing contract: {required}"
        )
if FINAL_REPORT_PROCESS_ISOLATION_HARDENING.get("human_review_required") is not True:
    raise RuntimeError("Final-report process isolation hardening must preserve human review")
if FINAL_REPORT_PROCESS_ISOLATION_HARDENING.get("client_delivery_allowed") is not False:
    raise RuntimeError(
        "Final-report process isolation hardening must block unapproved client delivery"
    )


__all__ = [
    "FINAL_REPORT_PROCESS_ISOLATION",
    "FINAL_REPORT_PROCESS_ISOLATION_HARDENING",
    "SPANISH_FINAL_REPORT_RUNTIME_CACHE",
    "VERSION",
    "app",
]
