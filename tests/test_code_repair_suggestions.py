from __future__ import annotations

from nico.code_repair_suggestions import build_code_suggestion


def test_known_security_pattern_returns_report_only_candidate() -> None:
    result = build_code_suggestion(
        category="python_shell_true",
        issue="subprocess shell=True expands command-injection risk",
        evidence=["nico/worker.py:42: shell=True"],
        affected_files=["nico/worker.py"],
    )

    assert result["status"] == "available"
    assert result["mode"] == "report_only"
    assert result["automatic_application_allowed"] is False
    assert result["automatic_commit_allowed"] is False
    assert result["automatic_pull_request_allowed"] is False
    assert result["human_review_required"] is True
    assert result["verified_fix"] is False
    assert "shell=False" in result["suggested_code"]
    assert result["applicability_conditions"]
    assert result["verification_steps"]


def test_unknown_issue_returns_no_fabricated_code() -> None:
    result = build_code_suggestion(
        category="unknown_business_logic",
        issue="The calculation appears incorrect",
        evidence=["A customer reported an unexpected number"],
        affected_files=[],
    )

    assert result["status"] == "unavailable"
    assert result["automatic_application_allowed"] is False
    assert "additional file context" in result["reason"].lower()


def test_secret_candidate_never_contains_supplied_secret() -> None:
    raw_secret = "gh" + "p_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    result = build_code_suggestion(
        category="secret_exposure",
        issue="Potential GitHub token",
        evidence=[f"token={raw_secret}"],
        affected_files=["settings.py"],
    )

    assert result["status"] == "available"
    assert raw_secret not in result["suggested_code"]
    assert "SERVICE_TOKEN" in result["suggested_code"]
    assert any("rotate" in item.lower() for item in result["applicability_conditions"])


def test_dependency_candidate_uses_placeholders_not_guessed_versions() -> None:
    result = build_code_suggestion(
        category="dependency_risk",
        issue="Dependency advisory requires an upgrade",
        evidence=["OSV advisory found"],
        affected_files=["requirements.txt"],
    )

    assert result["status"] == "available"
    assert "<minimum-fixed-version>" in result["suggested_code"]
    assert "verified-fixed-version" in result["suggested_code"]
    assert result["verified_fix"] is False
