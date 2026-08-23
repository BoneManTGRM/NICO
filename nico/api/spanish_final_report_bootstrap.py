from __future__ import annotations

from nico.api.terminal_authority_bootstrap import app
from nico.comprehensive_final_report_process_isolation_hardening_v2 import (
    install_comprehensive_final_report_process_isolation_hardening_v2,
)
from nico.comprehensive_final_report_process_isolation_v1 import (
    install_comprehensive_final_report_process_isolation_v1,
)
from nico.comprehensive_production_proof_lifecycle_v1 import (
    install_comprehensive_production_proof_lifecycle_v1,
)
from nico.comprehensive_spanish_assessment_scope_v97 import (
    install_comprehensive_spanish_assessment_scope_v97,
)
from nico.comprehensive_spanish_final_report_runtime_cache_v94 import (
    install_comprehensive_spanish_final_report_runtime_cache_v94,
)
from nico.provider_rollout_control_v1 import install_provider_rollout_routes

VERSION = "nico.api.spanish_final_report_bootstrap.v6"

# Bind the exact production assessment-scope presentation contract before the parent
# process installs the shared Spanish render cache. This keeps the parent preflight and
# the isolated final-report worker on the same es-MX vocabulary without changing any
# canonical evidence, scoring, human-review, or client-delivery authority.
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
        "Spanish assessment-scope contract did not install: "
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
    raise RuntimeError("Spanish production assessment scope is not translatable")
if (
    SPANISH_ASSESSMENT_SCOPE.get(
        "unknown_assessment_scope_contract_unregistered"
    )
    is not True
):
    raise RuntimeError("Spanish assessment-scope contract registered unapproved prose")

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

# Final-report publication executes in a killable subprocess. Install after
# localization so the child imports the same authoritative Spanish/terminal bootstrap.
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

# Require confirmed physical process exit before renderer capacity can be reused. This
# must be installed before proof cancellation so cancelled synthetic proof runs inherit
# the same no-overlap renderer lifecycle as normal production assessments.
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

# Synthetic release acceptance uses a reserved server-side scope. Install this last so
# proof cancellation and stale-proof reaping use the fully hardened renderer lifecycle.
PRODUCTION_PROOF_LIFECYCLE = install_comprehensive_production_proof_lifecycle_v1(app)
setattr(
    app.state,
    "nico_comprehensive_production_proof_lifecycle",
    PRODUCTION_PROOF_LIFECYCLE,
)
if PRODUCTION_PROOF_LIFECYCLE.get("bound") is not True:
    raise RuntimeError(
        "Comprehensive production-proof lifecycle did not install: "
        f"{PRODUCTION_PROOF_LIFECYCLE}"
    )
for required in (
    "reserved_proof_scope",
    "prior_proof_reaper_bound",
    "proof_cancel_route_bound",
    "client_run_scope_untouched",
):
    if PRODUCTION_PROOF_LIFECYCLE.get(required) is not True:
        raise RuntimeError(f"Production-proof lifecycle missing contract: {required}")
if PRODUCTION_PROOF_LIFECYCLE.get("human_review_required") is not True:
    raise RuntimeError("Production-proof lifecycle must preserve human review")
if PRODUCTION_PROOF_LIFECYCLE.get("client_delivery_allowed") is not False:
    raise RuntimeError("Production-proof lifecycle must block client delivery")

# The hosted-provider rollout authority is mounted on the same final production app.
# It exposes capability truth and preflight only; raw credentials remain server-side,
# support maturity cannot be upgraded by API input, and client delivery stays blocked.
PROVIDER_ROLLOUT_CONTROL = install_provider_rollout_routes(app)
setattr(
    app.state,
    "nico_provider_rollout_control",
    PROVIDER_ROLLOUT_CONTROL,
)
if PROVIDER_ROLLOUT_CONTROL.get("status") != "installed":
    raise RuntimeError(
        "Provider rollout control did not install: "
        f"{PROVIDER_ROLLOUT_CONTROL}"
    )
if PROVIDER_ROLLOUT_CONTROL.get("provider_count") != 4:
    raise RuntimeError("Provider rollout control must declare four hosted providers")
if any(
    count != 1
    for count in PROVIDER_ROLLOUT_CONTROL.get("route_counts", {}).values()
):
    raise RuntimeError("Provider rollout control routes are missing or duplicated")
if PROVIDER_ROLLOUT_CONTROL.get("credentials_server_side_only") is not True:
    raise RuntimeError("Provider rollout control must keep credentials server-side")
if PROVIDER_ROLLOUT_CONTROL.get("human_review_required") is not True:
    raise RuntimeError("Provider rollout control must preserve human review")
if PROVIDER_ROLLOUT_CONTROL.get("client_delivery_allowed") is not False:
    raise RuntimeError("Provider rollout control must block client delivery")


__all__ = [
    "FINAL_REPORT_PROCESS_ISOLATION",
    "FINAL_REPORT_PROCESS_ISOLATION_HARDENING",
    "PRODUCTION_PROOF_LIFECYCLE",
    "PROVIDER_ROLLOUT_CONTROL",
    "SPANISH_ASSESSMENT_SCOPE",
    "SPANISH_FINAL_REPORT_RUNTIME_CACHE",
    "VERSION",
    "app",
]
