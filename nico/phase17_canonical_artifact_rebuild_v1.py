from __future__ import annotations

from typing import Any, Mapping

from nico.v2_premium_evidence_appendix import (
    VERSION,
    rebuild_premium_client_artifacts_with_appendix,
)


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render canonical v2 truth through the premium report and evidence appendix.

    The v2 adapter remains the sole truth, lifecycle, filename, and delivery gate.
    The presentation restores the mature multi-chapter report and a canonical
    evidence appendix without reviving legacy finding or scanner mutation.
    """
    return rebuild_premium_client_artifacts_with_appendix(package)


__all__ = ["VERSION", "rebuild_client_artifacts"]
