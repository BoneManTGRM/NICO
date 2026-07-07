from nico.status_output import attach_status_output


def test_attach_status_output_adds_summary():
    result = attach_status_output({})

    assert "max_target_status" in result
    assert "max_target_summary" in result
    assert result["max_target_summary"]["overall_target"] == 84


def test_attach_status_output_preserves_payload():
    result = attach_status_output({"run_id": "run_1"})

    assert result["run_id"] == "run_1"
    assert result["max_target_summary"]["next_gate_count"] > 0
