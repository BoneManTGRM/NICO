from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHA = "d" * 40


def _module():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module("unified_production_acceptance_authoritative")


def test_authoritative_reader_is_bound_at_every_runtime_override_layer(monkeypatch):
    module = _module()
    observed: dict[str, bool] = {}

    def delegated_main(argv):
        observed.update(
            canonical=module.production.canonical_ui_state is module.authoritative_ui_state,
            acceptance=module.production.acceptance.ui_state is module.authoritative_ui_state,
            current=module.production.unified._current_ui_state is module.authoritative_ui_state,
            implementation=module.production.unified._impl._safe_ui_state is module.authoritative_ui_state,
        )
        assert argv == ["--passes", "2"]
        return 17

    monkeypatch.setattr(module.production, "main", delegated_main)
    assert module.main(["--passes", "2"]) == 17
    assert observed == {
        "canonical": True,
        "acceptance": True,
        "current": True,
        "implementation": True,
    }


def test_authoritative_reader_recovers_exact_identity_from_proof_url(monkeypatch):
    module = _module()
    run_id = "comprun_authoritative_identity"
    url = (
        "https://app.nicoaudit.com/assessment?"
        f"expected_commit_sha={SHA}&run_id={run_id}&tier=comprehensive"
    )

    class Page:
        def __init__(self):
            self.url = url

        def evaluate(self, _script):
            return {}

    monkeypatch.setattr(
        module,
        "_ORIGINAL_UI_STATE",
        lambda page: {
            "phase_label": "Internal review required",
            "message": "The automated assessment is complete.",
            "run_id": "",
            "commit_sha": "",
            "scanner": "",
            "report": "Complete",
            "review": "",
            "score": "Moderate · 72/100",
            "page_url": page.url,
        },
    )

    state = module.authoritative_ui_state(Page())
    assert state["run_id"] == run_id
    assert state["commit_sha"] == SHA
    assert state["scanner"] == "Complete with disclosed limitations"
    assert state["review"] == "Required"
    assert state["report"] == "Complete"
