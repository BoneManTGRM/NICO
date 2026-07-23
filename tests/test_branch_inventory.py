from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "branch_inventory.py"
SPEC = importlib.util.spec_from_file_location("nico_branch_inventory", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def classify(**overrides):
    values = {
        "branch": "agent/example",
        "default_branch": "main",
        "protected": False,
        "open_prs": [],
        "ahead": 0,
        "age_days": 10,
        "stale_days": 90,
    }
    values.update(overrides)
    return MODULE.classify(**values)


def test_default_branch_is_never_a_deletion_candidate() -> None:
    classification, candidate, _ = classify(branch="main")
    assert classification == "ACTIVE_DEFAULT"
    assert candidate is False


def test_open_pull_request_is_never_a_deletion_candidate() -> None:
    classification, candidate, reason = classify(open_prs=[741])
    assert classification == "OPEN_PR"
    assert candidate is False
    assert "741" in reason


def test_protected_branch_is_never_a_deletion_candidate() -> None:
    classification, candidate, _ = classify(protected=True)
    assert classification == "PROTECTED_OR_RELEASE"
    assert candidate is False


def test_release_or_recovery_name_is_never_a_deletion_candidate() -> None:
    for branch in ("release/v1", "production", "hotfix/security", "recovery/snapshot", "backup-2026"):
        classification, candidate, _ = classify(branch=branch)
        assert classification == "DEPLOYMENT_OR_RELEASE"
        assert candidate is False


def test_only_fully_merged_unexcluded_branch_is_safe_to_delete() -> None:
    classification, candidate, reason = classify(ahead=0)
    assert classification == "MERGED_SAFE_TO_DELETE"
    assert candidate is True
    assert "No commits" in reason


def test_stale_branch_with_unique_commits_requires_manual_disposition() -> None:
    classification, candidate, reason = classify(ahead=3, age_days=120)
    assert classification == "STALE_WITH_UNMERGED_COMMITS"
    assert candidate is False
    assert "3 unique commit" in reason


def test_recent_branch_with_unique_commits_requires_manual_review() -> None:
    classification, candidate, _ = classify(ahead=1, age_days=2)
    assert classification == "MANUAL_REVIEW"
    assert candidate is False
