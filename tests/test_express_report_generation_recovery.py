from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "nico" / "express_report_generation_recovery.py"
ASYNC_METADATA = ROOT / "nico" / "express_async_contract_metadata.py"


def test_report_recovery_requires_all_direct_formats() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert '_REQUIRED_FORMATS = ("markdown", "html", "pdf_base64")' in source
    assert "return all(bool(str(reports.get(name) or \"\").strip())" in source
    assert "for name in _REQUIRED_FORMATS" in source


def test_report_recovery_is_bounded_and_same_run_only() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert "_MAX_ATTEMPTS = 3" in source
    assert "while not _usable_formats(output) and attempts < _MAX_ATTEMPTS" in source
    assert "output = deepcopy(rebuild_reports(output))" in source
    assert '"same_run_continuation": True' in source
    assert '"duplicate_assessment_started": False' in source


def test_exhausted_recovery_fails_closed_with_explicit_evidence() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert 'output["status"] = "blocked"' in source
    assert 'output["report_generation_status"] = "blocked_missing_usable_artifacts"' in source
    assert 'output["recovery_code"] = "express_report_generation_exhausted"' in source
    assert 'output["client_delivery_allowed"] = False' in source
    assert "missing_formats" in source


def test_recovery_installs_with_async_runtime_after_renderer_bindings() -> None:
    source = ASYNC_METADATA.read_text(encoding="utf-8")
    assert "install_express_report_generation_recovery" in source
    assert "report_recovery = install_express_report_generation_recovery()" in source
    assert '"report_generation_recovery": report_recovery' in source
