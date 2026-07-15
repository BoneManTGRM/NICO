from __future__ import annotations

import json
from pathlib import Path

import nico.hosted_scanner_worker as hosted_worker
import nico.scanner_redaction_cycle_guard as guard
import nico.scanner_tool_runners as scanner_tools


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "nico" / "assessment_block_messages.py"


def test_cycle_safe_redaction_handles_self_referential_dicts_and_lists() -> None:
    secret = "ghp_" + "1234567890abcdefghijklmnop"
    nested: list[object] = []
    nested.append(nested)
    payload: dict[str, object] = {
        "token": f"token = {secret}",
        "nested": nested,
    }
    payload["self"] = payload

    redacted = guard.cycle_safe_redact_payload(payload)
    encoded = json.dumps(redacted, sort_keys=True)

    assert secret not in encoded
    assert "[REDACTED]" in encoded
    assert redacted["self"] == {"$circular_reference": "dict"}
    assert redacted["nested"][0] == {"$circular_reference": "list"}


def test_cycle_safe_redaction_bounds_excessive_depth() -> None:
    root: dict[str, object] = {}
    current = root
    for _ in range(80):
        child: dict[str, object] = {}
        current["child"] = child
        current = child

    redacted = guard.cycle_safe_redact_payload(root)
    encoded = json.dumps(redacted, sort_keys=True)

    assert "maximum_redaction_depth" in encoded


def test_installer_patches_scanner_module_and_hosted_worker_idempotently(monkeypatch) -> None:
    def unsafe_redactor(value):
        return value

    monkeypatch.setattr(scanner_tools, "redact_payload", unsafe_redactor)
    monkeypatch.setattr(hosted_worker, "redact_payload", unsafe_redactor)

    first = guard.install_cycle_safe_scanner_redaction()
    second = guard.install_cycle_safe_scanner_redaction()

    assert first["status"] == "installed"
    assert first["cycle_safe"] is True
    assert first["json_safe_output"] is True
    assert first["hosted_worker_patched"] is True
    assert second["status"] == "already_installed"
    assert scanner_tools.redact_payload is hosted_worker.redact_payload
    assert getattr(scanner_tools.redact_payload, "_nico_scanner_redaction_cycle_guard_v1") is True


def test_production_installer_enables_cycle_guard_before_express_execution() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "from nico.scanner_redaction_cycle_guard import install_cycle_safe_scanner_redaction" in source
    assert "scanner_redaction = install_cycle_safe_scanner_redaction()" in source
    assert source.index("scanner_redaction = install_cycle_safe_scanner_redaction()") < source.index(
        "express_diagnostics = install_express_backend_diagnostics()"
    )
    assert '"scanner_redaction_cycle_guard": scanner_redaction' in source
