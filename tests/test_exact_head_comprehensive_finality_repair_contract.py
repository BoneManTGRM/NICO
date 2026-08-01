from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "exact-head-comprehensive-finality-repair.md"
WORKFLOW = ROOT / ".github" / "workflows" / "diagnose-main-comprehensive-finality.yml"


def test_exact_head_finality_repair_preserves_release_and_delivery_boundaries() -> None:
    text = PLAN.read_text(encoding="utf-8")

    assert "Workstream 1 production stability" in text
    assert "Do not suppress or convert a genuine invariant failure into success." in text
    assert "Do not alter technical or evidence-adjusted scores" in text
    assert "Keep expert review mandatory and client delivery blocked before approval." in text
    assert "All pull-request checks pass on one immutable head." in text
    assert "Required post-merge production acceptance, mobile restart, and iOS WebKit proofs pass." in text


def test_diagnostic_workflow_is_read_only_and_exact_run_bounded() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "permissions:\n  contents: read" in source
    assert "comprun_4f6516ebad254c0a816c6e3282a00da7" in source
    assert "/report/json" in source
    assert "/report/markdown" in source
    assert "/report/html" in source
    assert "/report/pdf" in source
    assert "curl --fail-with-body" in source
    assert "client_delivery_allowed" not in source
