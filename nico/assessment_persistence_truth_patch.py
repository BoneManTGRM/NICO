from __future__ import annotations

from typing import Any

ASSESSMENT_PERSISTENCE_TRUTH_VERSION = "nico.assessment_persistence_truth.v3_verified_record"
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
    writable = bool(persistence_available or adapter in {"memory", "sqlite", "postgres"})
    durability_verified = bool(
        status.get("durability_verified")
        or status.get("survives_container_replacement_verified")
        or (adapter == "postgres" and persistence_available)
    )
    note = str(
        status.get("persistence_note")
        or "Assessment lifecycle state uses the configured storage adapter."
    )
    warning = str(status.get("durability_warning") or "")
    if writable and not durability_verified and not warning:
        warning = (
            "The assessment state is writable but deployment-survival is not verified. "
            "It may disappear after a container replacement."
        )
    return {
        # "recorded" is customer-facing and therefore requires verified durable
        # persistence. Writable ephemeral state remains disclosed separately.
        "recorded": durability_verified,
        "writable": writable,
        "durable": durability_verified,
        "durability_verified": durability_verified,
        "survives_container_replacement_verified": durability_verified,
        "adapter": adapter,
        "restored": restored,
        "note": note,
        "warning": warning,
    }


def install_assessment_persistence_truth() -> dict[str, Any]:
    from nico import full_assessment_runs, mid_assessment_api, mid_assessment_runs

    current = full_assessment_runs.persistence_metadata
    already_installed = bool(getattr(current, _MARKER, False))
    if not already_installed:
        setattr(_truthful_persistence_metadata, _MARKER, True)
        setattr(_truthful_persistence_metadata, "_nico_previous", current)
    full_assessment_runs.persistence_metadata = _truthful_persistence_metadata
    # Mid imports the helper by value in both the persistence and API modules,
    # so all call sites must be rebound explicitly.
    mid_assessment_runs.persistence_metadata = _truthful_persistence_metadata
    mid_assessment_api.persistence_metadata = _truthful_persistence_metadata
    return {
        "status": "already_installed" if already_installed else "installed",
        "version": ASSESSMENT_PERSISTENCE_TRUTH_VERSION,
        "mid_run_binding_installed": mid_assessment_runs.persistence_metadata is _truthful_persistence_metadata,
        "mid_api_binding_installed": mid_assessment_api.persistence_metadata is _truthful_persistence_metadata,
        "full_binding_installed": full_assessment_runs.persistence_metadata is _truthful_persistence_metadata,
        "sqlite_writable_equals_durable": False,
        "memory_writable_equals_recorded": False,
        "container_survival_requires_verification": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "ASSESSMENT_PERSISTENCE_TRUTH_VERSION",
    "install_assessment_persistence_truth",
]
