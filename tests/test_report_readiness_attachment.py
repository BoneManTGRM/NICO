from __future__ import annotations

from nico.report_readiness_attachment import attach_report_readiness_gate


def test_attach_report_readiness_gate_marks_delivery_ready_when_allowed():
    report = {"run_id": "run-1", "unavailable_data_notes": []}
    gate = {
        "artifact_schema": "nico.report_readiness_gate.v1",
        "status": "ready_for_fresh_express_report",
        "report_delivery_allowed": True,
        "missing": [],
        "blockers": [],
    }

    result = attach_report_readiness_gate(report, gate)

    assert result["report_readiness_gate"] == gate
    assert result["delivery_readiness"]["status"] == "delivery_ready"
    assert result["delivery_readiness"]["delivery_allowed"] is True
    assert result["unavailable_data_notes"] == []
    assert result["evidence_artifact_bundle"]["artifacts"][-1]["type"] == "report_readiness_gate"


def test_attach_report_readiness_gate_blocks_missing_gate():
    result = attach_report_readiness_gate({"run_id": "run-1"})

    assert result["report_readiness_gate"]["status"] == "missing_report_readiness_gate"
    assert result["delivery_readiness"]["status"] == "delivery_blocked"
    assert result["delivery_readiness"]["delivery_allowed"] is False
    assert any("Report delivery blocked" in note for note in result["unavailable_data_notes"])


def test_attach_report_readiness_gate_preserves_existing_bundle_and_notes():
    report = {
        "unavailable_data_notes": ["Existing note."],
        "evidence_artifact_bundle": {"artifacts": [{"type": "existing"}]},
    }
    gate = {
        "status": "blocked_report_readiness",
        "report_delivery_allowed": False,
        "missing": ["deployment:frontend_config.backend_url"],
        "blockers": ["Hosted smoke test has not passed."],
    }

    result = attach_report_readiness_gate(report, gate)

    assert result["unavailable_data_notes"][0] == "Existing note."
    assert any("deployment:frontend_config.backend_url" in note for note in result["unavailable_data_notes"])
    assert any("Hosted smoke test" in note for note in result["unavailable_data_notes"])
    assert result["evidence_artifact_bundle"]["artifacts"][0]["type"] == "existing"
    assert result["evidence_artifact_bundle"]["artifacts"][-1]["type"] == "report_readiness_gate"
