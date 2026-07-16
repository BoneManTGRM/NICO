from __future__ import annotations

from fastapi import FastAPI

from nico import scanner_tool_runners, snapshot_scanner_worker
from nico.mid_live_status_api import register_mid_live_status_routes
from nico.mid_runtime_diagnostics import MID_RUNTIME_DIAGNOSTICS_PATH, mid_runtime_status, register_mid_runtime_diagnostics
from nico.mid_terminal_truth_patch import MID_STATUS_PATH, mid_status_endpoint
from nico.snapshot_scanner_heartbeat_patch import install_snapshot_scanner_heartbeat


def _app_with_mid_status_routes() -> FastAPI:
    app = FastAPI()
    register_mid_live_status_routes(app)
    app.add_api_route(MID_STATUS_PATH, mid_status_endpoint, methods=["POST"])
    return app


def test_mid_runtime_diagnostics_are_ok_only_when_live_route_canonical_status_and_worker_alias_are_wrapped(monkeypatch) -> None:
    app = _app_with_mid_status_routes()
    installed = install_snapshot_scanner_heartbeat()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    status = mid_runtime_status(app)

    assert installed["source_runner_binding_installed"] is True
    assert installed["snapshot_worker_binding_installed"] is True
    assert installed["snapshot_worker_module_alias_verified"] is True
    assert status["status"] == "ok"
    assert status["mid_live_status_route_count"] == 1
    assert status["mid_canonical_status_route_count"] == 1
    assert status["source_runner_heartbeat_binding"] is True
    assert status["snapshot_worker_heartbeat_binding"] is True
    assert status["heartbeat_bindings_identical"] is True
    assert status["snapshot_worker_module_alias_verified"] is True
    assert status["same_run_duplicate_prevention"] is True
    assert status["canonical_status_not_found_generic_500_possible"] is False
    assert status["pre_reconciliation_score_mismatch_is_terminal"] is False
    assert status["lossless_truth_normalization"] is True
    assert status["truth_fields_removed"] is False
    assert status["optional_evidence_changes_identity"] is True
    assert status["bounded_stale_approval_retry_count"] == 1
    assert status["same_run_stale_approval_repair"] is True
    assert status["live_status_mutates_storage"] is False
    assert status["live_status_projects_post_continuation"] is True
    assert status["post_status_performs_same_run_repair"] is True
    assert status["post_repair_requires_exact_tenant_scope"] is True
    assert status["post_repair_scope_validated_before_mutation"] is True
    assert status["wrong_scope_repair_possible"] is False
    assert status["cross_tenant_run_existence_disclosed"] is False
    assert status["same_run_repair_recaptures_repository"] is False
    assert status["same_run_repair_reruns_scanner"] is False
    assert status["same_run_repair_recomputes_score"] is False
    assert status["same_run_repair_creates_replacement_run"] is False
    assert status["generic_full_skipped_labels_exposed_for_mid"] is False
    assert status["dedicated_mid_artifact_stages_projected"] is True
    assert status["mid_scorecard_wording"] is True
    assert status["retained_mid_section_boundaries_reconciled"] is True
    assert status["non_verified_empty_section_uses_explicit_limitation"] is True
    assert status["verified_empty_section_still_blocked"] is True
    assert status["missing_evidence_converted_to_pass"] is False
    assert status["section_specific_quality_issue_labels"] is True
    assert status["duplicate_start_allowed"] is False
    assert status["client_delivery_allowed"] is False


def test_mid_runtime_diagnostics_fail_closed_when_worker_module_alias_uses_unwrapped_runner(monkeypatch) -> None:
    app = _app_with_mid_status_routes()
    install_snapshot_scanner_heartbeat()
    monkeypatch.delenv("DATABASE_URL", raising=False)

    class UnwrappedToolModule:
        @staticmethod
        def run_scanner_tool(*args, **kwargs):
            return {}

    monkeypatch.setattr(snapshot_scanner_worker, "tool_runners", UnwrappedToolModule())
    status = mid_runtime_status(app)

    assert status["status"] == "blocked"
    assert status["source_runner_heartbeat_binding"] is True
    assert status["snapshot_worker_heartbeat_binding"] is False
    assert status["heartbeat_bindings_identical"] is False
    assert status["snapshot_worker_module_alias_verified"] is False


def test_mid_runtime_diagnostics_route_registers_exactly_once() -> None:
    app = _app_with_mid_status_routes()
    install_snapshot_scanner_heartbeat()

    first = register_mid_runtime_diagnostics(app)
    second = register_mid_runtime_diagnostics(app)
    routes = [
        route
        for route in app.routes
        if getattr(route, "path", "") == MID_RUNTIME_DIAGNOSTICS_PATH
        and "GET" in (getattr(route, "methods", set()) or set())
    ]

    assert first["status"] in {"ok", "blocked"}
    assert second["status"] in {"ok", "blocked"}
    assert first["version"].startswith("nico.mid_runtime_diagnostics.v7")
    assert first["mid_stage_truth_version"].startswith("nico.mid_stage_truth.")
    assert first["mid_report_section_boundary_version"].startswith("nico.mid_report_section_boundary.")
    assert first["mid_quality_issue_display_version"].startswith("nico.mid_quality_issue_display.")
    assert first["mid_truth_identity_consistency_version"].startswith("nico.mid_truth_identity_consistency.")
    assert first["mid_truth_identity_transport_version"].startswith("nico.mid_truth_identity_transport.v3")
    assert len(routes) == 1
    assert scanner_tool_runners.run_scanner_tool is snapshot_scanner_worker.tool_runners.run_scanner_tool
