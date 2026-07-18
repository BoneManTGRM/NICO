from __future__ import annotations

import base64
from pathlib import Path

from nico.express_report_generation_recovery import _pdf_integrity

ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "nico" / "express_report_generation_recovery.py"
ASYNC_METADATA = ROOT / "nico" / "express_async_contract_metadata.py"
RUNTIME_PATCH = ROOT / "nico" / "report_truth_runtime_patch.py"


def _result_with_pdf(payload: bytes) -> dict[str, object]:
    return {"reports": {"pdf_base64": base64.b64encode(payload).decode("ascii")}}


def test_report_recovery_requires_all_direct_formats_and_structurally_complete_pdf() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert '_REQUIRED_FORMATS = ("markdown", "html", "pdf_base64")' in source
    assert 'for name in ("markdown", "html")' in source
    assert 'base64.b64decode(encoded, validate=True)' in source
    assert 'decoded.startswith(b"%PDF-")' in source
    assert 'b"%%EOF" not in trailer_window' in source
    assert 'return text_ready and _pdf_integrity(result)["valid"] is True' in source


def test_corrupt_pdf_is_reported_as_missing_and_cannot_complete() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert '"reason": "invalid_base64"' in source
    assert '"reason": "invalid_pdf_signature"' in source
    assert '"reason": "missing_pdf_eof"' in source
    assert 'missing.append("pdf_base64")' in source
    assert '"pdf_integrity": pdf_integrity' in source
    assert '"pdf_integrity_required": True' in source
    assert '"pdf_eof_required": True' in source


def test_truncated_pdf_with_valid_header_fails_integrity() -> None:
    integrity = _pdf_integrity(_result_with_pdf(b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"))
    assert integrity["valid"] is False
    assert integrity["reason"] == "missing_pdf_eof"
    assert integrity["size_bytes"] > 0
    assert integrity["sha256"]


def test_pdf_with_header_and_eof_in_trailer_window_passes_integrity() -> None:
    payload = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\nstartxref\n0\n%%EOF\n"
    integrity = _pdf_integrity(_result_with_pdf(payload))
    assert integrity["valid"] is True
    assert integrity["reason"] == "verified"
    assert integrity["size_bytes"] == len(payload)
    assert integrity["sha256"]


def test_eof_marker_must_be_near_file_trailer() -> None:
    payload = b"%PDF-1.7\n%%EOF\n" + (b"x" * 2048)
    integrity = _pdf_integrity(_result_with_pdf(payload))
    assert integrity["valid"] is False
    assert integrity["reason"] == "missing_pdf_eof"


def test_recovery_bypasses_only_the_public_complete_status_guard_for_rendering() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    runtime = RUNTIME_PATCH.read_text(encoding="utf-8")
    assert 'if result.get("status") != "complete":' in runtime
    assert 'core_rebuild = getattr(final_report_consistency, "_rebuild_reports")' in recovery
    assert "core_rebuild(output)" in recovery
    assert 'original_status = output.get("status")' in recovery
    assert 'output["status"] = original_status' in recovery
    assert '"blocked_status_bypass_for_render_only": True' in recovery


def test_report_recovery_is_bounded_same_run_and_records_renderer_errors() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert "_MAX_ATTEMPTS = 3" in source
    assert "while not _usable_formats(output) and attempts < _MAX_ATTEMPTS" in source
    assert "output, renderer_error = _rebuild_terminal_payload(output)" in source
    assert '"same_run_continuation": True' in source
    assert '"duplicate_assessment_started": False' in source
    assert '"renderer_errors": renderer_errors' in source
    assert 'return output, f"{type(exc).__name__}: {exc}"' in source


def test_successful_recovery_restores_complete_terminal_state() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert 'output["status"] = "complete"' in source
    assert 'output["report_generation_status"] = "complete"' in source
    assert 'output["recovery_required"] = False' in source
    assert 'output.pop("recovery_code", None)' in source


def test_exhausted_recovery_fails_closed_with_explicit_evidence() -> None:
    source = RECOVERY.read_text(encoding="utf-8")
    assert 'output["status"] = "blocked"' in source
    assert 'output["report_generation_status"] = "blocked_missing_usable_artifacts"' in source
    assert 'output["recovery_code"] = "express_report_generation_exhausted"' in source
    assert 'output["client_delivery_allowed"] = False' in source
    assert "structurally complete PDF artifacts" in source
    assert "missing_formats" in source


def test_recovery_installs_with_async_runtime_after_renderer_bindings() -> None:
    source = ASYNC_METADATA.read_text(encoding="utf-8")
    assert "install_express_report_generation_recovery" in source
    assert "report_recovery = install_express_report_generation_recovery()" in source
    assert '"report_generation_recovery": report_recovery' in source
