from __future__ import annotations

from typing import Any, Mapping

from nico.v2_premium_report_renderer import (
    VERSION,
    rebuild_premium_client_artifacts,
)


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render the canonical v2 package through the premium Comprehensive layout.

    The v2 adapter remains the sole truth, lifecycle, filename, and delivery gate.
    This boundary restores the mature multi-chapter client presentation without
    reintroducing legacy finding, scanner, score, or approval-state mutations.
    """
    return rebuild_premium_client_artifacts(package)


__all__ = ["VERSION", "rebuild_client_artifacts"]
