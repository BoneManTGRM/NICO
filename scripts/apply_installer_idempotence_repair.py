from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"Expected repair target was not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    replace_once(
        Path("nico/assessment_score_integrity.py"),
        '''def install_assessment_score_integrity() -> dict[str, Any]:
    installed = bool(getattr(scanner_worker, "_nico_score_integrity_installed", False))
    _rebind()
    scanner_worker._nico_score_integrity_installed = True
    return {
''',
        '''def install_assessment_score_integrity() -> dict[str, Any]:
    installed = bool(getattr(scanner_worker, "_nico_score_integrity_installed", False))
    if not installed:
        _rebind()
        scanner_worker._nico_score_integrity_installed = True
    return {
''',
    )

    replace_once(
        Path("tests/test_assessment_score_integrity.py"),
        '''def test_installer_rebinds_scoring_collection_and_mid_attachment() -> None:
    first = install_assessment_score_integrity()
    second = install_assessment_score_integrity()
    compat_first = install_score_integrity_compatibility()
    compat_second = install_score_integrity_compatibility()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert compat_first["status"] in {"installed", "already_installed"}
    assert compat_second["status"] == "already_installed"
    assert first["version"] == INTEGRITY_VERSION
    assert "nico-secrets" in scanner_worker.TOOL_CATALOG
    assert "nico-static" in scanner_worker.TOOL_CATALOG
    assert hosted.scan_files.__name__ == "calibrated_scan_files"
    assert hosted.analyze_secrets.__name__ == "calibrated_analyze_secrets"
    assert snapshot_repository.scan_files.__name__ == "calibrated_scan_files"
    assert snapshot_repository.collect_complexity_evidence.__name__ == "calibrated_collect_complexity_evidence"
    assert scorecard._secrets_section.__name__ == "calibrated_secrets_section"
    assert scorecard._static_section.__name__ == "calibrated_static_section"
    assert snapshot_handlers._snapshot_evidence_attachment_handler.__name__ == "calibrated_attachment_handler"
    assert mid_handlers._snapshot_evidence_attachment_handler.__name__ == "calibrated_attachment_handler"
''',
        '''def test_installer_is_idempotent_and_preserves_later_attachment_wrappers() -> None:
    snapshot_attachment = snapshot_handlers._snapshot_evidence_attachment_handler
    mid_attachment = mid_handlers._snapshot_evidence_attachment_handler

    first = install_assessment_score_integrity()
    second = install_assessment_score_integrity()
    compat_first = install_score_integrity_compatibility()
    compat_second = install_score_integrity_compatibility()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert compat_first["status"] in {"installed", "already_installed"}
    assert compat_second["status"] == "already_installed"
    assert first["version"] == INTEGRITY_VERSION
    assert "nico-secrets" in scanner_worker.TOOL_CATALOG
    assert "nico-static" in scanner_worker.TOOL_CATALOG
    assert hosted.scan_files.__name__ == "calibrated_scan_files"
    assert hosted.analyze_secrets.__name__ == "calibrated_analyze_secrets"
    assert snapshot_repository.scan_files.__name__ == "calibrated_scan_files"
    assert snapshot_repository.collect_complexity_evidence.__name__ == "calibrated_collect_complexity_evidence"
    assert scorecard._secrets_section.__name__ == "calibrated_secrets_section"
    assert scorecard._static_section.__name__ == "calibrated_static_section"
    assert snapshot_handlers._snapshot_evidence_attachment_handler is snapshot_attachment
    assert mid_handlers._snapshot_evidence_attachment_handler is mid_attachment
''',
    )


if __name__ == "__main__":
    main()
