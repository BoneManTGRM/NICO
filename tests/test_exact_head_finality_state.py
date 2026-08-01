from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs" / "exact-head-comprehensive-finality-observation.json"


def test_exact_head_finality_state_is_fail_closed_and_dependency_ordered() -> None:
    payload = json.loads(STATE.read_text(encoding="utf-8"))

    assert payload["artifact_schema"] == "nico.completion.work_package_state.v1"
    assert payload["workstream"] == 1
    assert payload["dependency_state"] == "first_incomplete"
    assert payload["state"] == "diagnosing"
    assert payload["observed"]["terminal_stage"] == "cross_format_truth_verification"
    assert payload["observed"]["terminal_reason"] == "final_artifact_truth_verification_failed"
    assert payload["gates"]["preserve_report_truth"] is True
    assert payload["gates"]["preserve_security_boundaries"] is True
    assert payload["gates"]["human_review_required"] is True
    assert payload["gates"]["client_delivery_allowed"] is False
    assert payload["gates"]["merge_requires_all_pr_checks"] is True
    assert payload["gates"]["post_merge_live_production_proofs_required"] is True
