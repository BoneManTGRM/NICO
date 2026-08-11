from __future__ import annotations

from nico.comprehensive_review_work_runtime_v1 import (
    _normalize_review_ledger,
    _review_action_record,
)


def test_zero_candidate_ledger_is_validator_compatible_but_persists_numeric() -> None:
    record = {
        "review_work_ledger": {
            "artifact_schema": "nico.comprehensive_review_work_ledger.v1",
            "candidate_count": 0,
            "candidate_ids": [],
        }
    }
    compatible = _review_action_record(record)
    assert compatible is not record
    assert compatible["review_work_ledger"]["candidate_count"] == "0"
    assert record["review_work_ledger"]["candidate_count"] == 0

    normalized = _normalize_review_ledger(dict(compatible["review_work_ledger"]))
    assert normalized["candidate_count"] == 0


def test_nonzero_review_ledger_is_unchanged() -> None:
    record = {"review_work_ledger": {"candidate_count": 3}}
    assert _review_action_record(record) is record
