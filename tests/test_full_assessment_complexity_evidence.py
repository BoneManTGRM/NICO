from __future__ import annotations

from nico.full_assessment_complexity_evidence import collect_complexity_evidence


def test_complexity_evidence_measures_ast_hotspots_coupling_and_duplicates() -> None:
    repeated_body = """
    first = value + 1
    second = first * 2
    third = second - 3
    fourth = third / 4
    fifth = fourth + 5
    return fifth
"""
    files = {
        "nico/alpha.py": """
from nico.storage import STORE

def simple(value):
    return value + 1

def branching(value):
    if value > 0:
        for item in range(value):
            if item % 2:
                value += item
            elif item > 10:
                value -= item
    return value

def duplicate_alpha(value):
""" + repeated_body,
        "nico/beta.py": """
from .alpha import simple

def duplicate_beta(value):
""" + repeated_body,
        "apps/web/example.ts": """
import helper from './helper'
export function choose(value: number) {
  if (value > 10 && value < 20) {
    return value
  }
  return value ? value + 1 : 0
}
""",
        "tests/test_alpha.py": "def test_alpha():\n    assert True\n",
        "README.md": "# ignored",
    }

    result = collect_complexity_evidence(files)

    assert result["status"] == "attached"
    assert result["files_considered"] == 3
    assert result["files_analyzed"] == 3
    assert result["python_files_analyzed"] == 2
    assert result["javascript_typescript_files_analyzed"] == 1
    assert result["functions_measured"] >= 5
    assert result["average_cyclomatic_complexity"] is not None
    assert result["maximum_cyclomatic_complexity"] >= 4
    assert result["import_edges"] >= 3
    assert result["internal_import_edges"] >= 3
    assert result["maximum_fan_out"] >= 1
    assert result["duplicate_evidence"]["duplicate_block_groups"] >= 1
    assert result["duplicate_evidence"]["duplicate_line_ratio"] > 0
    assert result["duplicate_evidence"]["samples"]
    assert all("tests/test_alpha.py" not in str(item) for item in result["hotspots"])
    assert any(
        "bounded lexical heuristic" in note or "bounded function-level lexical extraction" in note
        for note in result["unavailable_data_notes"]
    )
    assert result["analyzer_version"] in {
        "nico-bounded-complexity-v1",
        "nico-bounded-complexity-v2",
    }
    assert "source contents are not stored" in result["retention_note"]
    assert result["human_review_required"] is True


def test_python_parse_failure_is_disclosed_and_excluded() -> None:
    result = collect_complexity_evidence(
        {
            "nico/good.py": "def good(value):\n    return value\n",
            "nico/bad.py": "def broken(:\n    return 1\n",
        }
    )

    assert result["status"] == "attached"
    assert result["files_considered"] == 2
    assert result["files_analyzed"] == 1
    assert result["python_parse_failures"] == 1
    assert result["parse_notes"]
    assert any("could not be parsed" in note for note in result["unavailable_data_notes"])


def test_no_eligible_source_files_returns_unavailable_evidence() -> None:
    result = collect_complexity_evidence(
        {
            "README.md": "# docs",
            "tests/test_only.py": "def test_only():\n    assert True\n",
            "dist/app.js": "if (true) {}",
        }
    )

    assert result["status"] == "unavailable"
    assert result["files_considered"] == 0
    assert result["files_analyzed"] == 0
    assert result["functions_measured"] == 0
    assert any("No eligible source files" in note for note in result["unavailable_data_notes"])
