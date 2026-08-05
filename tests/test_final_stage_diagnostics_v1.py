from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "final_stage_diagnostics_v1.py"
LOADER_PATH = ROOT / "scripts" / "two_service_live_acceptance_v2.py"


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("test_final_stage_diagnostics_v1_module", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Acceptance:
    @staticmethod
    def record(payload: dict[str, Any]) -> dict[str, Any]:
        value = payload.get("record")
        return value if isinstance(value, dict) else payload


class _Runtime(SimpleNamespace):
    pass


def _runtime() -> _Runtime:
    def status_summary(payload: dict[str, Any], *, http_status: int | None = None) -> dict[str, Any]:
        return {
            "status": payload.get("status"),
            "current_stage": payload.get("current_stage"),
            "http_status": http_status,
        }

    return _Runtime(_status_summary=status_summary)


def _blocked_payload() -> dict[str, Any]:
    return {
        "status": "blocked",
        "current_stage": "final_comprehensive_report_generation",
        "stage_results": {
            "scanner_execution": {
                "stage": "scanner_execution",
                "status": "complete",
                "reason": "not the terminal stage",
            },
            "final_comprehensive_report_generation": {
                "stage": "final_comprehensive_report_generation",
                "status": "blocked",
                "reason": "finding_integrity_invalid: exact source identity mismatch",
                "error_code": "finding_integrity_invalid",
                "error_message": "token=top-secret publication validation failed",
                "validation_errors": [
                    {"field": "finding_id", "code": "missing", "message": "secret=hidden"},
                    "priority:invalid_or_missing",
                ],
                "provider_output": {
                    "authorization": "Bearer should-never-be-retained",
                    "report_markdown": "private report body",
                },
            },
        },
    }


def test_install_retains_bounded_terminal_stage_diagnostics_without_changing_status() -> None:
    module = _load_module()
    runtime = _runtime()

    result = module.install(runtime, _Acceptance())
    summary = runtime._status_summary(_blocked_payload(), http_status=200)

    assert result == {
        "version": "nico.final_stage_diagnostics.v1",
        "installed": True,
        "already_installed": False,
    }
    assert summary["status"] == "blocked"
    assert summary["current_stage"] == "final_comprehensive_report_generation"
    assert summary["stage_reason"] == "finding_integrity_invalid: exact source identity mismatch"
    assert summary["stage_error_code"] == "finding_integrity_invalid"
    assert summary["stage_error_message"] == "token=[REDACTED] publication validation failed"
    assert summary["stage_validation_errors"] == [
        "field=finding_id; code=missing; message=secret=[REDACTED]",
        "priority:invalid_or_missing",
    ]

    serialized = json.dumps(summary, sort_keys=True)
    assert "top-secret" not in serialized
    assert "should-never-be-retained" not in serialized
    assert "private report body" not in serialized
    assert "provider_output" not in serialized


def test_diagnostics_are_bounded_and_installation_is_idempotent() -> None:
    module = _load_module()
    runtime = _runtime()
    first = module.install(runtime, _Acceptance())
    second = module.install(runtime, _Acceptance())

    payload = _blocked_payload()
    stage = payload["stage_results"]["final_comprehensive_report_generation"]
    stage["reason"] = "x" * 5000
    stage["validation_errors"] = [f"error-{index}-" + ("y" * 500) for index in range(50)]
    summary = runtime._status_summary(payload)

    assert first["already_installed"] is False
    assert second["already_installed"] is True
    assert len(summary["stage_reason"]) == 1000
    assert len(summary["stage_validation_errors"]) == 20
    assert all(len(item) <= 320 for item in summary["stage_validation_errors"])


def test_loader_installs_diagnostics_after_loading_the_legacy_runtime() -> None:
    source = LOADER_PATH.read_text(encoding="utf-8")

    assert "final_stage_diagnostics_v1.py" in source
    assert "install_final_stage_diagnostics" in source
    assert "FINAL_STAGE_DIAGNOSTICS = install_final_stage_diagnostics(" in source
    assert source.index("_legacy = _load_legacy()") < source.index(
        "FINAL_STAGE_DIAGNOSTICS = install_final_stage_diagnostics("
    )
