from __future__ import annotations

from typing import Any

ASSESSMENT_PERSISTENCE_TRUTH_VERSION = "nico.assessment_persistence_truth.v1"
_MARKER = "_nico_assessment_persistence_truth_v1"


def _truthful_persistence_metadata(store: Any = None, *, restored: bool = False) -> dict[str, Any]:
    from nico import full_assessment_runs

    active = store or full_assessment_runs.STORE
    try:
        status = active.status()
    except Exception:
        status = {}
    adapter = str(status.get("adapter") or status.get("mode") or "unknown")
    persistence_available = bool(status.get("persistence_available"))
    durability_verified = bool(
        status.get("durability_verified")
        or (adapter == "postgres" and persistence_available)
    )
    recorded = persistence_available or adapter in {"memory", "sqlite", "postgres"}
    note = str(
        status.get("persistence_note")
        or "Assessment lifecycle state is recorded through the configured storage adapter."
    )
    warning = str(status.get("durability_warning") or "")
    if recorded and not durability_verified and not warning:
        warning = (
            "The assessment record is writable but deployment-survival is not verified. "
            "It may disappear after a container replacement."
        )
    return {
        "recorded": recorded,
        "durable": durability_verified,
        "durability_verified": durability_verified,
        "survives_container_replacement_verified": durability_verified,
        "adapter": adapter,
        "restored": restored,
        "note": note,
        "warning": warning,
    }


def install_assessment_persistence_truth() -> dict[str, Any]:
    from nico import full_assessment_runs, mid_assessment_runs

    current = full_assessment_runs.persistence_metadata
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": ASSESSMENT_PERSISTENCE_TRUTH_VERSION,
        }
    setattr(_truthful_persistence_metadata, _MARKER, True)
    setattr(_truthful_persistence_metadata, "_nico_previous", current)
    full_assessment_runs.persistence_metadata = _truthful_persistence_metadata
    # Mid imports the helper by value, so rebind that module explicitly.
    mid_assessment_runs.persistence_metadata = _truthful_persistence_metadata
    return {
        "status": "installed",
        "version": ASSESSMENT_PERSISTENCE_TRUTH_VERSION,
        "mid_binding_installed": mid_assessment_runs.persistence_metadata is _truthful_persistence_metadata,
        "full_binding_installed": full_assessment_runs.persistence_metadata is _truthful_persistence_metadata,
        "sqlite_writable_equals_durable": False,
        "container_survival_requires_verification": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "ASSESSMENT_PERSISTENCE_TRUTH_VERSION",
    "install_assessment_persistence_truth",
]
