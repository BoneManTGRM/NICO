from __future__ import annotations

import base64
from typing import Any, Mapping

from nico.v2_authoritative_premium_report import (
    VERSION,
    install_pipeline_projection,
    rebuild_authoritative_premium_artifacts,
)
from nico.v2_authoritative_review_gate import install_authoritative_review_gate
from nico.v2_dark_branded_cover import apply_dark_branded_cover
from nico.v2_executive_score_dashboard import apply_executive_score_dashboard
from nico.v2_pdf_control_character_guard import (
    _assert_no_control_glyphs,
    install_pdf_control_character_guard,
)

# v2_pipeline_adapter imports this module before importing its canonical builder
# and hash helpers. Install the authoritative projection at that boundary so
# scoring, scanner, finding, JSON, Markdown, HTML, PDF, CSV, and UI truth all
# begin from the same repaired canonical object.
install_pipeline_projection()
# Preserve the old premium visual shell while making the human approval and
# immutable-package acceptance boundary explicit in every rendered format.
_AUTHORITATIVE_REVIEW_GATE = install_authoritative_review_gate()
# ReportLab's standard Helvetica bullet can extract as U+007F. Bind a PDF-only
# ASCII list projection and reject any remaining C0/C1 control glyphs.
_PDF_CONTROL_CHARACTER_GUARD = install_pdf_control_character_guard()


def rebuild_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    """Render the authoritative assessment through the premium report shell."""
    rendered = rebuild_authoritative_premium_artifacts(package)
    rendered = apply_executive_score_dashboard(rendered)
    rendered = apply_dark_branded_cover(rendered)

    # Validate the exact final PDF after every post-render transformation. This
    # prevents a later dashboard or cover step from silently bypassing the bound
    # renderer guard and publishing a PDF that production acceptance will reject.
    final_pdf = base64.b64decode(str(rendered.get("pdf_base64") or ""))
    _assert_no_control_glyphs(final_pdf)
    contract = dict(rendered.get("premium_report_renderer") or {})
    contract["final_pdf_control_character_validation"] = True
    rendered["premium_report_renderer"] = contract
    return rendered


__all__ = ["VERSION", "rebuild_client_artifacts"]
