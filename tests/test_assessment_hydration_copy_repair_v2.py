from __future__ import annotations

from pathlib import Path


SENTINEL = Path("apps/web/app/assessment/AssessmentHydrationContract.tsx")
PAGE = Path("apps/web/app/assessment/AssessmentPage.tsx")


def test_hydration_contract_repairs_stale_idle_copy_without_touching_live_progress() -> None:
    source = SENTINEL.read_text(encoding="utf-8")

    assert "function replaceText" in source
    assert 'workspace.querySelector(\'[data-assessment-run-state="true"]\')' in source
    assert "idleEngagement = authorization?.disabled !== true" in source
    assert "if (!runStateExists && idleEngagement)" in source
    assert "replaceText(action, expected.action)" in source
    assert 'action.setAttribute("aria-label", expected.action)' in source
    assert "replaceText(heading, expected.heading)" in source
    assert 'workspace.dataset.assessmentClientCopyRepaired = repaired ? "true" : "false"' in source
    assert "workspace.dataset.assessmentClientOriginalAction" in source
    assert "workspace.dataset.assessmentClientOriginalHeading" in source


def test_hydration_contract_observes_late_client_settling_and_runs_after_workspace() -> None:
    source = SENTINEL.read_text(encoding="utf-8")
    page = PAGE.read_text(encoding="utf-8")

    assert "observer.observe(document.documentElement" in source
    assert "observer?.disconnect();\n        observer = null" not in source
    assert page.index("<AssessmentWorkspace") < page.index("<AssessmentHydrationContract")


def test_hydration_contract_keeps_bilingual_authoritative_copy() -> None:
    source = SENTINEL.read_text(encoding="utf-8")

    assert "Create engagement and capture repository snapshot" in source
    assert "Create assessment engagement" in source
    assert "Crear encargo y capturar instantánea del repositorio" in source
    assert "Crear encargo de evaluación" in source
