from __future__ import annotations

from typing import Any, Mapping

from nico.v2_authoritative_premium_report import (
    VERSION,
    install_pipeline_projection,
    rebuild_authoritative_premium_artifacts,
)
from nico.v2_dark_branded_cover import apply_dark_branded_cover

# v2_pipeline_adapter imports this module before importing its canonical builder
# and hash helpers. Install the authoritative projection at that boundary so
# scoring, scanner, finding, JSON, Markdown, HTML, PDF, CSV, and UI truth all
# begin from the same repaired canonical object.
install_pipeline_projection()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render the new canonical system through the mature premium report shell.

    The canonical v2 assessment remains the sole source of score, scanner,
    finding, lifecycle, filename, and delivery truth. The renderer restores the
    prior dark branded cover, executive dashboard, dense chapter flow, and
    evidence appendix without reviving any legacy data path.
    """
    rendered = rebuild_authoritative_premium_artifacts(package)
    return apply_dark_branded_cover(rendered)


__all__ = ["VERSION", "rebuild_client_artifacts"]
