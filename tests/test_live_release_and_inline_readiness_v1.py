from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
COPY = ROOT / "apps" / "web" / "app" / "assessment" / "assessmentCopy.ts"
RELEASE = ROOT / "apps" / "web" / "app" / "api" / "release" / "route.ts"
INLINE_STYLE = ROOT / "apps" / "web" / "app" / "assessment" / "assessment-inline-readiness.css"
BOOTSTRAP = ROOT / "nico" / "comprehensive_production_bootstrap.py"


def test_no_run_readiness_failure_stays_inline_and_does_not_create_status_workspace() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "const preflightIssue = issue && !issue.runCreated ? issue : null" in workspace
    assert "const runIssue = issue && issue.runCreated ? issue : null" in workspace
    assert "const showStatePanel = Boolean(result?.run_id)" in workspace
    assert 'data-assessment-no-run-issue="true"' in workspace
    assert 'data-assessment-run-state="true"' in workspace
    assert "{showStatePanel ? <section" in workspace
    assert "preflightIssue.message" in workspace
    assert "preflightIssue ? <div" in workspace
    assert "preflightIssue.runCreated ?" not in workspace


def test_current_engagement_copy_is_machine_verifiable_and_old_action_is_absent() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    copy = COPY.read_text(encoding="utf-8")

    assert 'data-assessment-copy-contract="expert-engagement-v2"' in workspace
    assert 'data-assessment-action-copy="create-engagement-v2"' in workspace
    assert 'run: "Create engagement and capture repository snapshot"' in copy
    assert 'run: "Run NICO Assessment"' not in copy


def test_inline_readiness_presentation_is_compact_on_mobile() -> None:
    styles = INLINE_STYLE.read_text(encoding="utf-8")

    assert '[data-assessment-no-run-issue="true"]' in styles
    assert "box-shadow: none" in styles
    assert "font-size: 15px" in styles
    assert "@media (max-width: 760px)" in styles
    assert "min-height: 44px" in styles


def test_frontend_exposes_uncached_exact_release_identity() -> None:
    route = RELEASE.read_text(encoding="utf-8")

    assert 'const UI_CONTRACT = "expert-engagement-v2"' in route
    assert "process.env.VERCEL_GIT_COMMIT_SHA" in route
    assert "process.env.NICO_RELEASE_SHA" in route
    assert '"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"' in route
    assert "release_sha: releaseSha()" in route
    assert "ui_contract: UI_CONTRACT" in route


def test_sqlite_mount_detection_remains_fail_closed() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")

    assert "def _mounted_filesystems()" in source
    assert "def _detected_durable_mount(path: Path)" in source
    assert "def _sqlite_persistence_proof(path: Path)" in source
    assert '"overlay"' in source
    assert '"tmpfs"' in source
    assert 'return False, "unverified_container_filesystem"' in source
    assert 'persistence_proof_source' in source
