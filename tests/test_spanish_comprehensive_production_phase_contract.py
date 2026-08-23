from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v1.py"


def _string_constants() -> dict[str, str]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    values: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            values[target.id] = value.value
    return values


class SpanishComprehensiveProductionPhaseContractTests(unittest.TestCase):
    def test_terminal_phase_matches_the_live_review_boundary(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        values = _string_constants()

        self.assertEqual(
            values["SPANISH_TERMINAL_PHASE"],
            "Se requiere revisión experta",
        )
        self.assertNotIn(
            'SPANISH_TERMINAL_PHASE = "Revisión interna requerida"',
            source,
        )
        self.assertIn(
            'assert terminal.get("phase") == SPANISH_TERMINAL_PHASE',
            source,
        )


if __name__ == "__main__":
    unittest.main()
