from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "nico" / "hosted_truth_delivery_gate.py"
API_MAIN = ROOT / "nico" / "api" / "main.py"
ASYNC_API = ROOT / "nico" / "express_async_api.py"


def test_async_express_uses_directly_imported_client_acceptance_reference() -> None:
    main_source = API_MAIN.read_text(encoding="utf-8")
    async_source = ASYNC_API.read_text(encoding="utf-8")

    assert "from nico.client_acceptance import attach_client_acceptance_gate" in main_source
    assert "result = api_main.attach_client_acceptance_gate(result)" in async_source


def test_patch_rebinds_both_module_and_api_main_references() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert "from nico.api import main as api_main" in source
    assert "current = api_main.attach_client_acceptance_gate" in source
    assert "client_acceptance.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth" in source
    assert "api_main.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth" in source
    assert "normalize_assessment_completion(accepted, gated)" in source


def test_binding_is_idempotent_and_preserves_original_gate() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert '_PATCH_MARKER = "_nico_hosted_truth_completion_bound_v2"' in source
    assert "if getattr(current, _PATCH_MARKER, False)" in source
    assert 'client_acceptance._nico_original_attach_client_acceptance_gate = original' in source
    assert 'setattr(attach_client_acceptance_gate_with_report_truth, "_nico_previous", original)' in source
