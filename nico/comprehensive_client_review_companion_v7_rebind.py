from __future__ import annotations

from typing import Any

from nico.comprehensive_client_review_companion_v7 import (
    COMPANION_PAGE_COUNT,
    SECTIONS_PER_PAGE,
    render_paired_substantive_review_pdf,
)

VERSION = "nico.comprehensive-client-review-companion.v7-rebind"
_MARKER = "__nico_comprehensive_review_companion_v7_rebind__"


def install_comprehensive_review_companion_v7_rebind() -> dict[str, Any]:
    """Rebind every compatibility alias to the paired v7 renderer.

    Older installers may execute after v7 and resolve their own module-level
    callable again. Replace those callables, not only the exported aliases, so a
    later compatibility pass still resolves the four-page implementation.
    """

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_client_review_companion_v2 as v2
    from nico import comprehensive_client_review_companion_v3 as v3
    from nico import comprehensive_client_review_companion_v4 as v4
    from nico import comprehensive_client_review_companion_v5 as v5
    from nico import comprehensive_client_review_companion_v6 as v6
    from nico.comprehensive_client_review_companion_v7_finalizer_binding import (
        install_comprehensive_review_companion_v7_finalizer_binding,
    )

    setattr(render_paired_substantive_review_pdf, _MARKER, True)

    for module in (v2, v3, v4, v5, v6):
        module.render_comprehensive_review_companion_pdf = (
            render_paired_substantive_review_pdf
        )

    # v6's installer assigns this exact module-level symbol back into the
    # completion module. Rebinding it prevents a late v6 compatibility install
    # from restoring the old one-page-per-section renderer.
    v6.render_compact_substantive_review_pdf = render_paired_substantive_review_pdf

    v4.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    v5.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    v6.COMPANION_PAGE_COUNT = COMPANION_PAGE_COUNT
    completion.render_comprehensive_review_companion_pdf = (
        render_paired_substantive_review_pdf
    )
    finalizer_binding = install_comprehensive_review_companion_v7_finalizer_binding()

    return {
        "status": "installed",
        "version": VERSION,
        "page_count": COMPANION_PAGE_COUNT,
        "sections_per_page": SECTIONS_PER_PAGE,
        "completion_bound": (
            completion.render_comprehensive_review_companion_pdf
            is render_paired_substantive_review_pdf
        ),
        "v6_callable_bound": (
            v6.render_compact_substantive_review_pdf
            is render_paired_substantive_review_pdf
        ),
        "finalizer_binding": finalizer_binding,
        "late_compatibility_rebind_safe": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_review_companion_v7_rebind",
]
