from __future__ import annotations

BLOCKED_COMMAND_MARKERS = ("rm -rf", "mkfs", "dd if=", ":(){", "shutdown", "reboot", "curl ", "wget ", "nc ", "ncat ")


def command_allowed(command: str, network_allowed: bool = False) -> dict:
    lowered = command.lower()
    if any(marker in lowered for marker in BLOCKED_COMMAND_MARKERS):
        return {"allowed": False, "reason": "blocked_command_marker"}
    if not network_allowed and any(marker in lowered for marker in ("curl ", "wget ", "nc ", "ncat ")):
        return {"allowed": False, "reason": "network_disabled_by_default"}
    return {"allowed": True, "reason": "allowed_by_local_policy"}


def path_allowed(path: str, allowed_root: str) -> bool:
    from pathlib import Path

    try:
        Path(path).resolve().relative_to(Path(allowed_root).resolve())
        return True
    except ValueError:
        return False
