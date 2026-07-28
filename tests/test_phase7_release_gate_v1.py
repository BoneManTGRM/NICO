from __future__ import annotations

import pytest

from nico.phase7_release_gate_v1 import GateResult, REQUIRED_GATES, evaluate_release_gate, require_release_ready


def _all_passed() -> list[GateResult]:
    return [GateResult(name, True, evidence_reference=f"artifact://{name}") for name in REQUIRED_GATES]


def test_release_is_blocked_when_any_gate_is_missing() -> None:
    results = _all_passed()[:-1]
    decision = evaluate_release_gate(results)
    assert decision["ready_to_merge"] is False
    assert decision["missing_gates"] == [REQUIRED_GATES[-1]]


def test_release_is_blocked_when_gate_passes_without_evidence() -> None:
    results = _all_passed()
    results[0] = GateResult(REQUIRED_GATES[0], True, evidence_reference="")
    decision = evaluate_release_gate(results)
    assert decision["ready_to_merge"] is False
    assert decision["passed_without_evidence"] == [REQUIRED_GATES[0]]


def test_release_is_blocked_when_any_gate_fails() -> None:
    results = _all_passed()
    results[3] = GateResult(REQUIRED_GATES[3], False, reason="scanner incomplete")
    with pytest.raises(RuntimeError, match="failed=.*required_scanners_complete"):
        require_release_ready(results)


def test_release_is_ready_only_when_every_gate_passes_with_evidence() -> None:
    decision = require_release_ready(_all_passed())
    assert decision["ready_to_merge"] is True
    assert decision["client_delivery_allowed"] is False
