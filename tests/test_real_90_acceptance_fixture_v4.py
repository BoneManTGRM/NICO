from __future__ import annotations

import json
from pathlib import Path


def test_real_90_acceptance_fixture_forbids_score_inflation() -> None:
    payload = json.loads(
        Path("tests/fixtures/real_90_score_truth_v4_expected.json").read_text(encoding="utf-8")
    )
    minimums = payload["expected_minimums"]
    contracts = payload["non_negotiable_contracts"]

    assert minimums["technical_score"] >= 90
    assert minimums["evidence_adjusted_score"] >= 90
    assert contracts["target_score_used_as_input"] is False
    assert contracts["score_override_allowed"] is False
    assert contracts["unverified_candidate_volume_affects_technical_score"] is False
    assert contracts["verified_material_findings_affect_technical_score"] is True
    assert contracts["real_score_disagreement_remains_blocked"] is True
    assert contracts["human_review_required"] is True
    assert contracts["client_delivery_allowed"] is False
