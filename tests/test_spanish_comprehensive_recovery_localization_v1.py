from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FAILURE_PANEL = ROOT / "apps/web/app/AssessmentFailureEvidencePanel.tsx"
RECOVERY_PAGE = ROOT / "apps/web/app/operations/recovery/page.tsx"
COMPREHENSIVE_PANEL = ROOT / "apps/web/app/operations/ComprehensiveRecoveryPanel.tsx"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _spanish_copy(source: str) -> str:
    return source.split("const copy = spanish ? {", 1)[1].split("} : {", 1)[0]


def test_spanish_failure_recovery_link_retains_locale_and_exact_run_identity() -> None:
    source = _source(FAILURE_PANEL)

    assert "run_id=${encodeURIComponent(failure.run_id)}" in source
    assert "assessment_type=${encodeURIComponent(failure.assessment_type" in source
    assert '${spanish ? "&lang=es-MX" : ""}' in source
    assert 'window.location.assign(recoveryHref)' in source
    assert "failure.run_id" in source
    assert "replace(failure.run_id" not in source


def test_recovery_locale_is_query_authoritative_and_survives_refresh() -> None:
    source = _source(RECOVERY_PAGE)

    assert 'params.get("lang")' in source
    assert 'toLowerCase() === "es-mx" ? "es-MX" : "en"' in source
    assert 'const returnPath = spanish ? "/es/assessment" : "/assessment"' in source
    assert 'const operationsHref = spanish ? "/operations?lang=es-MX"' in source
    assert "document.referrer" not in source
    assert "history.replaceState" not in source
    assert "history.pushState" not in source
    assert "location.assign" not in source


def test_comprehensive_target_hides_unrelated_legacy_recovery_surfaces() -> None:
    source = _source(RECOVERY_PAGE)

    assert "comprehensiveTarget ? <ComprehensiveRecoveryPanel" in source
    assert "locale={locale}" in source
    assert "returnPath={returnPath}" in source
    assert "!comprehensiveTarget ? <ScannerRecoveryPanel" in source
    assert "targetRunId={targetRunId}" in source


def test_spanish_comprehensive_resume_returns_to_same_exact_run() -> None:
    source = _source(COMPREHENSIVE_PANEL)

    assert 'String(exact.run_id || "") !== targetRunId' in source
    assert 'String(recovered.run_id || "") !== targetRunId' in source
    assert 'target.searchParams.set("tier", "comprehensive")' in source
    assert 'target.searchParams.set("run_id", targetRunId)' in source
    assert 'const returnPath = spanish ? "/es/assessment"' in _source(RECOVERY_PAGE)
    assert "data-recovery-locale={locale}" in source


def test_spanish_recovery_copy_has_no_known_authored_english_leaks() -> None:
    page_copy = _spanish_copy(_source(RECOVERY_PAGE))
    panel_copy = _spanish_copy(_source(COMPREHENSIVE_PANEL))
    spanish_copy = f"{page_copy}\n{panel_copy}"

    for required in (
        "Control de recuperación",
        "Destino exacto de recuperación",
        "Límite de autorización de recuperación",
        "Reanudar la ejecución exacta conservada",
        "Motivo técnico conservado",
        "La revisión humana sigue siendo obligatoria",
    ):
        assert required in spanish_copy

    for forbidden in (
        "Recovery Control",
        "Exact recovery target",
        "Back to Operations",
        "Operator authentication",
        "Load recovery",
        "Resume the preserved exact",
        "Current stage",
        "Preserved failure reason",
        "Reload exact run state",
        "Working...",
        "Human review remains required",
    ):
        assert forbidden not in spanish_copy


def test_spanish_failure_stage_and_status_are_localized_without_mutating_ids() -> None:
    source = _source(FAILURE_PANEL)

    assert "stageDisplayLabel(item.step, spanish)" in source
    assert "statusDisplayLabel(item.status, spanish)" in source
    assert "data-stage-id={item.step}" in source
    assert "title={item.step}" in source
    assert "data-status-id={item.status}" in source
    assert "title={item.status}" in source
    assert "authoredFailureMessage(item.message, spanish" in source
    assert "authoredFailureMessage(failure.message, spanish" in source
    assert "return localizeExactSpanishText(source) || fallback" in source
    assert "technicalReasonFallback" in source
    assert "stageReasonFallback" in source
    assert "<p>{item.message}</p>" not in source
    assert "<dd>{failure.message}</dd>" not in source
