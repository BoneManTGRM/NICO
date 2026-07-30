from __future__ import annotations

from pathlib import Path

from nico.report_artifact_filename import (
    normalize_pdf_filename,
    normalize_report_artifact_filenames,
)
from nico.scanner_command_repair_v1 import install_scanner_command_repair
import nico.scanner_tool_runners as scanner_tool_runners


def test_pdf_filename_normalization_is_idempotent() -> None:
    duplicated = (
        "nico-comprehensive-assessment-repo-run-"
        "FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf"
    )
    expected = "nico-comprehensive-assessment-repo-run-FINAL-PENDING-APPROVAL.pdf"
    assert normalize_pdf_filename(duplicated) == expected
    assert normalize_pdf_filename(expected) == expected


def test_package_filename_normalization_repairs_nested_fields() -> None:
    package = {
        "human_review_required": True,
        "approval_status": "pending_human_approval",
        "pdf_filename": "report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
        "artifacts": {
            "client_filename": "report-PENDING-APPROVAL-PENDING-APPROVAL.pdf",
        },
    }
    repaired = normalize_report_artifact_filenames(package)
    assert repaired["pdf_filename"] == "report-FINAL-PENDING-APPROVAL.pdf"
    assert repaired["artifacts"]["client_filename"] == (
        "report-FINAL-PENDING-APPROVAL.pdf"
    )
    assert repaired["artifact_filename_contract"]["idempotent_pdf_filename"] is True


def test_bandit_policy_excludes_only_nonproduction_paths_and_skips_no_rules() -> None:
    policy = Path(".bandit").read_text(encoding="utf-8")
    assert "exclude =" in policy
    exclusion_line = policy.split("exclude =", 1)[1].splitlines()[0]
    excluded = {item.strip() for item in exclusion_line.split(",") if item.strip()}
    assert "tests" in excluded
    assert "nico" not in excluded
    assert "scripts" not in excluded
    assert "skips" not in policy.casefold()

    contract = install_scanner_command_repair()
    bandit = next(spec for spec in scanner_tool_runners.TOOL_SPECS if spec.name == "bandit")
    assert bandit.command[:5] == ("bandit", "-r", ".", "-f", "json")
    assert "-x" in bandit.command
    runtime_excludes = set(bandit.command[bandit.command.index("-x") + 1].split(","))
    assert runtime_excludes == excluded
    assert contract["bandit_rules_skipped"] is False


def test_gitleaks_policy_uses_defaults_without_broad_allowlists() -> None:
    policy = Path(".gitleaks.toml").read_text(encoding="utf-8")
    assert "useDefault = true" in policy
    assert "[[allowlists]]" not in policy
    assert "[allowlist]" not in policy


def test_diagnostic_fixture_contains_no_dynamic_execution_or_secret_like_literal() -> None:
    source = Path("tests/test_express_safe_trace_diagnostics.py").read_text(
        encoding="utf-8"
    )
    assert "exec(" not in source
    assert "eval(" not in source
    assert "provider-token-supersecret" not in source
    assert "FunctionType" in source
