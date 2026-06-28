from __future__ import annotations

SECRET_MEMORY = "secret_memory"


def memory_access_allowed(agent_memory_zones: tuple[str, ...], requested_zone: str, approved: bool = False) -> dict:
    if requested_zone == SECRET_MEMORY:
        return {"allowed": False, "reason": "secret_memory_blocked_raw_access"}
    allowed = requested_zone in agent_memory_zones
    return {"allowed": allowed, "reason": "allowed" if allowed else "memory_zone_denied"}


def mask_memory_payload(payload: dict) -> dict:
    return {key: ("***" if "secret" in key.lower() or "token" in key.lower() else value) for key, value in payload.items()}
