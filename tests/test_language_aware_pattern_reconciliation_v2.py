from __future__ import annotations

from nico.hosted_assessment import scan_files as raw_scan_files
from nico.language_aware_pattern_reconciliation import (
    _finding_path,
    _finding_rule,
    _python_call_lines,
    install_language_aware_pattern_reconciliation,
    wrap_scan_files,
)


def test_finding_parser_retains_path_line_and_rule() -> None:
    note = "nico/example.py:14: python_shell_true — subprocess shell=True expands command-injection risk."

    assert _finding_path(note) == "nico/example.py"
    assert _finding_rule(note) == "python_shell_true"


def test_python_ast_only_retains_executable_calls_not_rule_text() -> None:
    source = '''
RULE_TEXT = "shell=True and dangerouslySetInnerHTML"
import subprocess
subprocess.run("echo ok", shell=True)
'''
    lines = _python_call_lines(source)

    assert lines["python_shell_true"] == {4}


def test_scan_filter_excludes_cross_language_and_string_literal_false_positives() -> None:
    files = {
        "nico/rules.py": 'RULE = "dangerouslySetInnerHTML shell=True"\n',
        "apps/web/app/page.tsx": 'const value = /x/.exec(input);\nconst view = <div dangerouslySetInnerHTML={{__html: safe}} />;\n',
        "nico/runner.py": 'import subprocess\nsubprocess.run(command, shell=True)\n',
    }
    wrapped = wrap_scan_files(raw_scan_files)
    result = wrapped(files)
    risks = result["risks"]

    assert not any("nico/rules.py" in item for item in risks)
    assert not any("python_eval_exec" in item and "page.tsx" in item for item in risks)
    assert any("react_dangerous_html" in item and "page.tsx" in item for item in risks)
    assert any("python_shell_true" in item and "runner.py" in item for item in risks)
    assert result["risk_pattern_filter"]["excluded_language_or_literal_mismatches"] >= 3


def test_installer_binds_hosted_and_snapshot_scan_paths() -> None:
    status = install_language_aware_pattern_reconciliation()

    assert status["scan_wrapper_bound"] is True
    assert status["python_rules_require_python_ast_call"] is True
    assert status["script_rules_require_script_extension"] is True
