from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mobile_restart_live_acceptance_v1.py"


def _fill_values_by_label(source: str) -> dict[str, list[ast.expr]]:
    tree = ast.parse(source)
    values: dict[str, list[ast.expr]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "fill" or len(node.args) != 1:
            continue
        locator_call = node.func.value
        if not isinstance(locator_call, ast.Call) or not isinstance(locator_call.func, ast.Attribute):
            continue
        if locator_call.func.attr != "get_by_label" or len(locator_call.args) != 1:
            continue
        label_node = locator_call.args[0]
        if not isinstance(label_node, ast.Constant) or not isinstance(label_node.value, str):
            continue
        values.setdefault(label_node.value, []).append(node.args[0])
    return values


def test_mobile_production_consumer_cannot_create_an_engagement() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    fills = _fill_values_by_label(source)

    assert fills == {}
    run_proof = source.split("def run_proof(", 1)[1].split(
        "def _continuation_count", 1
    )[0]
    assert "run_existing_proof(browser, args)" in run_proof
    assert ".click()" not in run_proof
    assert "comprehensive-intake" not in run_proof
    assert "_require_existing_source_args(args)" in run_proof
