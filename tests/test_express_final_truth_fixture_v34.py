import json
from pathlib import Path


def test_express_final_truth_fixture_retains_release_boundaries() -> None:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "express_final_truth_repair_v34.json").read_text(encoding="utf-8")
    )
    invariants = fixture["required_invariants"]

    assert invariants["terminal_steps_all_complete"] is True
    assert invariants["canonical_overall_score_is_evidence_adjusted"] is True
    assert invariants["source_scores_finalized_before_presentation"] is True
    assert invariants["ordinary_findings_not_double_charged"] is True
    assert invariants["human_review_required"] is True
    assert invariants["client_delivery_allowed"] is False
