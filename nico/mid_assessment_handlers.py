from __future__ import annotations

from typing import Any

from nico.full_assessment_idempotent_handlers import idempotent_full_assessment_handlers
import nico.snapshot_assessment_handlers as snapshot_handlers


def mid_assessment_handlers(timeframe_days: int = 180) -> dict[str, Any]:
    """Compose one evidence-bound Mid pipeline without creating an Express run.

    Evidence bridges are installed during production startup. Resolve them from the
    module at composition time so Mid runs use the current attachment/scanner chain
    instead of stale function objects captured before installers completed.
    """

    bounded_days = max(30, min(int(timeframe_days or 180), 365))
    handlers = idempotent_full_assessment_handlers(timeframe_days=bounded_days)

    def repository_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        return snapshot_handlers._snapshot_repository_handler(
            {**context, "timeframe_days": bounded_days}, outputs
        )

    handlers["repo_evidence"] = repository_handler
    handlers["scanner_worker"] = snapshot_handlers._snapshot_scanner_handler
    handlers["evidence_attachment"] = snapshot_handlers._snapshot_evidence_attachment_handler
    return handlers
