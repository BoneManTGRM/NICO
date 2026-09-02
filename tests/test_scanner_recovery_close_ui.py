from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scanner_recovery_close_is_explicit_bilingual_and_evidence_preserving() -> None:
    panel = (ROOT / "apps/web/app/operations/ScannerRecoveryPanel.tsx").read_text(encoding="utf-8")
    page = (ROOT / "apps/web/app/operations/recovery/page.tsx").read_text(encoding="utf-8")

    assert "/operations/recovery/scanner/${encodeURIComponent(scanId)}/close" in panel
    assert 'body: JSON.stringify({actor: actor.trim(), reason_code: closeReason})' in panel
    assert "Close and retain evidence" in panel
    assert "Cerrar conservando la evidencia" in panel
    assert "conservando su evidencia" in panel
    assert "superseded_by_terminal_assessment" in panel
    assert "duplicate_or_test_run" in panel
    assert "locale={locale}" in page
