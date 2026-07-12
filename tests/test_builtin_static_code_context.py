from __future__ import annotations

from pathlib import Path

import nico.assessment_score_integrity as integrity
import nico.builtin_static_code_context as context


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_production_executable_code_hit_remains_material(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "nico/runtime.py",
        "def execute(user_input: str):\n    return eval(user_input)\n",
    )

    result = context.triaged_builtin_static_scan(tmp_path)

    assert result["status"] == "failed"
    assert result["finding_count"] == 1
    assert result["material_finding_count"] == 1
    assert result["test_only_finding_count"] == 0
    assert result["findings_by_rule"] == {"python_eval_exec": 1}
    assert "nico/runtime.py:2" in result["safe_output_preview"]


def test_comments_strings_and_detector_definitions_do_not_become_material(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "nico/detectors.py",
        """import re

# eval(user_input) is intentionally documented as an unsafe example.
EXAMPLE = "os.system(command) and shell=True"
PATTERN = re.compile(r"\\b(eval|exec)\\s*\\(")

def safe(value: str) -> str:
    return value
""",
    )

    result = context.triaged_builtin_static_scan(tmp_path)

    assert result["status"] == "passed"
    assert result["finding_count"] == 0
    assert result["material_finding_count"] == 0
    assert result["test_only_finding_count"] == 0
    assert result["code_context_masking"] is True


def test_non_production_executable_hit_is_disclosed_but_not_scored(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "tests/test_unsafe_example.py",
        "def demonstrate(payload: str):\n    return eval(payload)\n",
    )

    result = context.triaged_builtin_static_scan(tmp_path)

    assert result["status"] == "passed"
    assert result["finding_count"] == 0
    assert result["material_finding_count"] == 0
    assert result["test_only_finding_count"] == 1
    assert result["total_finding_count"] == 1
    assert result["excluded_findings_by_rule"] == {"python_eval_exec": 1}
    assert "Excluded non-production findings: 1" in result["safe_output_preview"]


def test_javascript_comments_and_strings_are_masked_but_code_is_scored(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "apps/web/safe.ts",
        "// element.innerHTML = unsafe\nconst example = 'dangerouslySetInnerHTML';\nexport const safe = true;\n",
    )
    _write(
        tmp_path,
        "apps/web/runtime.ts",
        "export function render(element: HTMLElement, html: string) {\n  element.innerHTML = html;\n}\n",
    )

    result = context.triaged_builtin_static_scan(tmp_path)

    assert result["status"] == "failed"
    assert result["material_finding_count"] == 1
    assert result["findings_by_rule"] == {"js_inner_html": 1}


def test_installer_rebinds_integrity_scanner_idempotently(monkeypatch) -> None:
    monkeypatch.setattr(integrity, "_nico_builtin_static_code_context_installed", False, raising=False)
    monkeypatch.setattr(integrity, "_built_in_static_scan", context._ORIGINAL_BUILTIN_STATIC_SCAN)

    first = context.install_builtin_static_code_context()
    second = context.install_builtin_static_code_context()

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert integrity._built_in_static_scan is context.triaged_builtin_static_scan
    assert first["version"] == context.BUILTIN_STATIC_CONTEXT_VERSION
