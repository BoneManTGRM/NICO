from __future__ import annotations

from nico.provider_locale_completion_state_v1 import (
    ExternalProviderEvidence,
    ProductionAcceptanceEvidence,
    build_provider_locale_completion_state,
)

SHA = "a" * 40


def _passing_production() -> ProductionAcceptanceEvidence:
    return ProductionAcceptanceEvidence(
        exact_current_main=True,
        vercel_deployment=True,
        railway_deployment=True,
        spanish_comprehensive_proof=True,
        ios_webkit_proof=True,
        mobile_restart_proof=True,
        two_service_acceptance=True,
        completion_bound_report=True,
        no_validated_p0_p1=True,
    )


def test_machine_state_records_priority1_engineering_parity_without_fabricating_live_proof() -> None:
    state = build_provider_locale_completion_state(current_main_sha=SHA)

    assert state["current_main_sha"] == SHA
    assert all(state["priority1_provider_engineering_parity"].values())
    assert not any(state["priority1_real_provider_integration"].values())
    assert state["real_provider_integration_required_now"] is False
    assert state["engineering_program_complete"] is True
    assert state["commercial_deadline_ready"] is False
    assert "exact_current_main_production_acceptance_incomplete" in state["blocking_gates"]
    assert state["human_review_required"] is True
    assert state["human_approval_completed"] is False
    assert state["client_delivery_allowed"] is False


def test_deadline_gate_can_pass_without_fabricating_unavailable_external_credentials() -> None:
    state = build_provider_locale_completion_state(
        current_main_sha=SHA,
        production=_passing_production(),
        external=ExternalProviderEvidence(authorized_real_credentials_available=False),
    )

    assert state["commercial_deadline_ready"] is True
    assert state["blocking_gates"] == []
    assert state["work_packages"]["N"]["status"] == "blocked_external"
    assert state["client_delivery_allowed"] is False


def test_authorized_real_provider_credentials_make_live_integration_a_required_gate() -> None:
    state = build_provider_locale_completion_state(
        current_main_sha=SHA,
        production=_passing_production(),
        external=ExternalProviderEvidence(
            authorized_real_credentials_available=True,
            gitlab_real_integration=True,
            bitbucket_real_integration=False,
            azure_real_integration=True,
        ),
    )

    assert state["commercial_deadline_ready"] is False
    assert "authorized_real_provider_integration_incomplete" in state["blocking_gates"]


def test_priority2_external_infrastructure_is_never_synthesized() -> None:
    unavailable = build_provider_locale_completion_state(
        current_main_sha=SHA,
        production=_passing_production(),
    )
    assert unavailable["work_packages"]["N"]["status"] == "blocked_external"

    available = build_provider_locale_completion_state(
        current_main_sha=SHA,
        production=_passing_production(),
        external=ExternalProviderEvidence(priority2_authorized_infrastructure_available=True),
    )
    assert available["commercial_deadline_ready"] is False
    assert "priority2_authorized_infrastructure_requires_validation" in available["blocking_gates"]


def test_invalid_or_non_exact_sha_fails_closed() -> None:
    for value in ("", "abc", "g" * 40, "a" * 39, "a" * 41):
        try:
            build_provider_locale_completion_state(current_main_sha=value)
        except ValueError as exc:
            assert str(exc) == "exact_current_main_sha_required"
        else:
            raise AssertionError(value)
