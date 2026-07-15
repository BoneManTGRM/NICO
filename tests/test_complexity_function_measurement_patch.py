from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from nico import complexity_engine
from nico.complexity_function_measurement_patch import (
    CHURN_WINDOW_DAYS,
    install_complexity_function_measurement_patch,
    recent_git_churn,
)


def test_python_nested_functions_are_measured_independently() -> None:
    text = """
def outer(value):
    def inner(item):
        if item:
            for part in item:
                if part:
                    return part
        return None
    return inner(value)
"""

    result = complexity_engine._analyze_python(Path("nico/example.py"), text)

    assert result["function_count"] == 2
    assert result["function_complexity_method"] == "python_ast_function_level_v2"
    assert result["max_function_complexity"] >= 4
    assert result["max_function_complexity"] < result["cyclomatic_complexity"]
    names = {item["name"] for item in result["highest_risk_functions"]}
    assert names == {"outer", "inner"}


def test_javascript_module_aggregate_is_not_substituted_for_function_risk() -> None:
    text = "\n".join(
        f"function fn{index}(value) {{ if (value) {{ return value; }} return null; }}"
        for index in range(30)
    )

    result = complexity_engine._analyze_script(Path("apps/web/example.ts"), text)

    assert result["function_count"] == 30
    assert result["cyclomatic_complexity"] > 25
    assert result["max_function_complexity"] == 2
    assert result["function_complexity_method"] == "javascript_typescript_function_level_v2"


def test_recent_churn_uses_report_aligned_window(monkeypatch, tmp_path) -> None:
    observed: dict[str, object] = {}

    def fake_run_command(command, *, cwd, limits):
        observed["command"] = command
        observed["cwd"] = cwd
        return SimpleNamespace(ok=True, stdout="5\t3\tnico/example.py\n")

    monkeypatch.setattr(complexity_engine, "run_command", fake_run_command)

    churn = recent_git_churn(tmp_path)

    assert churn == {"nico/example.py": 8}
    assert f"--since={CHURN_WINDOW_DAYS} days ago" in observed["command"]
    assert observed["cwd"] == tmp_path


def test_profile_exposes_function_measurement_model(tmp_path) -> None:
    repo = tmp_path / "repo"
    (repo / "nico").mkdir(parents=True)
    (repo / "nico" / "service.py").write_text(
        "def service(value):\n"
        "    if value:\n"
        "        return value\n"
        "    return None\n",
        encoding="utf-8",
    )

    profile = complexity_engine.build_complexity_profile(repo)

    assert profile["scoring_model"] == "function_risk_density_v3"
    assert profile["churn_window_days"] == 180
    assert "python_ast_function_level_v2" in profile["function_measurement_methods"]
    assert profile["max_function_cyclomatic_complexity"] >= 2
    assert any("Function-level complexity measurement completed" in item for item in profile["evidence"])


def test_installation_is_idempotent() -> None:
    first = install_complexity_function_measurement_patch()
    second = install_complexity_function_measurement_patch()

    assert first["churn_window_days"] == 180
    assert second["churn_window_days"] == 180
    assert second["module_aggregate_used_as_function_risk"] is False
