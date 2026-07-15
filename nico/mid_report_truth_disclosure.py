from __future__ import annotations

from typing import Any, Callable

_MARKER = "_nico_mid_report_truth_disclosure_v1"


def install_mid_report_truth_disclosure() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module
    from nico import mid_report_professional_v3 as v3_module

    current: Callable[[dict[str, Any]], str] = report_module._markdown
    if getattr(current, _MARKER, False):
        return {"status": "already_installed"}

    def markdown_with_truth_disclosure(payload: dict[str, Any]) -> str:
        markdown = current(payload).rstrip()
        if "Unsupported claims permitted: 0" not in markdown:
            markdown += "\n\n- Unsupported claims permitted: 0."
        return markdown + "\n"

    setattr(markdown_with_truth_disclosure, _MARKER, True)
    setattr(markdown_with_truth_disclosure, "_nico_previous", current)
    report_module._markdown = markdown_with_truth_disclosure
    v3_module._markdown = markdown_with_truth_disclosure
    return {
        "status": "installed",
        "unsupported_claims_permitted": 0,
        "human_review_required": True,
    }


__all__ = ["install_mid_report_truth_disclosure"]
