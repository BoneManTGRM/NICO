from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_glyph_score_leakage.v1"
_PATCH_MARKER = "_nico_express_glyph_score_leakage_v1"
_GLYPH_FIELDS = {"bar", "glyph_bar", "contribution_bar"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def strip_glyph_score_fields(value: Any, seen: set[int] | None = None) -> Any:
    """Remove text-glyph score bars while retaining numeric geometry metadata."""
    if seen is None:
        seen = set()
    if not isinstance(value, (dict, list)):
        return value
    identity = id(value)
    if identity in seen:
        return value
    seen.add(identity)

    if isinstance(value, list):
        for item in value:
            strip_glyph_score_fields(item, seen)
        return value

    for key in tuple(value):
        if key in _GLYPH_FIELDS:
            value.pop(key, None)

    section_id = _text(value.get("id") or value.get("section_id")).casefold()
    label = _text(value.get("label") or value.get("title") or value.get("name")).casefold()
    if section_id == "scanner_worker_evidence" or label == "scanner worker evidence":
        value.update(
            {
                "status": "SUPPLEMENTAL",
                "display_status": "SUPPLEMENTAL · NOT SCORED",
                "directly_scored": False,
                "mapped_to_scored_controls": True,
                "score_treatment": "supplemental_not_scored",
                "presented_score": None,
                "presented": None,
            }
        )
        if "score" in value:
            value["diagnostic_finding_count"] = value.get("score")
            value["score"] = None
        geometry = value.get("bar_geometry")
        if isinstance(geometry, dict):
            geometry.update({"value": 0.0, "ratio": 0.0, "width": 0.0})

    for child in tuple(value.values()):
        strip_glyph_score_fields(child, seen)
    return value


def normalize_express_glyph_score_truth(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    strip_glyph_score_fields(output)
    output["express_glyph_score_truth"] = {
        "status": "complete",
        "version": VERSION,
        "glyph_score_fields_removed": True,
        "numeric_geometry_retained": True,
        "scanner_worker_not_scored": True,
    }
    return output


def _apply_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    result.clear()
    result.update(normalized)


def install_express_glyph_score_leakage_patch() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        normalized = normalize_express_glyph_score_truth(result)
        _apply_in_place(result, normalized)
        return current(result)

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "glyph_score_fields_removed": True,
        "scanner_worker_not_scored": True,
    }


__all__ = [
    "VERSION",
    "install_express_glyph_score_leakage_patch",
    "normalize_express_glyph_score_truth",
    "strip_glyph_score_fields",
]
