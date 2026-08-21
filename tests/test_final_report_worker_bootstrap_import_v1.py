from __future__ import annotations


def test_renderer_bootstrap_imports_with_only_renderer_owned_runtime() -> None:
    from nico.api import final_report_worker_bootstrap as worker

    state = worker.FINAL_REPORT_WORKER_RUNTIME
    assert state["status"] == "ready"
    assert state["same_terminal_report_authority_as_production"] is True
    assert state["spanish_final_report_runtime_cache_bound"] is True
    assert state["process_isolation_owned_by_parent"] is True
    assert state["physical_exit_hardening_owned_by_parent"] is True
    assert state["production_proof_lifecycle_owned_by_parent"] is True
    assert state["nested_renderer_orchestration_installed"] is False
    assert state["human_review_required"] is True
    assert state["client_delivery_allowed"] is False

    cache = worker.SPANISH_FINAL_REPORT_RUNTIME_CACHE
    assert cache["bound"] is True
    assert cache["preflight_translation_results_reused_by_renderer"] is True
    assert cache["markdown_pdf_localized_inputs_reused_for_same_canonical_object"] is True

    # The isolated child must not reinstall the parent web-process lifecycle. Those
    # state entries are added only by nico.api.spanish_final_report_bootstrap.
    assert not hasattr(worker.app.state, "nico_final_report_process_isolation")
    assert not hasattr(worker.app.state, "nico_final_report_process_isolation_hardening")
    assert not hasattr(worker.app.state, "nico_comprehensive_production_proof_lifecycle")
