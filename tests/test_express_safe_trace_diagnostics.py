from __future__ import annotations

import json
from types import FunctionType

import nico.express_backend_diagnostics as backend_diagnostics
import nico.express_safe_trace_diagnostics as safe_trace


def _synthetic_sensitive_value() -> str:
    """Build a deterministic redaction fixture without storing a secret-like literal."""
    return "-".join(("synthetic", "sensitive", "redaction", "fixture"))


def _collector_template() -> None:
    secret = SYNTHETIC_SENSITIVE_VALUE  # type: ignore[name-defined]
    raise ValueError(secret)


def _synthetic_nico_exception() -> BaseException:
    """Create a bounded NICO traceback frame without eval/exec or a hard-coded token."""
    namespace: dict[str, object] = {
        "__name__": "nico.synthetic_collection_failure",
        "SYNTHETIC_SENSITIVE_VALUE": _synthetic_sensitive_value(),
    }
    code = _collector_template.__code__.replace(
        co_filename="/private/runtime/secret_collector.py",
        co_name="collect",
        co_qualname="collect",
        co_firstlineno=1,
    )
    collect = FunctionType(code, namespace, "collect")
    try:
        collect()
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
    assert _synthetic_sensitive_value() not in encoded
    assert "/private/runtime" not in encoded
    assert "secret_collector.py" not in encoded


def test_installer_extends_diagnostic_and_public_message_without_exception_text(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def base_diagnostic(run_id: str, stage: str, exc: BaseException) -> dict[str, str]:
        calls.append((run_id, stage, type(exc).__name__))
        return {
            "diagnostic_id": "express_diag_test",
            "failure_stage": stage,
            "exception_class": type(exc).__name__,
        }

    def base_failure(run_id: str, request_payload: dict, stage: str, exc: BaseException) -> dict:
        diagnostic = backend_diagnostics._diagnostic(run_id, stage, exc)
        message = "opaque base failure"
        return {
            **diagnostic,
            "status": "failed",
            "run_id": run_id,
            "message": message,
            "progress": [{"step": stage, "status": "failed", "message": message}],
        }

    monkeypatch.setattr(backend_diagnostics, "_diagnostic", base_diagnostic)
    monkeypatch.setattr(backend_diagnostics, "_diagnostic_failure", base_failure)

    first = safe_trace.install_express_safe_trace_diagnostics()
    second = safe_trace.install_express_safe_trace_diagnostics()
    exc = _synthetic_nico_exception()
    result = backend_diagnostics._diagnostic_failure(
        "express_run_test",
        {"repository": "BoneManTGRM/NICO"},
        "collect_assessment",
        exc,
    )

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert first["bounded_location_in_public_message"] is True
    assert first["exception_text_exposed"] is False
    assert first["locals_exposed"] is False
    assert first["absolute_paths_exposed"] is False
    assert calls == [("express_run_test", "collect_assessment", "ValueError")]
    assert result["failure_module"] == "nico.synthetic_collection_failure"
    assert result["failure_function"] == "collect"
    assert result["failure_line"] == 3
    assert result["safe_failure_location"] == "nico.synthetic_collection_failure.collect:3"
    assert "NICO frame nico.synthetic_collection_failure.collect:3" in result["message"]
    assert result["progress"][0]["message"] == result["message"]
    assert len(result["message"]) <= 320
    assert _synthetic_sensitive_value() not in repr(result)
    assert "/private/runtime" not in repr(result)


def test_non_nico_traceback_does_not_publish_external_frame_identity() -> None:
    try:
        raise ValueError("external sensitive value")
    except Exception as exc:
        frame = safe_trace._safe_failure_frame(exc)

    assert frame == {}
