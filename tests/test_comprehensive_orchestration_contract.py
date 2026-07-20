from nico.comprehensive_orchestration_contract import (
    COMPREHENSIVE_ONLY_STAGES,
    COMPREHENSIVE_STAGES,
    EXPRESS_STAGES,
    TERMINAL_STAGES,
    build_comprehensive_contract,
    stage_contract,
    validate_comprehensive_contract,
)


def test_comprehensive_contains_every_express_stage_and_all_deep_stages() -> None:
    contract = build_comprehensive_contract(
        repository="BoneManTGRM/NICO",
        authorized=True,
        commit_sha="56fe88f4b067e3ec3ae6886344a15ddd8c918c1c",
    )

    stage_ids = [item["id"] for item in contract["stages"]]
    assert stage_ids == list(COMPREHENSIVE_STAGES)
    assert stage_ids[: len(EXPRESS_STAGES)] == list(EXPRESS_STAGES)
    assert all(stage in stage_ids for stage in COMPREHENSIVE_ONLY_STAGES)
    assert all(stage in stage_ids for stage in TERMINAL_STAGES)
    assert contract["includes_everything_in_express"] is True


def test_comprehensive_uses_one_identity_and_blocks_automatic_delivery() -> None:
    contract = build_comprehensive_contract(repository="owner/repo", authorized=True)

    assert contract["service_id"] == "comprehensive"
    assert contract["one_snapshot"] is True
    assert contract["one_run_id"] is True
    assert contract["one_evidence_ledger"] is True
    assert contract["one_canonical_score"] is True
    assert contract["one_final_report_package"] is True
    assert contract["human_review_required"] is True
    assert contract["client_delivery_allowed"] is False
    assert validate_comprehensive_contract(contract)["status"] == "valid"


def test_comprehensive_blocks_missing_authorization_or_repository() -> None:
    contract = build_comprehensive_contract(repository="", authorized=False)

    assert contract["status"] == "blocked"
    assert "repository_required" in contract["blockers"]
    assert "explicit_authorization_required" in contract["blockers"]
    assert all(stage["status"] == "blocked" for stage in contract["stages"])


def test_validation_rejects_missing_express_stage_and_delivery_bypass() -> None:
    contract = build_comprehensive_contract(repository="owner/repo", authorized=True)
    contract["stages"] = [item for item in contract["stages"] if item["id"] != EXPRESS_STAGES[0]]
    contract["client_delivery_allowed"] = True

    validation = validate_comprehensive_contract(contract)
    assert validation["status"] == "invalid"
    assert "missing_express_stages" in validation["violations"]
    assert "client_delivery_must_remain_blocked" in validation["violations"]
    assert EXPRESS_STAGES[0] in validation["missing_express_stages"]


def test_stage_lookup_returns_copy() -> None:
    contract = build_comprehensive_contract(repository="owner/repo", authorized=True)
    stage = stage_contract(contract, "functional_qa")
    assert stage is not None
    stage["status"] = "mutated"
    assert stage_contract(contract, "functional_qa")["status"] == "pending"
