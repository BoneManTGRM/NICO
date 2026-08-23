from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
ROUTE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"
PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentPage.tsx"
SENTINEL = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentHydrationContract.tsx"
SPANISH_ROUTE = ROOT / "apps" / "web" / "app" / "es" / "assessment" / "page.tsx"
ACCEPTANCE = SCRIPTS / "unified_production_acceptance.py"


def load_acceptance_module():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("hydrated_acceptance_contract", ACCEPTANCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_routes_use_one_canonical_hydrated_assessment_page_with_locale_only_wrappers() -> None:
    route = ROUTE.read_text(encoding="utf-8")
    spanish_route = SPANISH_ROUTE.read_text(encoding="utf-8")

    assert 'import AssessmentPage from "./AssessmentPage"' in route
    assert '<AssessmentPage locale="en-US" />' in route
    assert "AssessmentWorkspace" not in route
    assert "AssessmentMetricDisplayV44" not in route
    assert 'import AssessmentPage from "../../assessment/AssessmentPage"' in spanish_route
    assert '<AssessmentPage locale="es-MX" />' in spanish_route
    assert "AssessmentWorkspace" not in spanish_route
    assert "useAssessmentRun" not in spanish_route


def test_assessment_page_binds_client_hydration_to_server_release_sha() -> None:
    page = PAGE.read_text(encoding="utf-8")
    sentinel = SENTINEL.read_text(encoding="utf-8")

    assert 'ASSESSMENT_CLIENT_COPY_CONTRACT = "expert-engagement-hydrated-v1"' in page
    assert "process.env.VERCEL_GIT_COMMIT_SHA" in page
    assert "<AssessmentHydrationContract" in page
    assert "releaseSha={exactReleaseSha}" in page
    assert "clientCopyContract={ASSESSMENT_CLIENT_COPY_CONTRACT}" in page

    assert 'data-workspace="assessment"' in sentinel
    assert 'data-engagement-type="comprehensive"' in sentinel
    assert 'data-canonical-assessment="strategic"' in sentinel
    assert "workspace.dataset.assessmentHydrated = \"true\"" in sentinel
    assert "workspace.dataset.assessmentClientCopyContract = clientCopyContract" in sentinel
    assert "workspace.dataset.assessmentClientReleaseSha" in sentinel
    assert "workspace.dataset.assessmentClientCopyVerified" in sentinel
    assert "Create engagement and capture repository snapshot" in sentinel
    assert "Crear encargo y capturar instantánea del repositorio" in sentinel
    assert "Run NICO Assessment" not in sentinel


def test_acceptance_waits_for_hydrated_release_contract_before_reading_action_copy() -> None:
    source = ACCEPTANCE.read_text(encoding="utf-8")

    assert 'CLIENT_COPY_CONTRACT = "expert-engagement-hydrated-v1"' in source
    assert "wait_for_hydrated_workspace" in source
    assert source.index("wait_for_hydrated_workspace(") < source.index("run_button = workspace.locator")
    assert 'service_workers="block"' in source
    assert '"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"' in source
    assert "nico_browser_probe" in source
    assert '"hydrated_release_verified": True' in source


def test_hydrated_workspace_match_requires_exact_sha_contract_and_copy() -> None:
    module = load_acceptance_module()
    expected_sha = "a" * 40
    valid = {
        "hydrated": "true",
        "client_copy_contract": module.CLIENT_COPY_CONTRACT,
        "client_release_sha": expected_sha,
        "client_copy_verified": "true",
        "observed_action": module.PUBLIC_RUN_LABELS["en"],
        "observed_heading": module.PUBLIC_HEADINGS["en"],
    }

    assert module.hydrated_workspace_matches(valid, locale="en", expected_sha=expected_sha) is True

    for field, replacement in (
        ("hydrated", "false"),
        ("client_copy_contract", "stale-contract"),
        ("client_release_sha", "b" * 40),
        ("client_copy_verified", "false"),
        ("observed_action", "Run NICO Assessment"),
        ("observed_heading", "Complete technical and strategic diligence"),
    ):
        invalid = dict(valid)
        invalid[field] = replacement
        assert module.hydrated_workspace_matches(invalid, locale="en", expected_sha=expected_sha) is False
