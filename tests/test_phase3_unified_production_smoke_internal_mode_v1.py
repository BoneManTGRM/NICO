from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3.py"


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


def test_unified_production_acceptance_keeps_client_engagement_fields_blank() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    fills = _fill_values_by_label(source)

    for label in ("Client name, optional", "Project name, optional"):
        assert label in fills, f"unified production proof no longer controls {label!r}"
        assert len(fills[label]) == 1, f"expected one unified-proof fill for {label!r}"
        value = fills[label][0]
        assert isinstance(value, ast.Constant) and value.value == "", (
            f"{label!r} must stay blank so the automated unified production proof remains "
            "an internal assessment instead of fabricating Phase 3 client-engagement context"
        )

    assert "Production Acceptance Pass" not in source
    assert "NICO {service.title()} Acceptance" not in source
