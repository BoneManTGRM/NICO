from __future__ import annotations

from types import SimpleNamespace

import nico.production_score_endpoint_binding as binding


def test_binding_reconciles_after_acceptance_gate(monkeypatch) -> None:
    order: list[str] = []

    def acceptance_gate(result: dict) -> dict:
        order.append("acceptance")
        updated = dict(result)
        updated["client_acceptance_attached"] = True
        return updated

    def reconcile(result: dict) -> dict:
        order.append("reconcile")
        updated = dict(result)
        updated["maturity_signal"] = {"level": "Senior", "score": 92}
        updated["post_polish_reconciled"] = True
        return updated

    target = SimpleNamespace(attach_client_acceptance_gate=acceptance_gate)
    monkeypatch.setattr(binding, "reconcile_after_polish", reconcile)

    installed = binding.install_production_score_endpoint_binding(target)
    result = target.attach_client_acceptance_gate({"status": "complete"})

    assert installed["status"] == "installed"
    assert installed["final_mutation_stage"] is True
    assert order == ["acceptance", "reconcile"]
    assert result["client_acceptance_attached"] is True
    assert result["post_polish_reconciled"] is True
    assert result["maturity_signal"]["score"] == 92


def test_binding_is_idempotent(monkeypatch) -> None:
    calls = {"acceptance": 0, "reconcile": 0}

    def acceptance_gate(result: dict) -> dict:
        calls["acceptance"] += 1
        return dict(result)

    def reconcile(result: dict) -> dict:
        calls["reconcile"] += 1
        return dict(result)

    target = SimpleNamespace(attach_client_acceptance_gate=acceptance_gate)
    monkeypatch.setattr(binding, "reconcile_after_polish", reconcile)

    first = binding.install_production_score_endpoint_binding(target)
    second = binding.install_production_score_endpoint_binding(target)
    target.attach_client_acceptance_gate({"status": "complete"})

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert calls == {"acceptance": 1, "reconcile": 1}


def test_binding_preserves_human_review_and_client_ready_flags(monkeypatch) -> None:
    def acceptance_gate(result: dict) -> dict:
        updated = dict(result)
        updated["human_review_required"] = True
        updated["client_ready"] = False
        return updated

    def reconcile(result: dict) -> dict:
        updated = dict(result)
        updated["score_source_of_truth"] = {
            "final_stage": "post_polish_score_reconciliation",
            "score": 92,
        }
        return updated

    target = SimpleNamespace(attach_client_acceptance_gate=acceptance_gate)
    monkeypatch.setattr(binding, "reconcile_after_polish", reconcile)
    binding.install_production_score_endpoint_binding(target)

    result = target.attach_client_acceptance_gate({"status": "complete"})

    assert result["human_review_required"] is True
    assert result["client_ready"] is False
    assert result["score_source_of_truth"]["score"] == 92
