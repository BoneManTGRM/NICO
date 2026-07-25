from __future__ import annotations

from pathlib import Path


PROXY = Path("apps/web/app/api/nico/[...path]/route.ts")
WORKSPACE = Path("apps/web/app/assessment/useAssessmentRun.ts")


def test_proxy_rejects_conflicting_backend_origins_instead_of_cross_store_failover() -> None:
    source = PROXY.read_text(encoding="utf-8")

    assert "assessment_backend_configuration_conflict" in source
    assert "values.length > 1" in source
    assert "for (const backend of backends)" not in source
    assert "const backend = resolution.backend" in source
    assert "A run cannot safely fail over between independent stores" in source


def test_workspace_requires_container_replacement_safe_storage_before_intake() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "verifyRuntimePersistence" in source
    assert '"/diagnostics/comprehensive-runtime"' in source
    assert "survives_container_replacement_verified" in source
    assert source.index("await verifyRuntimePersistence()") < source.index('"/assessment/comprehensive-intake"')
