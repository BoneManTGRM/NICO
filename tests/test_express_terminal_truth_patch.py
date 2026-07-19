from __future__ import annotations

from nico import express_terminal_truth_patch as patch


def test_complete_is_rejected_while_truth_gate_is_running(monkeypatch):
    monkeypatch.setattr(
        patch,
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
    result = patch.reconcile_terminal_truth(
        {
            "status": "completed",
            "complete": True,
            "progress_percent": 100,
            "steps": [
                {"title": "Report generation", "status": "complete"},
                {"title": "Truth and review gates", "status": "running"},
                {"title": "Complete", "status": "complete"},
            ],
        }
    )
    assert result["status"] == "finalizing"
    assert result["complete"] is False
    assert result["progress_percent"] == 99
    assert "truth_and_review_gates_nonterminal" in result["completion_blockers"]


def test_complete_is_rejected_when_record_is_not_durable(monkeypatch):
    monkeypatch.setattr(
        patch,
        "_storage_truth",
        lambda: {
            "recorded": True,
            "durable": False,
            "durability_verified": False,
            "adapter": "sqlite",
            "label": "Recorded, not durable",
            "warning": "volume not verified",
        },
    )
    result = patch.reconcile_terminal_truth(
        {
            "status": "complete",
            "complete": True,
            "steps": [{"title": "Truth and review gates", "status": "complete"}],
        }
    )
    assert result["status"] == "finalizing"
    assert result["evidence_readiness"] == "pending"
    assert result["durable_record"]["label"] == "Recorded, not durable"
    assert "durable_record_unverified" in result["completion_blockers"]


def test_scanner_worker_is_supplemental_but_mapped(monkeypatch):
    monkeypatch.setattr(
        patch,
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
    result = patch.reconcile_terminal_truth(
        {
            "status": "running",
            "sections": [
                {
                    "id": "scanner_worker_evidence",
                    "title": "Scanner Worker Evidence",
                    "status": "gray",
                }
            ],
        }
    )
    scanner = result["sections"][0]
    assert scanner["directly_scored"] is False
    assert scanner["mapped_to_scored_controls"] is True
    assert scanner["gray_not_scored"] is False
    assert scanner["display_status"] == "SUPPLEMENTAL · MAPPED TO SCORED CONTROLS"


def test_completed_with_terminal_gate_and_durable_record_remains_complete(monkeypatch):
    monkeypatch.setattr(
        patch,
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
    result = patch.reconcile_terminal_truth(
        {
            "status": "completed",
            "complete": True,
            "steps": [{"title": "Truth and review gates", "status": "complete"}],
        }
    )
    assert result["status"] == "completed"
    assert result["complete"] is True
    assert result["completion_state_reconciled"] is False
