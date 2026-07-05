"""Phase 3 File Integrity Regression Test

Covers maturity.py and roadmap.py in addition to previous files.
"""

import py_compile
from pathlib import Path

MATURITY = Path("nico/modules/maturity.py")
ROADMAP = Path("nico/modules/roadmap.py")


def test_maturity_file_size():
    with open(MATURITY, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 60


def test_maturity_contains_assess_maturity():
    with open(MATURITY, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def assess_maturity" in content


def test_maturity_contains_vulnerability_fields():
    with open(MATURITY, "r", encoding="utf-8") as f:
        content = f.read()
    assert "critical_count" in content
    assert "high_count" in content
    assert "vulnerabilities_found" in content


def test_maturity_contains_semaphore_and_quick_wins():
    with open(MATURITY, "r", encoding="utf-8") as f:
        content = f.read()
    assert "semaphore" in content
    assert "quick_wins" in content
    assert "drivers" in content


def test_roadmap_file_size():
    with open(ROADMAP, "r", encoding="utf-8") as f:
        content = f.read()
    assert len(content.splitlines()) > 60


def test_roadmap_contains_build_roadmap():
    with open(ROADMAP, "r", encoding="utf-8") as f:
        content = f.read()
    assert "def build_roadmap" in content


def test_roadmap_contains_phases():
    with open(ROADMAP, "r", encoding="utf-8") as f:
        content = f.read()
    assert "30_days" in content
    assert "60_days" in content
    assert "90_days" in content


def test_roadmap_contains_vulnerability_fields():
    with open(ROADMAP, "r", encoding="utf-8") as f:
        content = f.read()
    assert "critical_count" in content
    assert "high_count" in content
    assert "vulnerabilities_found" in content


def test_pycompile_maturity():
    py_compile.compile(str(MATURITY), doraise=True)


def test_pycompile_roadmap():
    py_compile.compile(str(ROADMAP), doraise=True)
