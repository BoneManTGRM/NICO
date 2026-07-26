from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WRAPPER = SCRIPTS / "two_service_live_acceptance_v3.py"
IMPLEMENTATION = SCRIPTS / "two_service_live_acceptance_v3_impl.py"
COPY = ROOT / "apps" / "web" / "app" / "assessment" / "assessmentCopy.ts"


def _module():
    spec = importlib.util.spec_from_file_location(
        "test_two_service_live_acceptance_review_terminal_v12",
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


def test_current_bilingual_review_required_copy_is_terminal() -> None:
    module = _module()
    copy_source = COPY.read_text(encoding="utf-8")
    expected = {
        "Expert review required",
        "Se requiere revisión experta",
    }

    installed = module.install_current_review_terminal_phases()

    assert expected <= installed
    assert {
        "Complete",
        "Human review required",
        "Run failed or blocked",
        "Continuation timed out",
    } <= installed
    for label in expected:
        assert label in copy_source


def test_wrapper_delegates_to_complete_existing_acceptance_implementation(monkeypatch) -> None:
    module = _module()
    implementation_source = IMPLEMENTATION.read_text(encoding="utf-8")
    observed: dict[str, object] = {}

    def delegated(argv):
        observed["argv"] = argv
        observed["terminal_phases"] = set(module.acceptance.TERMINAL_PHASES)
        return 17

    monkeypatch.setattr(module.runtime, "main", delegated)

    assert module.main(["--passes", "2"]) == 17
    assert observed["argv"] == ["--passes", "2"]
    assert module.CURRENT_REVIEW_TERMINAL_PHASES <= observed["terminal_phases"]
    assert "UI_BACKEND_RECONCILIATION_SECONDS" in implementation_source
    assert "runtime._wait_for_service_terminal = _wait_for_service_terminal" in implementation_source
    assert "runtime.run_service = _run_service_at_expected_commit" in implementation_source
    assert len(implementation_source.splitlines()) > 400
