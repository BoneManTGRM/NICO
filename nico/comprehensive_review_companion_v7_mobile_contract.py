from __future__ import annotations

from functools import wraps
from typing import Any

from nico.comprehensive_client_review_companion_v7 import (
    COMPANION_PAGE_COUNT,
    SECTIONS_PER_PAGE,
)
from nico.comprehensive_client_review_companion_v5 import SECTION_COUNT

VERSION = "nico.comprehensive-review-companion.v7-mobile-contract"
_MARKER = "__nico_comprehensive_review_companion_v7_mobile_contract__"


def install_comprehensive_review_companion_v7_mobile_contract() -> dict[str, Any]:
    """Expose the active paired worksheet contract through mobile runtime status."""

    from nico import comprehensive_mobile_score_projection_v2 as mobile

    current = mobile.install_comprehensive_mobile_score_projection_v2
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "decision_useful_review_companion_pages": COMPANION_PAGE_COUNT,
            "review_companion_section_count": SECTION_COUNT,
            "review_companion_sections_per_page": SECTIONS_PER_PAGE,
        }

    @wraps(current)
    def install() -> dict[str, Any]:
        result = dict(current())
        result.update(
            {
                "decision_useful_review_companion_pages": COMPANION_PAGE_COUNT,
                "review_companion_section_count": SECTION_COUNT,
                "review_companion_sections_per_page": SECTIONS_PER_PAGE,
                "all_review_sections_retained": True,
                "paired_review_pages_active": True,
            }
        )
        return result

    setattr(install, _MARKER, True)
    setattr(install, "_nico_previous", current)
    mobile.install_comprehensive_mobile_score_projection_v2 = install
    return {
        "status": "installed",
        "version": VERSION,
        "decision_useful_review_companion_pages": COMPANION_PAGE_COUNT,
        "review_companion_section_count": SECTION_COUNT,
        "review_companion_sections_per_page": SECTIONS_PER_PAGE,
        "mobile_runtime_status_bound": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_review_companion_v7_mobile_contract",
]
