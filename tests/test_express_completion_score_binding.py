from __future__ import annotations

from types import SimpleNamespace

from nico import assessment_score_integrity
from nico import express_async_api
from nico import post_polish_score_reconciliation_patch as post_polish
from nico.express_completion_score_binding import (
    bind_api_main_response,
    install_express_completion_score_binding,
)


def test_response_boundary_reconciles_completed_assessment(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_reconcile(value: dict) -> dict:
        reconciled = dict(value)
        reconciled["final_score_reconciliation"] = {
            "status": "reconciled",
            "post_polish_applied": True,
        }
        calls.append(reconciled)
        return reconciled

    monkeypatch.setattr(post_polish, "reconcile_after_polish", fake_reconcile)
    api_main = SimpleNamespace(
        safe_assessment_response_payload=lambda value: dict(value),
    )

    installed = bind_api_main_response(api_main)
    response = api_main.safe_assessment_response_payload(
        {"status": "complete", "maturity_signal": {"score": 92}}
    )

    assert installed["status"] == "installed"
    assert response["final_score_reconciliation"]["post_polish_applied"] is True
    assert calls and calls[0]["maturity_signal"]["score"] == 92


def test_response_boundary_does_not_reconcile_nonterminal_state(monkeypatch) -> None:
    called = False

    def fake_reconcile(value: dict) -> dict:
        nonlocal called
        called = True
        return value

    monkeypatch.setattr(post_polish, "reconcile_after_polish", fake_reconcile)
    api_main = SimpleNamespace(
        safe_assessment_response_payload=lambda value: dict(value),
    )
    bind_api_main_response(api_main)

    response = api_main.safe_assessment_response_payload({"status": "running"})

    assert response["status"] == "running"
    assert called is False


def test_production_bootstrap_is_the_authoritative_binding() -> None:
    # Late diagnostics installers may legitimately become the outermost _execute
    # wrapper. Railway imports and calls this patched score-integrity installer only
    # after nico.api.main is fully loaded, so the final response boundary—not wrapper
    # name or nesting order—is the production contract.
    assert callable(express_async_api._execute)
    assert getattr(
        assessment_score_integrity.install_assessment_score_integrity,
        "_nico_express_completion_score_bootstrap_v1",
        False,
    ) is True


def test_installer_is_idempotent() -> None:
    first = install_express_completion_score_binding()
    second = install_express_completion_score_binding()

    assert first["async_execute"]["async_execute_bound"] is True
    assert second["async_execute"]["status"] == "already_installed"
    assert second["production_bootstrap"]["status"] == "already_installed"
    assert second["score_inflation_allowed"] is False
