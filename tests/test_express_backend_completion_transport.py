from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT = ROOT / "nico" / "express_backend_completion_transport.py"
INIT = ROOT / "nico" / "__init__.py"


def test_live_api_gate_normalizes_completion_before_transport() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")
    assert "current_gate: Callable" in source
    assert "after = current_gate(result)" in source
    assert "return normalize_assessment_completion(before, after)" in source
    assert "api_main.attach_client_acceptance_gate = authoritative_gate" in source
    assert "client_acceptance.attach_client_acceptance_gate = authoritative_gate" in source


def test_safe_payload_preserves_completion_score_sections_and_reports() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")
    assert '"assessment_completion"' in source
    assert '"express_completion"' in source
    assert '"reports"' in source
    assert '"sections"' in source
    assert '"maturity_signal"' in source
    assert '"technical_score"' in source
    assert "output = _copy_completion_fields(normalized, safe)" in source


def test_complete_contract_is_persisted_pending_human_review() -> None:
    source = TRANSPORT.read_text(encoding="utf-8")
    assert 'completion.get("status") == "complete_pending_human_review"' in source
    assert 'output["status"] = "complete"' in source
    assert 'output["current_stage"] = "complete"' in source
    assert 'output["progress_percent"] = 100' in source
    assert 'output["human_review_required"] = True' in source
    assert 'output["client_delivery_allowed"] = False' in source


def test_transport_installs_after_all_express_report_bindings() -> None:
    source = INIT.read_text(encoding="utf-8")
    final_bind = source.rindex("install_express_backend_completion_transport()")
    assert source.index("install_express_report_premium_v14()") < final_bind
    assert source.index("install_express_dossier_export_v15()") < final_bind
    assert source.index("install_report_quality_gate_compat()") < final_bind
