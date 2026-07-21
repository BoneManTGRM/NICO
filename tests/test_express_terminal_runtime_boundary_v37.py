from __future__ import annotations

from pathlib import Path

from nico.express_terminal_runtime_boundary_v37 import VERSION, install_express_terminal_runtime_boundary_v37


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_boundary_preserves_legacy_score_without_second_deduction() -> None:
    install_express_terminal_runtime_boundary_v37()
    from nico import express_evidence_specific_scoring_v33 as scoring

    result = {
        "maturity_signal": {"level": "Senior", "score": 82},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "yellow",
                "score": 74,
                "findings": ["A retained review finding."],
                "evidence": [],
                "unavailable": [],
            }
        ],
    }

    records, overall = scoring.reconcile_express_scores(result)

    assert records == []
    assert overall == 74
    assert result["sections"][0]["presented_score"] == 74
    assert result["sections"][0]["score_deductions"] == []


def test_runtime_boundary_is_installed_after_v36() -> None:
    source = (ROOT / "nico" / "express_live_renderer_binding_v22.py").read_text(encoding="utf-8")

    assert "install_express_terminal_runtime_boundary_v37" in source
    assert source.index("terminal_report_compat = install_express_terminal_report_compat_v36()") < source.index(
        "terminal_runtime_boundary = install_express_terminal_runtime_boundary_v37()"
    )
    assert VERSION == "nico.express_terminal_runtime_boundary.v37"
