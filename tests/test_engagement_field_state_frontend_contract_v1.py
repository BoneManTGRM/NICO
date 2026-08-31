from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps/web/app/assessment"


def source(name: str) -> str:
    return (ASSESSMENT / name).read_text(encoding="utf-8")


def test_all_five_fields_have_explicit_state_controls_in_desktop_and_mobile() -> None:
    workspace = source("AssessmentWorkspace.tsx")
    strategic = source("StrategicEvidenceForm.tsx")
    controls = source("EngagementFieldStateControls.tsx")

    for field in (
        "client_name",
        "project_name",
        "primary_technical_contact",
        "access_method",
        "authorized_scope",
    ):
        assert field in workspace + strategic
    assert "data-engagement-field" in workspace
    assert "data-engagement-field" in strategic
    assert "engagementFieldStates[field].state" in strategic
    assert "isEngagementFieldUnavailable" in workspace
    assert "isEngagementFieldUnavailable" in strategic
    for english, spanish in (
        ("Exclude from scope", "Excluir del alcance"),
        ("Excluded from scope", "Excluido del alcance"),
        ("Not supplied", "No proporcionado"),
        ("Not applicable", "No aplica"),
    ):
        assert english in controls + source("engagementFieldState.ts")
        assert spanish in controls + source("engagementFieldState.ts")


def test_intake_and_recovery_carry_structured_states_without_starting_again() -> None:
    hook = source("useAssessmentRun.ts")
    persistence = source("assessmentRunPersistence.ts")
    bridge = source("AssessmentIntakeDomSnapshotBridge.tsx")

    assert "engagement_field_states:" in hook
    assert "engagement.field_states" in hook
    assert "engagementFieldStates: states" in hook
    assert "engagementFieldStates: EngagementFieldStates" in persistence
    assert "normalizeEngagementFieldStates" in persistence
    assert "payload.engagement_field_states = fieldStates" in bridge
    assert "if (!(wrapper instanceof HTMLElement)) continue;" in bridge
    assert "Object.entries(snapshot.engagementStates)" in bridge
    assert "state === \"excluded_from_scope\" || state === \"not_applicable\"" in bridge
    assert hook.count('"/assessment/comprehensive-intake"') == 1
    resume = hook.split("async function resumePersistedRun", 1)[1].split(
        "async function run", 1
    )[0]
    assert 'method: "GET"' in resume
    assert '"/assessment/comprehensive-intake"' not in resume


def test_one_frontend_mapper_owns_exact_english_and_mexican_spanish_states() -> None:
    state = source("engagementFieldState.ts")
    expected = (
        "Verified",
        "Verificado",
        "Supplied — independent verification pending",
        "Proporcionado — verificación independiente pendiente",
        "Not supplied",
        "No proporcionado",
        "Excluded from scope",
        "Excluido del alcance",
        "Not applicable",
        "No aplica",
    )
    for value in expected:
        assert value in state
