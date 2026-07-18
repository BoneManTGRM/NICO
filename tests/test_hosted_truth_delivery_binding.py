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
    assert "current = client_acceptance.attach_client_acceptance_gate" in source
    assert "client_acceptance.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth" in source
    assert "api_main.attach_client_acceptance_gate = attach_client_acceptance_gate_with_report_truth" in source
    assert "normalize_assessment_completion(accepted, gated)" in source


def test_binding_is_idempotent_and_preserves_current_gate() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert '_PATCH_MARKER = "_nico_hosted_truth_completion_bound_v3"' in source
    assert "if getattr(current, _PATCH_MARKER, False)" in source
    assert 'client_acceptance._nico_original_attach_client_acceptance_gate = current' in source
    assert 'setattr(attach_client_acceptance_gate_with_report_truth, "_nico_previous", current)' in source


def test_assessment_storage_uses_actual_terminal_status_and_run_identity() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert "_patch_assessment_storage_truth(api_main)" in source
    assert 'status = str(result.get("status") or "unknown")' in source
    assert 'result.get("run_id")' in source
    assert 'result.get("assessment_id")' in source
    assert 'result.get("report_id")' in source
    assert 'result.get("scan_id")' in source
    assert 'run_id = _assessment_run_id(result)' in source
    assert 'record_id = f"{workflow}_{customer_id}_{project_id}_{run_id}"' in source
    assert '"status": status' in source
    assert '"run_id": run_id' in source


def test_missing_upstream_identity_is_stable_across_storage_retries() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert '_STORAGE_RUN_ID_KEY = "_nico_storage_run_id"' in source
    assert "fallback_id = result.get(_STORAGE_RUN_ID_KEY)" in source
    assert "fallback_id = uuid4().hex" in source
    assert "result[_STORAGE_RUN_ID_KEY] = fallback_id" in source
    assert "return str(fallback_id)" in source


def test_assessment_storage_covers_all_product_tiers_without_cross_tier_lookup() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert '"express": "_LAST_HOSTED_ASSESSMENT"' in source
    assert '"mid": "_LAST_MID_ASSESSMENT"' in source
    assert '"full": "_LAST_FULL_ASSESSMENT"' in source
    assert '"retainer": "_LAST_RETAINER_OPS"' in source
    assert 'source_by_workflow.get(str(workflow).lower(), "")' in source
    assert '"tier": workflow' in source


def test_assessment_storage_patch_is_idempotent_and_preserves_previous_helper() -> None:
    source = GATE.read_text(encoding="utf-8")

    assert '_STORAGE_PATCH_MARKER = "_nico_assessment_storage_truth_bound_v2"' in source
    assert "if getattr(current, _STORAGE_PATCH_MARKER, False)" in source
    assert 'setattr(truthful_assessment_storage_record, "_nico_previous", current)' in source
    assert "api_main.assessment_storage_record = truthful_assessment_storage_record" in source
