from __future__ import annotations


def test_phase1_candidate_intelligence_is_bound_in_production_app() -> None:
    from nico.api.production import app

    status = dict(getattr(app.state, "nico_native_comprehensive_provider_status", {}) or {})
    assert status["candidate_lineage_migration_bound"] is True
    assert status["candidate_technical_triage_bound"] is True
    assert status["fresh_technical_triage_new_or_changed"] is True
    assert status["review_by_exception_routing_bound"] is True
    assert status["osv_scanner_context_bound"] is True
    assert status["human_approval_may_carry_forward"] is False
    assert status["client_delivery_allowed"] is False
