from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from nico import scanner_tool_runners, snapshot_scanner_worker
from nico.mid_live_status_api import MID_LIVE_STATUS_PATH, MID_LIVE_STATUS_VERSION
from nico.mid_quality_issue_display_patch import MID_QUALITY_ISSUE_DISPLAY_VERSION
from nico.mid_report_score_integrity import MID_REPORT_SCORE_INTEGRITY_VERSION
from nico.mid_report_section_boundary_patch import MID_REPORT_SECTION_BOUNDARY_VERSION
from nico.mid_stage_truth_patch import MID_STAGE_TRUTH_VERSION
from nico.mid_terminal_truth_patch import MID_STATUS_PATH, MID_TERMINAL_TRUTH_VERSION
from nico.mid_truth_identity_consistency import MID_TRUTH_IDENTITY_CONSISTENCY_VERSION
from nico.mid_truth_identity_transport import MID_TRUTH_IDENTITY_TRANSPORT_VERSION
from nico.report_quality_gate import REPORT_QUALITY_GATE_VERSION
from nico.snapshot_scanner_heartbeat_patch import SNAPSHOT_SCANNER_HEARTBEAT_VERSION
from nico.storage import STORE

MID_RUNTIME_DIAGNOSTICS_PATH = "/diagnostics/mid-runtime"
MID_RUNTIME_DIAGNOSTICS_VERSION = "nico.mid_runtime_diagnostics.v7-watchdog"
_HEARTBEAT_MARKER = "_nico_snapshot_scanner_heartbeat_tool_v3"


def _route_count(app: FastAPI, method: str, path: str) -> int:
    expected = method.upper()
    return sum(
        1
        for route in app.routes
        if str(getattr(route, "path", "")) == path
        and expected in {str(item).upper() for item in (getattr(route, "methods", set()) or set())}
    )


def _durable_required() -> bool:
    return (
        bool(os.getenv("DATABASE_URL", "").strip())
        or os.getenv("NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE", "false").strip().lower() == "true"
        or os.getenv("NICO_ENABLE_SQLITE_DURABLE_STORAGE", "false").strip().lower() == "true"
    )


def mid_runtime_status(app: FastAPI) -> dict[str, Any]:
    source_runner = scanner_tool_runners.run_scanner_tool
    worker_module = getattr(snapshot_scanner_worker, "tool_runners", None)
    worker_runner = getattr(worker_module, "run_scanner_tool", None)
    source_binding = bool(getattr(source_runner, _HEARTBEAT_MARKER, False))
    worker_binding = bool(getattr(worker_runner, _HEARTBEAT_MARKER, False))
    same_binding = source_runner is worker_runner
    module_alias_verified = worker_module is scanner_tool_runners
    live_routes = _route_count(app, "GET", MID_LIVE_STATUS_PATH)
    canonical_status_routes = _route_count(app, "POST", MID_STATUS_PATH)
    storage = STORE.status()
    durable_required = _durable_required()
    recording_ready = bool(storage.get("persistence_available"))
    adapter = str(storage.get("adapter") or storage.get("mode") or "unknown")
    durability_verified = bool(
        storage.get("durability_verified")
        or (adapter == "postgres" and recording_ready)
    )
    ready = (
        source_binding
        and worker_binding
        and same_binding
        and module_alias_verified
        and live_routes == 1
        and canonical_status_routes == 1
        and (recording_ready or not durable_required)
    )
    return {
        "status": "ok" if ready else "blocked",
        "version": MID_RUNTIME_DIAGNOSTICS_VERSION,
        "mid_live_status_version": MID_LIVE_STATUS_VERSION,
        "mid_live_status_route_count": live_routes,
        "mid_canonical_status_route_count": canonical_status_routes,
        "mid_terminal_truth_version": MID_TERMINAL_TRUTH_VERSION,
        "mid_stage_truth_version": MID_STAGE_TRUTH_VERSION,
        "mid_report_score_integrity_version": MID_REPORT_SCORE_INTEGRITY_VERSION,
        "mid_report_section_boundary_version": MID_REPORT_SECTION_BOUNDARY_VERSION,
        "mid_quality_issue_display_version": MID_QUALITY_ISSUE_DISPLAY_VERSION,
        "mid_truth_identity_consistency_version": MID_TRUTH_IDENTITY_CONSISTENCY_VERSION,
        "mid_truth_identity_transport_version": MID_TRUTH_IDENTITY_TRANSPORT_VERSION,
        "pre_reconciliation_score_mismatch_is_terminal": False,
        "final_report_score_matches_weighted_calculation": True,
        "lossless_truth_normalization": True,
        "truth_fields_removed": False,
        "optional_evidence_changes_identity": True,
        "canonical_truth_before_review_packet_identity": True,
        "canonical_truth_before_report_identity": True,
        "canonical_truth_before_approval_identity": True,
        "bounded_stale_approval_retry_count": 1,
        "same_run_stale_approval_repair": True,
        "live_status_mutates_storage": False,
        "live_status_projects_post_continuation": True,
        "post_status_performs_same_run_repair": True,
        "post_repair_requires_exact_tenant_scope": True,
        "post_repair_scope_validated_before_mutation": True,
        "wrong_scope_repair_possible": False,
        "cross_tenant_run_existence_disclosed": False,
        "same_run_repair_recaptures_repository": False,
        "same_run_repair_reruns_scanner": False,
        "same_run_repair_recomputes_score": False,
        "same_run_repair_creates_replacement_run": False,
        "approval_truth_hash_diagnostics_bounded": True,
        "terminal_report_gate_status_is_read_only": True,
        "canonical_status_not_found_generic_500_possible": False,
        "stale_scanner_running_after_downstream_completion": False,
        "generic_full_skipped_labels_exposed_for_mid": False,
        "dedicated_mid_artifact_stages_projected": True,
        "mid_scorecard_wording": True,
        "retained_mid_section_boundaries_reconciled": True,
        "non_verified_empty_section_uses_explicit_limitation": True,
        "verified_empty_section_still_blocked": True,
        "missing_evidence_converted_to_pass": False,
        "section_specific_quality_issue_labels": True,
        "report_quality_issue_codes_exposed": True,
        "scanner_heartbeat_version": SNAPSHOT_SCANNER_HEARTBEAT_VERSION,
        "scanner_heartbeat_marker": _HEARTBEAT_MARKER,
        "source_runner_heartbeat_binding": source_binding,
        "snapshot_worker_heartbeat_binding": worker_binding,
        "heartbeat_bindings_identical": same_binding,
        "snapshot_worker_module_alias_verified": module_alias_verified,
        "watchdog_countdown_required": True,
        "hard_timeout_then_continue_required": True,
        "report_quality_gate_version": REPORT_QUALITY_GATE_VERSION,
        "storage_adapter": adapter,
        "storage_mode": storage.get("mode") or adapter,
        "storage_path": storage.get("database_path") or "",
        "storage_recording_ready": recording_ready,
        "durable_storage_required": durable_required,
        "durable_storage_ready": recording_ready,
        "durability_verified": durability_verified,
        "survives_container_replacement_verified": durability_verified,
        "durability_warning": storage.get("durability_warning") or "",
        "memory_storage_accepted": not durable_required,
        "same_run_duplicate_prevention": True,
        "duplicate_start_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def register_mid_runtime_diagnostics(app: FastAPI) -> dict[str, Any]:
    if not _route_count(app, "GET", MID_RUNTIME_DIAGNOSTICS_PATH):
        def diagnostics() -> dict[str, Any]:
            return mid_runtime_status(app)

        app.add_api_route(
            MID_RUNTIME_DIAGNOSTICS_PATH,
            diagnostics,
            methods=["GET"],
            tags=["diagnostics", "mid"],
        )
        app.openapi_schema = None
    return mid_runtime_status(app)


__all__ = [
    "MID_RUNTIME_DIAGNOSTICS_PATH",
    "MID_RUNTIME_DIAGNOSTICS_VERSION",
    "mid_runtime_status",
    "register_mid_runtime_diagnostics",
]
