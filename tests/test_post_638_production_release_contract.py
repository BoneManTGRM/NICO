from __future__ import annotations

from nico import express_terminal_truth_patch as terminal_truth
from nico.express_decision_quality_v17 import normalize_express_decision_quality

MERGED_BASE_SHA = "dbbca3671e8620d115ac25cbbbf2c74f25f28a90"


def test_terminal_complete_requires_durable_record_and_terminal_truth_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        terminal_truth,
        "_storage_truth",
        lambda: {
            "recorded": True,
            "durable": True,
            "durability_verified": True,
            "adapter": "postgres",
            "label": "Recorded and durable",
            "warning": "",
        },
    )
    payload = {
        "status": "complete",
        "state": "complete",
        "complete": True,
        "completed": True,
        "terminal": True,
        "progress_percent": 100,
        "steps": [
            {"name": "Report generation", "status": "complete"},
            {"name": "Truth and review gates", "status": "complete"},
        ],
    }
    reconciled = terminal_truth.reconcile_terminal_truth(payload)
    assert reconciled["status"] == "complete"
    assert reconciled["progress_percent"] == 100
    assert reconciled["durability_verified"] is True
    assert reconciled.get("completion_blockers", []) == []


def test_terminal_complete_is_blocked_when_truth_gate_is_running(monkeypatch) -> None:
    monkeypatch.setattr(
        terminal_truth,
        "_storage_truth",
        lambda: {
            "recorded": True,
            "durable": True,
            "durability_verified": True,
            "adapter": "postgres",
            "label": "Recorded and durable",
            "warning": "",
        },
    )
    payload = {
        "status": "complete",
        "complete": True,
        "progress_percent": 100,
        "steps": [{"name": "Truth and review gates", "status": "running"}],
    }
    reconciled = terminal_truth.reconcile_terminal_truth(payload)
    assert reconciled["status"] == "finalizing"
    assert reconciled["complete"] is False
    assert reconciled["progress_percent"] == 99
    assert "truth_and_review_gates_nonterminal" in reconciled["completion_blockers"]


def test_terminal_complete_is_blocked_when_record_is_not_durable(monkeypatch) -> None:
    monkeypatch.setattr(
        terminal_truth,
        "_storage_truth",
        lambda: {
            "recorded": True,
            "durable": False,
            "durability_verified": False,
            "adapter": "sqlite",
            "label": "Recorded, not durable",
            "warning": "ephemeral storage",
        },
    )
    payload = {
        "status": "complete",
        "complete": True,
        "progress_percent": 100,
        "steps": [{"name": "Truth and review gates", "status": "complete"}],
    }
    reconciled = terminal_truth.reconcile_terminal_truth(payload)
    assert reconciled["status"] == "finalizing"
    assert reconciled["complete"] is False
    assert reconciled["progress_percent"] == 99
    assert "durable_record_unverified" in reconciled["completion_blockers"]


def test_express_normalization_publishes_release_verification_metadata() -> None:
    result = {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"score": 90, "level": "Senior"},
        "evidence_adjusted_score": 68,
        "sections": [],
        "score_contributions": [
            {"control": "Code Audit", "presented_score": 86},
            {"control": "Client / Human Acceptance", "presented_score": 0},
        ],
    }
    normalized = normalize_express_decision_quality(result)
    quality = normalized["express_decision_quality"]
    assert quality["score_bars_use_proportional_geometry"] is True
    assert quality["architecture_velocity_page_boundary"] is True
    assert quality["scanner_worker_is_supplemental"] is True
    assert normalized["score_contributions"][0]["bar_geometry"]["width"] == 103.2
    assert normalized["score_contributions"][1]["bar_geometry"]["width"] == 0.0
