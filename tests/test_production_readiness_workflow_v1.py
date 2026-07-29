from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"
DOC = ROOT / "docs" / "production-assessment-readiness.md"


def test_workflow_fails_before_browser_install_when_persistence_is_unsafe() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    readiness = source.index("- name: Verify production assessment readiness")
    browser = source.index("- name: Install pinned browser proof dependencies")
    live_run = source.index("- name: Run two consecutive authoritative strategic assessment passes")

    assert readiness < browser < live_run
    assert "/api/nico/diagnostics/comprehensive-runtime" in source
    assert 'runtime_status != "ready"' in source
    assert "not replacement_safe" in source
    assert "Configure Postgres or a verified persistent volume" in source


def test_deployment_runbook_preserves_fail_closed_persistence() -> None:
    source = DOC.read_text(encoding="utf-8")

    assert "NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE=true" in source
    assert "${{Postgres.DATABASE_URL}}" in source
    assert "survives_container_replacement_verified: true" in source
    assert "comprehensive_sqlite_persistent_volume_required" in source
    assert "same incomplete run" in source
