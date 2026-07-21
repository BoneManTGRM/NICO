from __future__ import annotations

import sys
from functools import wraps
from typing import Any, Callable

from nico.express_pdf_section_index_v1 import VERSION as INDEX_VERSION
from nico.express_pdf_section_index_v1 import append_canonical_section_index

VERSION = "nico.express_pdf_section_index_binding.v1"
_PATCH_MARKER = "_nico_express_pdf_section_index_binding_v1"


def install_express_pdf_section_index_binding_v1() -> dict[str, Any]:
    from nico import final_report_consistency as target

    current: Callable[[dict[str, Any]], dict[str, Any]] = target.finalize_express_result_consistency
    if getattr(current, _PATCH_MARKER, False):
        api_main = sys.modules.get("nico.api.main")
        if api_main is not None:
            api_main.finalize_express_result_consistency = current
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def finalize(result: dict[str, Any]) -> dict[str, Any]:
        finalized = current(result)
        if finalized.get("status") == "complete":
            append_canonical_section_index(finalized)
        return finalized

    setattr(finalize, _PATCH_MARKER, True)
    setattr(finalize, "_nico_previous", current)
    target.finalize_express_result_consistency = finalize
    api_main = sys.modules.get("nico.api.main")
    if api_main is not None:
        api_main.finalize_express_result_consistency = finalize
    return {
        "status": "installed",
        "version": VERSION,
        "index_version": INDEX_VERSION,
        "backend_finalizer_bound": True,
        "api_alias_rebound": api_main is not None,
        "canonical_section_labels_required": True,
        "canonical_score_labels_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_pdf_section_index_binding_v1"]
