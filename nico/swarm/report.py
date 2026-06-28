from __future__ import annotations

from .permissions import permission_matrix


def swarm_report() -> dict:
    return {"type": "controlled_internal_defensive_swarm", "permissions": permission_matrix()}
