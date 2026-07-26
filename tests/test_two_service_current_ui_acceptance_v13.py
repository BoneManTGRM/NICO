from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WRAPPER = SCRIPTS / "two_service_live_acceptance_v3.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "test_two_service_live_acceptance_current_ui_v13",
        WRAPPER,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_run_proof_uses_registered_terminal_phases_and_current_labels() -> None:
    source = WRAPPER.read_text(encoding="utf-8")

    assert 'state["phase_label"] in acceptance.TERMINAL_PHASES' in source
    assert 'state["phase_label"] in {"Complete", "Human review required"}' not in source
    assert "Expert review required" in source
    assert "Se requiere revisión experta" in source
    assert "Exact commit" in source
    assert "Evidence scanners" in source
    assert "Assessment package" in source
    assert "Expert review" in source
    assert "Technical maturity" in source


def test_current_ui_state_preserves_exact_rendered_review_phase() -> None:
    module = _module()

    class Page:
        url = "https://app.nicoaudit.com/assessment?tier=comprehensive"

        def evaluate(self, _script):
            return {
                "phase_label": "Expert review required",
                "message": "Technical analysis and report preparation are complete.",
                "run_id": "comprun_exact",
                "commit_sha": "a" * 40,
                "scanner": "Complete",
                "report": "Complete",
                "review": "Expert review required",
                "score": "Senior · 91/100",
                "page_url": self.url,
            }

    state = module._current_ui_state(Page())

    assert state["phase_label"] == "Expert review required"
    assert state["run_id"] == "comprun_exact"
    assert state["commit_sha"] == "a" * 40
    assert state["scanner"] == "Complete"
    assert state["report"] == "Complete"
    assert state["review"] == "Expert review required"
    assert state["score"] == "Senior · 91/100"


def test_font_timeout_does_not_override_structured_acceptance_evidence(tmp_path: Path) -> None:
    module = _module()

    class Page:
        def screenshot(self, **_kwargs):
            raise TimeoutError("waiting for fonts to load")

    result = module._capture_optional_screenshot(Page(), tmp_path / "proof.png")

    assert result["screenshot"] == ""
    assert result["screenshot_sha256"] == ""
    assert "TimeoutError" in result["screenshot_error"]
    assert "fonts" in result["screenshot_error"]


def test_runtime_override_installs_current_ui_and_run_proof() -> None:
    module = _module()

    module._apply_runtime_overrides()

    assert module._impl._safe_ui_state is module._current_ui_state
    assert module._impl._original_run_service is module._current_run_service
