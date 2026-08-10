from __future__ import annotations

import hashlib
import json
from typing import Any

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import (
    FINAL_REPORT_STAGE_ID,
    _canonical_hash,
    _record_hash,
    apply_comprehensive_stage_result,
    create_comprehensive_run_record,
    restore_comprehensive_run_record,
    validate_comprehensive_run_record,
)
from nico.comprehensive_run_store import ComprehensiveRunStore


class _NoDeepcopyDict(dict[str, Any]):
    def __deepcopy__(self, memo: dict[int, Any]) -> "_NoDeepcopyDict":
        raise AssertionError("retained canonical stage evidence must not be deep-copied")


def _new_record() -> dict[str, Any]:
    return create_comprehensive_run_record(
        run_id="comprun_copy_boundary",
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_copy_boundary",
        customer_id="customer",
        project_id="project",
        authorized=True,
    )


def _install_retained_sentinel(record: dict[str, Any]) -> _NoDeepcopyDict:
    first_stage = COMPREHENSIVE_STAGES[0]
    retained = _NoDeepcopyDict(record["stage_results"][first_stage])
    record["stage_results"] = dict(record["stage_results"])
    record["stage_results"][first_stage] = retained
    record["integrity_sha256"] = _record_hash(record)
    assert validate_comprehensive_run_record(record)["status"] == "valid"
    return retained


def test_canonical_streaming_hash_preserves_existing_digest_contract() -> None:
    payload = {
        "z": ["ñ", {"value": 3}],
        "a": {"nested": True},
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    assert _canonical_hash(payload) == hashlib.sha256(encoded).hexdigest()


def test_stage_continuation_retains_prior_evidence_without_copying_it() -> None:
    record = _new_record()
    first_stage, second_stage = COMPREHENSIVE_STAGES[:2]
    record = apply_comprehensive_stage_result(
        record,
        stage_id=first_stage,
        result={"status": "complete", "evidence": {"items": ["retained"]}},
    )
    retained = _install_retained_sentinel(record)
    incoming = {"status": "complete", "evidence": {"items": []}}

    updated = apply_comprehensive_stage_result(
        record,
        stage_id=second_stage,
        result=incoming,
    )
    incoming["evidence"]["items"].append("caller mutation")

    assert updated is not record
    assert updated["stage_results"] is not record["stage_results"]
    assert updated["stage_results"][first_stage] is retained
    assert second_stage not in record["stage_results"]
    assert updated["stage_results"][second_stage]["evidence"]["items"] == []
    assert updated["human_review_required"] is True
    assert updated["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(updated)["status"] == "valid"


def test_final_report_package_uses_bounded_copy_boundary() -> None:
    record = _new_record()
    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id == FINAL_REPORT_STAGE_ID:
            break
        record = apply_comprehensive_stage_result(
            record,
            stage_id=stage_id,
            result={"status": "complete", "evidence": {"stage": stage_id}},
        )

    retained = _install_retained_sentinel(record)
    canonical_json = _NoDeepcopyDict({"identity": {"run_id": "comprun_copy_boundary"}})
    report_package = _NoDeepcopyDict(
        {
            "report_id": "report-copy-boundary",
            "json": canonical_json,
            "pdf_base64": "JVBERi0xLjQK",
        }
    )

    updated = apply_comprehensive_stage_result(
        record,
        stage_id=FINAL_REPORT_STAGE_ID,
        result={"status": "complete", "report_package": report_package},
    )
    stored_package = updated["stage_results"][FINAL_REPORT_STAGE_ID]["report_package"]

    assert updated["stage_results"][COMPREHENSIVE_STAGES[0]] is retained
    assert stored_package is not report_package
    assert stored_package["json"] is canonical_json
    assert updated["human_review_required"] is True
    assert updated["client_delivery_allowed"] is False
    assert validate_comprehensive_run_record(updated)["status"] == "valid"


def test_restore_and_store_validation_do_not_clone_retained_stage_tree() -> None:
    record = _new_record()
    first_stage = COMPREHENSIVE_STAGES[0]
    record = apply_comprehensive_stage_result(
        record,
        stage_id=first_stage,
        result={"status": "complete", "evidence": {"items": ["retained"]}},
    )
    retained = _install_retained_sentinel(record)

    restored = restore_comprehensive_run_record(record)
    store = ComprehensiveRunStore(lambda: None)
    canonical = store._validated_copy(restored)
    serialized = store._row_values(canonical)[-1]

    assert restored is not record
    assert restored["identity"] is not record["identity"]
    assert restored["stage_results"] is not record["stage_results"]
    assert restored["stage_results"][first_stage] is retained
    assert canonical["stage_results"][first_stage] is retained
    assert json.loads(serialized)["stage_results"][first_stage]["status"] == "complete"
    assert validate_comprehensive_run_record(canonical)["status"] == "valid"
