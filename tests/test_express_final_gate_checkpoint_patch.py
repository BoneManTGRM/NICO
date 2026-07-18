from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "nico" / "express_final_gate_checkpoint_patch.py"
ASYNC_METADATA = ROOT / "nico" / "express_async_contract_metadata.py"
ASYNC_API = ROOT / "nico" / "express_async_api.py"


def test_async_runner_enters_final_gate_after_report_generation() -> None:
    source = ASYNC_API.read_text(encoding="utf-8")
    assert "result = api_main.finalize_express_result_consistency(result)" in source
    assert '"truth_and_review_gates"' in source
    assert "result = api_main.attach_evidence_artifact_bundle(result)" in source


def test_post_render_result_is_cached_by_exact_run_id() -> None:
    source = PATCH.read_text(encoding="utf-8")
    assert "run_id = str(output.get(\"run_id\") or result.get(\"run_id\") or \"\").strip()" in source
    assert "_CHECKPOINTS[run_id] = deepcopy(output)" in source
    assert '"preserves_exact_run": True' in source


def test_truth_gate_stage_records_rich_report_checkpoint_not_bare_stage_payload() -> None:
    source = PATCH.read_text(encoding="utf-8")
    assert 'if stage != "truth_and_review_gates"' in source
    assert "checkpoint = deepcopy(_CHECKPOINTS.get(run_id) or {})" in source
    assert 'checkpoint["status"] = "running"' in source
    assert 'checkpoint["current_stage"] = "truth_and_review_gates"' in source
    assert 'checkpoint["progress_percent"] = max(94, int(progress_percent or 94))' in source
    assert '"rich_report_checkpoint_persisted": True' in source
    assert '"usable_report_artifacts": _usable_reports(checkpoint)' in source
    assert "express_async_api._record(run_id, request_payload, checkpoint)" in source


def test_checkpoint_keeps_reports_score_sections_and_review_truth() -> None:
    source = PATCH.read_text(encoding="utf-8")
    assert "checkpoint = deepcopy(_CHECKPOINTS.get(run_id) or {})" in source
    assert 'checkpoint["human_review_required"] = True' in source
    assert 'checkpoint["client_ready"] = False' in source
    assert 'checkpoint["persistence"] = express_async_api._persistence()' in source
    assert "checkpoint.pop(\"reports\", None)" not in source
    assert "checkpoint.pop(\"sections\", None)" not in source
    assert "checkpoint.pop(\"maturity_signal\", None)" not in source


def test_checkpoint_patch_installs_with_async_runtime() -> None:
    source = ASYNC_METADATA.read_text(encoding="utf-8")
    assert "install_express_final_gate_checkpoint_patch" in source
    assert "final_gate_checkpoint = install_express_final_gate_checkpoint_patch()" in source
    assert '"final_gate_checkpoint": final_gate_checkpoint' in source
