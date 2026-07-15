from __future__ import annotations

import json

import nico.express_backend_diagnostics as backend_diagnostics
import nico.express_safe_trace_diagnostics as safe_trace


def _synthetic_nico_exception() -> BaseException:
    namespace: dict[str, object] = {"__name__": "nico.synthetic_collection_failure"}
    source = "def collect():\n    secret = 'provider-token-supersecret'\n    raise ValueError(secret)\n"
    exec(compile(source, "/private/runtime/secret_collector.py", "exec"), namespace)
    try:
        namespace["collect"]()  # type: ignore[index,operator]
    except Exception as exc:
        return exc
    raise AssertionError("synthetic exception was not raised")


def test_safe_failure_frame_records_only_deepest_nico_code_identity() -> None:
    exc = _synthetic_nico_exception()

    frame = safe_trace._safe_failure_frame(exc)
    encoded = json.dumps(frame)

    assert frame == {
        "failure_module": "nico.synthetic_collection_failure",
        "failure_function": "collect",
        "failure_line": 3,
    }
    assert "provider-token-supersecret" not in encoded
    assert "/private/runtime" not in encoded
    assert "secret_collector.py" not in encoded


def test_installer_extends_existing_diagnostic_without_exposing_exception_text(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def base_diagnostic(run_id: str, stage: str, exc: BaseException) -> dict[str, str]:
        calls.append((run_id, stage, type(exc).__name__))
        return {
            "diagnostic_id": "express_diag_test",
            "failure_stage": stage,
            "exception_class": type(exc).__name__,
        }

    monkeypatch.setattr(backend_diagnostics, "_diagnostic", base_diagnostic)

    first = safe_trace.install_express_safe_trace_diagnostics()
    second = safe_trace.install_express_safe_trace_diagnostics()
    exc = _synthetic_nico_exception()
    result = backend_diagnostics._diagnostic("express_run_test", "collect_assessment", exc)

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert first["exception_text_exposed"] is False
    assert first["locals_exposed"] is False
    assert first["absolute_paths_exposed"] is False
    assert calls == [("express_run_test", "collect_assessment", "ValueError")]
    assert result["failure_module"] == "nico.synthetic_collection_failure"
    assert result["failure_function"] == "collect"
    assert result["failure_line"] == 3
    assert "provider-token-supersecret" not in repr(result)


def test_non_nico_traceback_does_not_publish_external_frame_identity() -> None:
    try:
        raise ValueError("external secret")
    except Exception as exc:
        frame = safe_trace._safe_failure_frame(exc)

    assert frame == {}
