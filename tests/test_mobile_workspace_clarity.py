from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "web" / "app"
STYLES = ROOT / "apps" / "web" / "styles"


def test_assessment_service_descriptors_are_bilingual_and_contained() -> None:
    source = (APP / "WorkspaceClarityRepair.tsx").read_text(encoding="utf-8")
    css = (STYLES / "workspace-clarity.css").read_text(encoding="utf-8")

    assert 'express: "Línea base técnica"' in source
    assert 'comprehensive: "Diligencia técnica integral"' in source
    assert 'express: "Technical baseline"' in source
    assert 'comprehensive: "Technical diligence"' in source
    assert ".nico-service-choice-contained" in css
    assert "overflow: hidden !important" in css
    assert ".nico-service-detail" in css
    assert "position: static !important" in css
    assert "max-width: calc(100% - 1rem)" in css


def test_operator_only_workspaces_are_not_primary_navigation() -> None:
    source = (APP / "PrimaryNavigation.tsx").read_text(encoding="utf-8")

    primary = source.split("export const PRIMARY_SERVICES = [", 1)[1].split("] as const;", 1)[0]
    assert 'key: "run-job"' in primary
    assert 'key: "operations"' not in primary
    assert 'key: "retainer"' not in primary
    assert 'label: "Operations (Admin)"' in source
    assert 'label: "Retainer Ops"' in source
    assert 'label: "Operaciones (administrador)"' in source
    assert 'data-primary-service-count="1"' in source


def test_operations_and_retainer_explain_their_distinct_purpose() -> None:
    source = (APP / "WorkspaceClarityRepair.tsx").read_text(encoding="utf-8")

    assert "Owner-only deployment health" in source
    assert "NICO_ADMIN_TOKEN is a protected backend deployment secret" in source
    assert "This page is not required to run an assessment" in source
    assert "It does not replace or start the baseline assessment" in source
    assert "This is an operator workflow for ongoing service delivery" in source
    assert 'placeholder = "express_run_... or comprun_..."' in source


def test_home_redirect_masks_the_legacy_command_center_before_navigation() -> None:
    source = (APP / "AssessmentHomeRedirect.tsx").read_text(encoding="utf-8")
    css = (STYLES / "workspace-clarity.css").read_text(encoding="utf-8")

    assert "useLayoutEffect" in source
    assert 'window.location.replace("/assessment?tier=express#assessment")' in source
    assert 'className="nico-home-redirect"' in source
    assert ".nico-home-redirect" in css
    assert "z-index: 10000" in css
