from __future__ import annotations

from typing import Any

from nico.full_assessment_idempotent_handlers import idempotent_full_assessment_handlers
from nico.snapshot_assessment_handlers import (
    _snapshot_evidence_attachment_handler,
    _snapshot_repository_handler,
    _snapshot_scanner_handler,
)


def mid_assessment_handlers(timeframe_days: int = 180) -> dict[str, Any]:
    """Compose one evidence-bound Mid pipeline without creating an Express run."""

    bounded_days = max(30, min(int(timeframe_days or 180), 365))
    handlers = idempotent_full_assessment_handlers(timeframe_days=bounded_days)

    def repository_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
        return _snapshot_repository_handler({**context, "timeframe_days": bounded_days}, outputs)

    handlers["repo_evidence"] = repository_handler
    handlers["scanner_worker"] = _snapshot_scanner_handler
    handlers["evidence_attachment"] = _snapshot_evidence_attachment_handler
    return handlers
