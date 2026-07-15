from __future__ import annotations

import json
from pathlib import Path

import nico.scanner_tool_runners as tool_runners
from nico.scanner_redaction_safety import (
    cycle_safe_redact_payload,
    install_scanner_redaction_safety,
    scanner_redaction_safety_status,
)


def test_cycle_safe_redaction_handles_self_referential_dict_without_mutation() -> None:
    secret = "api_key = 1234567890abcdef"
    payload: dict[str, object] = {"secret": secret}
    payload["self"] = payload

    redacted = cycle_safe_redact_payload(payload)

    assert payload["self"] is payload
    assert payload["secret"] == secret
    assert redacted["secret"] == "api_key = [REDACTED]"
    assert redacted["self"] == {"$circular_reference": "dict"}
    assert secret not in json.dumps(redacted, sort_keys=True)


def test_cycle_safe_redaction_handles_self_referential_list() -> None:
    payload: list[object] = ["token = 1234567890abcdef"]
    payload.append(payload)

    redacted = cycle_safe_redact_payload(payload)

    assert payload[1] is payload
    assert redacted[0] == "token = [REDACTED]"
    assert redacted[1] == {"$circular_reference": "list"}
    json.dumps(redacted)


def test_cycle_safe_redaction_bounds_excessive_depth() -> None:
    root: list[object] = []
    cursor = root
    for _ in range(80):
        child: list[object] = []
        cursor.append(child)
        cursor = child

    redacted = cycle_safe_redact_payload(root)
    serialized = json.dumps(redacted, sort_keys=True)

    assert "maximum_redaction_depth" in serialized


def test_installer_is_idempotent_and_patches_runtime_boundary() -> None:
    first = install_scanner_redaction_safety()
    active = tool_runners.redact_payload
    second = install_scanner_redaction_safety()

    assert first["cycle_safe_redaction_installed"] is True
    assert second["cycle_safe_redaction_installed"] is True
    assert tool_runners.redact_payload is active
    assert getattr(active, "_nico_scanner_redaction_safety_v1", False) is True
    assert scanner_redaction_safety_status()["status"] == "ok"


def test_write_scanner_artifact_serializes_circular_evidence_safely(tmp_path: Path) -> None:
    install_scanner_redaction_safety()
    secret = "password = 1234567890abcdef"
    payload: dict[str, object] = {"secret": secret}
    payload["self"] = payload

    destination = tool_runners.write_scanner_artifact(payload, tmp_path / "scanner" / "artifact.json")
    stored = json.loads(destination.read_text(encoding="utf-8"))

    assert secret not in destination.read_text(encoding="utf-8")
    assert stored["secret"] == "password = [REDACTED]"
    assert stored["self"] == {"$circular_reference": "dict"}
