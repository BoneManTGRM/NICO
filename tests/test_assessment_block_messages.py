from __future__ import annotations

import json
from pathlib import Path

from nico.assessment_block_messages import (
    actionable_blocked_exception,
    assessment_block_detail,
    classify_assessment_block,
)


ROOT = Path(__file__).resolve().parents[1]
NETWORK_BUDGET = ROOT / "nico" / "assessment_network_budget.py"
ASSESSMENT_WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"


def test_repository_404_is_actionable_without_exposing_provider_detail() -> None:
    result = {
        "status": "blocked",
        "repository": "BoneManTGRM/NICI",
        "error": "Repository metadata unavailable: GitHub returned HTTP 404; upstream-body=private-provider-detail",
    }

    detail = assessment_block_detail(result)
    encoded = json.dumps(detail)

    assert detail == {
        "status": "blocked",
        "code": "repository_not_found_or_inaccessible",
        "message": (
            "Repository 'BoneManTGRM/NICI' could not be found or accessed. "
            "Check the owner/repository spelling. For a private repository, verify that NICO's backend GitHub authorization can access it."
        ),
        "field": "repository",
        "repository": "BoneManTGRM/NICI",
    }
    assert "private-provider-detail" not in encoded
    assert "upstream-body" not in encoded


def test_missing_authorization_has_distinct_safe_guidance() -> None:
    result = {
        "status": "blocked",
        "error": "Explicit authorization is required before NICO assesses a repository.",
    }

    assert classify_assessment_block(result) == "authorization_required"
    assert assessment_block_detail(result) == {
        "status": "blocked",
        "code": "authorization_required",
        "message": "Confirm that you own this repository or have explicit permission to assess it, then try again.",
        "field": "authorization",
    }


def test_invalid_repository_format_has_distinct_safe_guidance() -> None:
    detail = assessment_block_detail(
        {"status": "blocked", "error": "repository must be owner/name or a GitHub repository URL"}
    )

    assert detail["code"] == "invalid_repository"
    assert detail["field"] == "repository"
    assert "owner/name" in detail["message"]


def test_bounded_github_timeout_is_not_mislabeled_as_authorization_failure() -> None:
    detail = assessment_block_detail(
        {
            "status": "blocked",
            "repository": "BoneManTGRM/NICO",
            "error": "Repository metadata unavailable: GitHub request did not complete within the bounded collection window.",
        }
    )

    assert detail["code"] == "github_temporarily_unavailable"
    assert "bounded request window" in detail["message"]
    assert detail["repository"] == "BoneManTGRM/NICO"


def test_unknown_policy_block_remains_generic_and_redacted() -> None:
    detail = assessment_block_detail(
        {"status": "blocked", "code": "unrecognized_internal_reason", "error": "secret internal detail"}
    )

    assert detail == {
        "status": "blocked",
        "code": "unrecognized_internal_reason",
        "message": "Request blocked by NICO safety, authorization, or review policy.",
    }
    assert "secret internal detail" not in json.dumps(detail)


def test_actionable_exception_preserves_fail_closed_http_status() -> None:
    exc = actionable_blocked_exception(
        {
            "status": "blocked",
            "repository": "BoneManTGRM/NICI",
            "error": "Repository metadata unavailable: GitHub returned HTTP 404; this evidence source is unavailable.",
        }
    )

    assert exc.status_code == 400
    assert exc.detail["code"] == "repository_not_found_or_inaccessible"
    assert exc.detail["status"] == "blocked"


def test_production_installer_activates_block_message_patch() -> None:
    source = NETWORK_BUDGET.read_text(encoding="utf-8")

    assert "from nico.assessment_block_messages import install_assessment_block_messages" in source
    assert "block_messages = install_assessment_block_messages()" in source
    assert '"block_messages": block_messages' in source


def test_frontend_prioritizes_safe_backend_message_and_starts_with_empty_repository() -> None:
    source = ASSESSMENT_WORKSPACE.read_text(encoding="utf-8")

    assert 'typeof data.detail === "string" ? data.detail : data.detail?.message' in source
    assert 'const [repository, setRepository] = useState("")' in source
    assert 'useState("BoneManTGRM/NICO")' not in source
    assert 'useState("BoneManTGRM/NICI")' not in source
