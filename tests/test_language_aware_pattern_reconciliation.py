from __future__ import annotations

from nico.language_aware_pattern_reconciliation import (
    _finding_path,
    _is_cross_language_python_exec_hit,
)


def test_typescript_regex_exec_is_not_python_dynamic_execution() -> None:
    note = (
        "apps/web/app/AssessmentExpressRecoveryGuard.tsx:163: "
        "python_eval_exec - Dynamic code execution should be reviewed."
    )
    assert _finding_path(note) == "apps/web/app/AssessmentExpressRecoveryGuard.tsx"
    assert _is_cross_language_python_exec_hit(note) is True


def test_javascript_regex_exec_is_language_mismatch() -> None:
    note = "apps/web/app/status.js:22: python_eval_exec - Dynamic code execution should be reviewed."
    assert _is_cross_language_python_exec_hit(note) is True


def test_python_eval_exec_remains_reviewable() -> None:
    note = "nico/worker.py:22: python_eval_exec - Dynamic code execution should be reviewed."
    assert _is_cross_language_python_exec_hit(note) is False


def test_unrelated_typescript_rule_is_not_suppressed() -> None:
    note = "apps/web/app/status.tsx:22: hardcoded_secret - Potential credential exposure."
    assert _is_cross_language_python_exec_hit(note) is False
