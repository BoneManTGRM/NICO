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


def _active_review_layout() -> dict[str, Any]:
    from nico import comprehensive_client_review_companion_v7 as v7

    flowing = bool(getattr(v7.render_paired_substantive_review_pdf, "_nico_review_flowing", False))
    return {
        "decision_useful_review_companion_pages": None if flowing else COMPANION_PAGE_COUNT,
        "review_companion_section_count": SECTION_COUNT,
        "review_companion_sections_per_page": None if flowing else SECTIONS_PER_PAGE,
        "paired_review_pages_active": not flowing,
        "flowing_review_pages_active": flowing,
    }


def install_comprehensive_review_companion_v7_mobile_contract() -> dict[str, Any]:
    """Expose active layout policy; only a rendered artifact has an actual count."""

    from nico import comprehensive_mobile_score_projection_v2 as mobile

    current = mobile.install_comprehensive_mobile_score_projection_v2
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            **_active_review_layout(),
        }

    @wraps(current)
    def install() -> dict[str, Any]:
        result = dict(current())
        result.update(
            {
                **_active_review_layout(),
                "all_review_sections_retained": True,
            }
        )
        return result

    setattr(install, _MARKER, True)
    setattr(install, "_nico_previous", current)
    mobile.install_comprehensive_mobile_score_projection_v2 = install
    return {
        "status": "installed",
        "version": VERSION,
        **_active_review_layout(),
        "mobile_runtime_status_bound": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_review_companion_v7_mobile_contract",
]
