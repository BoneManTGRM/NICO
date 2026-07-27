from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


PYTHON_HOTSPOTS = (
    ("nico/comprehensive_premium_pdf_v6.py", "_build_pdf", 121, 360),
    ("nico/comprehensive_decision_grade_markdown_v5.py", "_build_markdown", 113, 250),
    ("nico/comprehensive_decision_grade_report_v5.py", "build_comprehensive_report_package", 99, 470),
    ("nico/typescript_ast_complexity_v1.py", "_build_complexity", 99, 165),
)

TYPESCRIPT_HOTSPOTS = (
    ("apps/web/app/assessment/AssessmentWorkspace.tsx", "AssessmentWorkspace"),
    ("apps/web/app/operations/final-review/FinalReviewWorkspace.tsx", "FinalReviewWorkspace"),
    ("apps/web/app/full-run/page.tsx", "FullRunPage"),
)


class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.value = 1

    def visit_If(self, node: ast.If) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.value += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.value += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.value += len(node.handlers) + bool(node.orelse) + bool(node.finalbody)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self.value += max(0, len(node.cases) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.value += 1 + len(node.ifs)
        self.generic_visit(node)


def _function_node(path: Path, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    raise AssertionError(f"{function_name} not found in {path.relative_to(ROOT)}")


def _complexity(node: ast.AST) -> int:
    visitor = _ComplexityVisitor()
    visitor.visit(node)
    return visitor.value


@pytest.mark.parametrize("relative_path,function_name,max_complexity,max_loc", PYTHON_HOTSPOTS)
def test_python_hotspot_does_not_regress(
    relative_path: str,
    function_name: str,
    max_complexity: int,
    max_loc: int,
) -> None:
    path = ROOT / relative_path
    assert path.is_file(), f"missing Phase 4 hotspot source: {relative_path}"
    node = _function_node(path, function_name)
    measured_complexity = _complexity(node)
    measured_loc = (node.end_lineno or node.lineno) - node.lineno + 1

    assert measured_complexity <= max_complexity, (
        f"{relative_path}:{function_name} complexity regressed to {measured_complexity}; "
        f"ratchet ceiling is {max_complexity}. Extract bounded helpers instead of increasing it."
    )
    assert measured_loc <= max_loc, (
        f"{relative_path}:{function_name} grew to {measured_loc} lines; ratchet ceiling is {max_loc}."
    )


@pytest.mark.parametrize("relative_path,component_name", TYPESCRIPT_HOTSPOTS)
def test_typescript_hotspot_anchor_is_preserved(relative_path: str, component_name: str) -> None:
    path = ROOT / relative_path
    assert path.is_file(), f"missing Phase 4 hotspot source: {relative_path}"
    source = path.read_text(encoding="utf-8")
    assert component_name in source, f"durable hotspot anchor {component_name} disappeared from {relative_path}"
    assert "@ts-ignore" not in source, f"{relative_path} must not hide refactor errors with @ts-ignore"
