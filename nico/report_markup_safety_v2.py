from __future__ import annotations

import re
from typing import Any, Callable

_PATCH_MARKER = "_nico_report_markup_safety_v2"
_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def _clean_markup(value: Any) -> Any:
    """Remove presentation markup from untrusted report text before ReportLab sees it.

    NICO report helpers intentionally escape arbitrary text. Callers must therefore not
    inject pseudo-HTML such as ``<b>`` into report strings because escaped tags become
    visible client-facing defects. This normalizer keeps the underlying words and strips
    only tag-shaped presentation fragments.
    """
    if isinstance(value, str):
        return _TAG_RE.sub("", value)
    return value


def install_report_markup_safety_v2() -> dict[str, Any]:
    from nico import report_flowable_safety as safety

    if getattr(safety, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": "report-markup-safety-v2"}

    original: Callable[..., Any] = safety._paragraph

    def safe_paragraph(text: Any, *args: Any, **kwargs: Any) -> Any:
        return original(_clean_markup(text), *args, **kwargs)

    safety._paragraph = safe_paragraph
    setattr(safety, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": "report-markup-safety-v2",
        "raw_markup_visible": False,
        "untrusted_text_escaped": True,
    }


__all__ = ["install_report_markup_safety_v2", "_clean_markup"]
