from nico.repair_intelligence import repair_quality_policy, suggest_repair


def test_repair_suggestion_includes_detailed_patch_plan():
    result = suggest_repair({
        "issue": "Missing dependency caused CI failure after adding upload endpoint",
        "evidence": ["Run all tests failed", "UploadFile/Form requires multipart parser"],
        "affected_files": ["requirements.txt", "nico/api/main.py"],
    })
    assert result["status"] == "complete"
    assert result["strategy"] == "dependency_or_runtime_contract_fix"
    assert result["root_cause_hypothesis"]
    assert result["patch_steps"]
    assert result["patch_prompt"]
    assert result["test_plan"]
    assert result["rollback_plan"]
    assert result["human_review_required"] is True
    assert result["automatic_application_allowed"] is False
    assert result["code_change_applied"] is False


def test_repair_policy_requires_review_and_evidence():
    policy = repair_quality_policy()
    assert policy["status"] == "ok"
    assert "quality_checklist" in policy
    assert any("review" in rule.lower() for rule in policy["rules"])
    assert policy["code_suggestion_policy"]["automatic_application_allowed"] is False
