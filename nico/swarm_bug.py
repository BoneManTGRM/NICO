from __future__ import annotations

import asyncio
from typing import Any

from nico.swarm_bugs import swarm_audit


class BugSwarm:
    """Asynchronous compatibility facade over NICO's evidence-bound local scan.

    The prior implementation depended on an undeclared CrewAI package and returned an
    opaque model result. This facade uses NICO's real scanner, RYE prioritization, and
    report-only repair candidates. It never changes the assessed repository.
    """

    def __init__(self) -> None:
        self.detectors = (
            "built_in_secret_scanner",
            "built_in_appsec_scanner",
            "built_in_dependency_scanner",
            "built_in_log_scanner",
            "configured_external_scanners",
        )

    async def swarm(self, repo: str) -> dict[str, Any]:
        result = await asyncio.to_thread(swarm_audit, repo)
        result["detector_families"] = list(self.detectors)
        result["parallel_execution_claim"] = (
            "The asynchronous facade keeps the caller non-blocking. Individual scanner concurrency is reported only "
            "when the underlying scanner evidence proves it."
        )
        return result


__all__ = ["BugSwarm"]
