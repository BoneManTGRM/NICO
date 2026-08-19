from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECOVERY_PAGE = ROOT / "apps/web/app/operations/recovery/page.tsx"
COMPREHENSIVE_PANEL = ROOT / "apps/web/app/operations/ComprehensiveRecoveryPanel.tsx"
FAILURE_PANEL = ROOT / "apps/web/app/AssessmentFailureEvidencePanel.tsx"


def test_failure_cta_routes_exact_comprehensive_run_into_recovery_control() -> None:
    failure_source = FAILURE_PANEL.read_text(encoding="utf-8")
    page_source = RECOVERY_PAGE.read_text(encoding="utf-8")

    assert "assessment_type=${encodeURIComponent(failure.assessment_type || \"comprehensive\")}" in failure_source
    assert 'runId.startsWith("comprun_")' in page_source
    assert "ComprehensiveRecoveryPanel" in page_source
    assert "comprehensiveTarget ? <ComprehensiveRecoveryPanel" in page_source
    assert "targetRunId={targetRunId}" in page_source
    assert '(!comprehensiveTarget && !adminToken.trim())' in page_source
    assert 'disabled={comprehensiveTarget}' in page_source
    assert "not required for Comprehensive recovery" in page_source


def test_comprehensive_recovery_reuses_exact_run_and_bounded_continue() -> None:
    source = COMPREHENSIVE_PANEL.read_text(encoding="utf-8")

    assert "data-comprehensive-recovery=\"true\"" in source
    assert "This control never creates a replacement run" in source
    assert "Resume same Comprehensive run ID" in source
    assert "`${apiUrl}/assessment/comprehensive-run/${encodeURIComponent(targetRunId)}`" in source
    assert "`${apiUrl}/assessment/comprehensive-run/${encodeURIComponent(targetRunId)}/continue`" in source
    assert "JSON.stringify({max_stages: 1})" in source
    assert 'String(exact.run_id || "") !== targetRunId' in source
    assert 'String(recovered.run_id || "") !== targetRunId' in source
    assert 'target.searchParams.set("run_id", targetRunId)' in source
    assert 'target.searchParams.set("tier", "comprehensive")' in source
    assert "recovered.terminal === true" in source
    assert "Preserved evidence was not converted into a passing result" in source
    assert "X-NICO-Admin-Token" not in source
    assert "No operator token is required for this bounded Comprehensive recovery" in source
    assert 'disabled={loading || !recoverable(run)}' in source
