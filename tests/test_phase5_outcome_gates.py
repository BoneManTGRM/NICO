from __future__ import annotations

import ast
import re
from pathlib import Path

from nico.full_assessment_complexity_evidence import _analyze_python


ROOT = Path(__file__).resolve().parents[1]
USES_PATTERN = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_PATTERN = re.compile(r"^[^/@]+/[^/@]+(?:/[^@]+)?@[0-9a-f]{40}$")


def test_all_repository_workflow_action_references_are_immutable() -> None:
    mutable: list[str] = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            match = USES_PATTERN.match(line)
            if not match:
                continue
            reference = match.group(1)
            if reference.startswith("./"):
                continue
            if not FULL_SHA_PATTERN.fullmatch(reference):
                mutable.append(f"{path.relative_to(ROOT)}:{line_number}: {reference}")

    assert not mutable, "Mutable GitHub Action references remain:\n" + "\n".join(mutable)


def test_build_complexity_is_below_report_target() -> None:
    path = ROOT / "nico" / "typescript_ast_complexity_v1.py"
    analysis = _analyze_python(str(path.relative_to(ROOT)), path.read_text(encoding="utf-8"))
    functions = {
        item["name"]: item
        for item in analysis.get("functions") or []
        if isinstance(item, dict) and item.get("name")
    }
    measured = functions["_build_complexity"]

    assert measured["cyclomatic_complexity"] <= 30, measured
    assert measured["loc"] <= 90, measured


def test_phase5_report_truth_modules_parse_and_keep_scores_evidence_bound() -> None:
    for relative in ("nico/phase5_report_truth_v1.py", "nico/phase5_report_truth_v2.py"):
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=relative)

    source = (ROOT / "nico" / "phase5_report_truth_v1.py").read_text(encoding="utf-8")
    assert '"exclude_from_maturity": True' in source
    assert '"client_delivery_allowed"] = False' in source
    assert "Only exact-SHA retained evidence changes report outcomes" in source
