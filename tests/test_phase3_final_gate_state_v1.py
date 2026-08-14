from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "phase3-final-gate-state.json"


def test_phase3_final_gate_cannot_claim_completion_before_production_proof() -> None:
    payload = json.loads(STATE.read_text(encoding="utf-8"))

    assert payload["phase"] == 3
    assert payload["state"] == "repair_in_progress"
    assert payload["one_public_product"] == "NICO Comprehensive"
    assert payload["one_client_report"] is True
    assert "exact_main_unified_production_acceptance_green" in payload["required_before_complete"]
    assert "fresh_comprehensive_report_bound_to_exact_main" in payload["required_before_complete"]
    assert payload["human_review_required"] is True
    assert payload["client_delivery_allowed_before_approval"] is False
