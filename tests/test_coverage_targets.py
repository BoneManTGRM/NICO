from nico.coverage_targets import COVERAGE_TARGETS, max_coverage_targets


def test_max_coverage_targets_are_upper_end_values():
    assert COVERAGE_TARGETS["express"] == "95%"
    assert COVERAGE_TARGETS["mid"] == "85%"
    assert COVERAGE_TARGETS["retainer"] == "70%"
    assert COVERAGE_TARGETS["client_ready_with_human_review"] == "85%"


def test_max_coverage_payload_keeps_human_gate_rule():
    payload = max_coverage_targets()

    assert payload["status"] == "ok"
    assert payload["mode"] == "upper_end_goals"
    assert payload["details"]["express"]["max_target"] == "95%"
    assert "Human review" in payload["rule"]
