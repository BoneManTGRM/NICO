from __future__ import annotations

import nico.assessment_score_integrity as score_integrity
from nico.typescript_complexity_syntax import count_runtime_branches, install_typescript_complexity_syntax


def test_optional_properties_and_parameters_are_not_runtime_branches() -> None:
    text = """
    type Result = {
      status?: string;
      error?: { message?: string };
    };
    function read(value?: Result): string | undefined {
      return value?.status;
    }
    """

    assert count_runtime_branches(text) == 0


def test_runtime_branches_remain_counted_without_double_counting_optional_chaining() -> None:
    text = """
    const answer = enabled ? primary : fallback;
    const selected = value ?? fallback;
    if (selected && ready || forced) {
      run();
    }
    const nested = object?.child;
    """

    # ternary + nullish + if + && + ||
    assert count_runtime_branches(text) == 5


def test_installer_rebinds_function_level_analyzer_branch_counter() -> None:
    result = install_typescript_complexity_syntax()

    assert result["version"] == "nico-typescript-complexity-syntax-v1"
    assert score_integrity._branch_count("type A = { value?: string }") == 0
    assert score_integrity._branch_count("const value = condition ? a : b") == 1
