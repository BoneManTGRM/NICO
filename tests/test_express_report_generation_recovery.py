from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "nico" / "express_report_generation_recovery.py"
ASYNC_METADATA = ROOT / "nico" / "express_async_contract_metadata.py"


def test_report_recovery_requires_all_direct_formats_and_verified_pdf() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert '_REQUIRED_FORMATS = ("markdown", "html", "pdf_base64")' in source
    assert 'for name in ("markdown", "html")' in source
    assert 'base64.b64decode(encoded, validate=True)' in source
    assert 'decoded.startswith(b"%PDF-")' in source
    assert 'return text_ready and _pdf_integrity(result)["valid"] is True' in source


def test_corrupt_pdf_is_reported_as_missing_and_cannot_complete() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert '"reason": "invalid_base64"' in source
    assert '"reason": "invalid_pdf_signature"' in source
    assert 'missing.append("pdf_base64")' in source
    assert '"pdf_integrity": pdf_integrity' in source
    assert '"pdf_integrity_required": True' in source


def test_verified_pdf_records_hash_and_decoded_size() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert '"reason": "verified"' in source
    assert '"size_bytes": len(decoded)' in source
    assert '"sha256": hashlib.sha256(decoded).hexdigest()' in source


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
    assert "integrity-verified PDF artifacts" in source
    assert "missing_formats" in source


def test_recovery_installs_with_async_runtime_after_renderer_bindings() -> None:
    source = ASYNC_METADATA.read_text(encoding="utf-8")
    assert "install_express_report_generation_recovery" in source
    assert "report_recovery = install_express_report_generation_recovery()" in source
    assert '"report_generation_recovery": report_recovery' in source
