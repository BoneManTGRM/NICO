from nico.workflow_supply_chain_policy_v1 import (
    audit_action_references,
    classify_action_reference,
    validate_dependabot_policy,
)


def test_commit_sha_is_immutable() -> None:
    result = classify_action_reference("actions/checkout@" + "a" * 40)
    assert result["pinned"] is True


def test_tag_is_mutable_and_requires_review() -> None:
    result = audit_action_references(["actions/checkout@v4"])
    assert result["all_external_actions_pinned"] is False
    assert result["review_required"] is True


def test_local_action_is_allowed() -> None:
    result = classify_action_reference("./.github/actions/example@local")
    assert result["pinned"] is True


def test_dependabot_requires_cooldown_and_grouping() -> None:
    config = {
        "updates": [
            {
                "package-ecosystem": ecosystem,
                "cooldown": {"default-days": 7},
                "groups": {"all": {"patterns": ["*"]}},
            }
            for ecosystem in ("pip", "npm", "github-actions")
        ]
    }
    assert validate_dependabot_policy(config)["ready"] is True


def test_dependabot_missing_cooldown_fails_closed() -> None:
    config = {
        "updates": [
            {"package-ecosystem": "pip", "groups": {"all": {"patterns": ["*"]}}},
            {"package-ecosystem": "npm", "groups": {"all": {"patterns": ["*"]}}},
            {"package-ecosystem": "github-actions", "groups": {"all": {"patterns": ["*"]}}},
        ]
    }
    result = validate_dependabot_policy(config)
    assert result["ready"] is False
    assert any("cooldown" in blocker for blocker in result["blockers"])
