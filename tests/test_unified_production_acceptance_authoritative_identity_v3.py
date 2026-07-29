from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

module = importlib.import_module("unified_production_acceptance_authoritative")


class _Page:
    url = (
        "https://app.nicoaudit.com/assessment?tier=comprehensive"
        "&expected_commit_sha=" + "a" * 40
        + "&run_id=comprun_authoritative#assessment"
    )

    def evaluate(self, _script: str):
        return {
            "run_id": "",
            "commit_sha": "",
            "scanner": "",
            "review": "",
            "report": "Complete",
        }


def test_authoritative_ui_state_uses_exact_url_identity_and_terminal_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        module,
        "_ORIGINAL_UI_STATE",
        lambda _page: {
            "phase_label": "Internal review required",
            "message": "Complete",
            "run_id": "",
            "commit_sha": "",
            "scanner": "",
            "report": "Complete",
            "review": "",
            "score": "Moderate · 72/100",
            "page_url": _Page.url,
        },
    )

    state = module.authoritative_ui_state(_Page())

    assert state["run_id"] == "comprun_authoritative"
    assert state["commit_sha"] == "a" * 40
    assert state["scanner"] == "Complete with disclosed limitations"
    assert state["review"] == "Required"


def test_authoritative_run_service_keeps_reader_bound_for_terminal_read(monkeypatch: pytest.MonkeyPatch):
    sentinel = lambda _page: {"run_id": "legacy"}
    monkeypatch.setattr(module.production.acceptance, "ui_state", sentinel)
    observed = {}

    def fake_run_service(browser, config, pass_number, service):
        observed["reader"] = module.production.acceptance.ui_state
        observed["arguments"] = (browser, config, pass_number, service)
        return {"status": "passed"}

    monkeypatch.setattr(module, "_ORIGINAL_RUN_SERVICE", fake_run_service)

    result = module.authoritative_run_service("browser", "config", 1, "comprehensive")

    assert result == {"status": "passed"}
    assert observed["reader"] is module.authoritative_ui_state
    assert observed["arguments"] == ("browser", "config", 1, "comprehensive")
    assert module.production.acceptance.ui_state is sentinel


def test_install_binds_authoritative_reader_and_run_wrapper(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module.production, "canonical_ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.acceptance, "ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.unified, "_current_ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.unified._impl, "_safe_ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.unified, "_current_run_service", lambda *args: {})
    monkeypatch.setattr(module.production.unified._impl, "_original_run_service", lambda *args: {})

    module.install_authoritative_identity_reader()

    assert module.production.canonical_ui_state is module.authoritative_ui_state
    assert module.production.acceptance.ui_state is module.authoritative_ui_state
    assert module.production.unified._current_ui_state is module.authoritative_ui_state
    assert module.production.unified._impl._safe_ui_state is module.authoritative_ui_state
    assert module.production.unified._current_run_service is module.authoritative_run_service
    assert module.production.unified._impl._original_run_service is module.authoritative_run_service
