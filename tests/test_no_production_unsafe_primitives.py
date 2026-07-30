from __future__ import annotations

import ast
from pathlib import Path

PRODUCTION_ROOTS = (Path("nico"), Path("scripts"))
EXCLUDED_SEGMENTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "coverage",
    "generated",
    "vendor",
    "vendors",
    "fixtures",
}


def _production_python_files() -> list[Path]:
    files: list[Path] = []
    for root in PRODUCTION_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(segment in EXCLUDED_SEGMENTS for segment in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def test_production_code_has_no_eval_exec_or_disabled_tls_verification() -> None:
    violations: list[str] = []
    for path in _production_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            call_name = _name(node.func)
            if call_name in {"eval", "exec", "builtins.eval", "builtins.exec"}:
                violations.append(f"{path}:{node.lineno}: prohibited dynamic execution: {call_name}")
            if call_name.endswith("_create_unverified_context"):
                violations.append(f"{path}:{node.lineno}: unverified TLS context")
            for keyword in node.keywords:
                if keyword.arg != "verify":
                    continue
                if isinstance(keyword.value, ast.Constant) and keyword.value.value is False:
                    violations.append(f"{path}:{node.lineno}: TLS verification disabled")

    assert not violations, "\n".join(violations)
