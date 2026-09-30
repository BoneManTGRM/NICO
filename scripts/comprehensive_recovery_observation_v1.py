"""Decide when a detached recovery's bounded status has reached a new boundary."""
from collections.abc import Mapping
from typing import Any


def recovery_boundary_observed(view: Mapping[str, Any], *, initial_revision: int) -> bool:
    revision = view.get("revision")
    return bool(
        type(revision) is int
        and revision > initial_revision
        and view.get("terminal") is True
    )
