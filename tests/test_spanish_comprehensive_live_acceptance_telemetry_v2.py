from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "spanish_comprehensive_live_acceptance_v2.py"
)


def _load_module() -> Any:
    recovery = types.ModuleType("mobile_restart_live_acceptance_v1")
    recovery.BROWSER_PROJECTION_HEADER = "X-NICO-Browser-Projection"
    recovery.BROWSER_PROJECTION_VALUE = "terminal-manifest-v1"
    recovery.TERMINAL_PHASES = {
        "Internal review required",
        "Revisión interna requerida",
    }
    recovery._wait_for_terminal = lambda *args, **kwargs: None
    recovery._ui_state = lambda page: dict(page.ui)

    proof = types.ModuleType("spanish_comprehensive_live_acceptance_v1")
    proof.main = lambda argv=None: 0

    sys.modules[recovery.__name__] = recovery
    sys.modules[proof.__name__] = proof
    module_name = "spanish_comprehensive_live_acceptance_v2_under_test"
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class _Page:
    def __init__(self, clock: _Clock, *, run_id: str = "comprun_test") -> None:
        self.clock = clock
        self.ui = {
            "phase": "Evaluación en curso",
            "run_id": run_id,
            "commit_sha": "a" * 40,
            "report": "Generando el informe final de evaluación",
            "review": "Comienza después de preparar el informe",
            "score": "Se calcula después de la puntuación",
        }

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.clock.advance(milliseconds / 1_000)


def _terminal_payload(*, status: str, state: str, reason: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "current_stage": "final_comprehensive_report_generation",
        "progress_percent": 82.61,
        "terminal": True,
        "active_stage_execution": {
            "state": state,
            "stage_id": "final_comprehensive_report_generation",
            "worker_model": "isolated_subprocess",
        },
    }
    if reason:
        payload["worker_failure"] = {
            "reason": reason,
            "worker_model": "isolated_subprocess",
        }
    return payload


def test_backend_terminal_failure_returns_exact_reason() -> None:
    module = _load_module()
    reason = "v2_production_publication_failed:ValueError:missing Spanish translation"
    snapshot = {
        "lifecycle": {"terminal": True, "status": "blocked"},
        "active_stage_execution": {"state": "blocked"},
        "failure": {"reason": reason},
    }

    assert module._backend_terminal_failure(snapshot) == reason


def test_nonterminal_backend_does_not_trigger_failure() -> None:
    module = _load_module()
    snapshot = {
        "lifecycle": {"terminal": False, "status": "running"},
        "active_stage_execution": {"state": "rendering"},
        "failure": {"reason": "final_report_background_publication_in_progress"},
    }

    assert module._backend_terminal_failure(snapshot) == ""


def test_terminal_success_does_not_bypass_ui_and_artifact_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    clock = _Clock()
    page = _Page(clock)
    emitted: list[dict[str, Any]] = []
    payload = _terminal_payload(status="complete", state="complete")

    monkeypatch.setattr(module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(module, "_fetch_run_payload", lambda page, run_id: payload)
    monkeypatch.setattr(module, "_emit", lambda snapshot: emitted.append(snapshot))
    monkeypatch.setattr(module, "_telemetry_seconds", lambda: 5.0)

    with pytest.raises(AssertionError, match="Timed out waiting for terminal Spanish run"):
        module._wait_for_terminal_with_telemetry(page, "comprun_test", 2.0)

    assert emitted[-1]["lifecycle"]["terminal"] is True
    assert emitted[-1]["status"] == "timed_out"


def test_wait_fails_fast_when_backend_is_terminal_but_ui_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    clock = _Clock()
    page = _Page(clock)
    emitted: list[dict[str, Any]] = []
    reason = "v2_production_publication_failed:ValueError:missing Spanish translation"
    payload = _terminal_payload(status="blocked", state="blocked", reason=reason)

    monkeypatch.setattr(module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(module, "_fetch_run_payload", lambda page, run_id: payload)
    monkeypatch.setattr(module, "_emit", lambda snapshot: emitted.append(snapshot))
    monkeypatch.setattr(module, "_telemetry_seconds", lambda: 30.0)

    with pytest.raises(
        AssertionError,
        match="Backend reached terminal Spanish run failure",
    ) as exc:
        module._wait_for_terminal_with_telemetry(page, "comprun_test", 5_400.0)

    assert reason in str(exc.value)
    assert clock.value == 0.0
    assert len(emitted) == 1
    assert emitted[0]["status"] == "terminal_failure_observed"
    assert emitted[0]["failure"]["reason"] == reason
    assert emitted[0]["lifecycle"]["terminal"] is True


def test_emit_persists_terminal_backend_failure_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    monkeypatch.setattr(module, "_OUTPUT_PATH", tmp_path / "spanish-proof.json")
    snapshot = {
        "artifact_schema": module.VERSION,
        "status": "terminal_failure_observed",
        "run_id": "comprun_test",
        "lifecycle": {"terminal": True, "status": "blocked"},
        "failure": {"reason": "publication_failed"},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    module._emit(snapshot)

    persisted = json.loads(
        (tmp_path / "spanish-proof.progress.json").read_text(encoding="utf-8")
    )
    assert persisted == snapshot
