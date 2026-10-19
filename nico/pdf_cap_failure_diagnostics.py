"""Bounded page-budget evidence, collected only when composition fails."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from importlib.metadata import version
import json
import logging
import os
import platform
import re
from typing import Any, Iterator

from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES

SCHEMA = "nico.pdf-cap-failure.v1"
_IDENTITY = ContextVar("pdf_cap_failure_identity", default=None)
_COUNTS = (
    "page_limit", "base_pages", "retained_body_pages_before_reflow",
    "retained_body_pages_after_reflow", "register_pages", "gate_pages",
    "review_pages", "ci_boundary_pages", "human_evidence_pages",
    "required_pages", "total_pages",
)
_VERSIONS = ("python_version", "reportlab_version", "pillow_version", "pypdf_version")
_FONTS = ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique")


def sanitize_pdf_cap_diagnostic(value: Any) -> dict[str, Any] | None:
    """Rebuild a fixed schema; reject malformed counts rather than trusting extras."""
    if type(value) is not dict or value.get("schema") != SCHEMA:
        return None
    reason = value.get("failure_reason")
    if reason not in ("pdf_required_pages_limit", "pdf_total_pages_limit"):
        return None
    if any(type(value.get(k)) is not int or not 0 <= value[k] <= 1_000_000 for k in _COUNTS):
        return None
    if type(value.get("reflow_attempted")) is not bool:
        return None
    if value["required_pages"] != sum(value[k] for k in (
        "register_pages", "gate_pages", "review_pages", "ci_boundary_pages", "human_evidence_pages"
    )) or value["total_pages"] != value["required_pages"] + value["retained_body_pages_after_reflow"]:
        return None
    before, after = value["retained_body_pages_before_reflow"], value["retained_body_pages_after_reflow"]
    if not 0 < after <= before <= value["base_pages"] or value["page_limit"] != MAX_CLIENT_PDF_PAGES:
        return None
    if reason == "pdf_required_pages_limit":
        if value["required_pages"] <= value["page_limit"] or value["reflow_attempted"] or after != before:
            return None
    elif value["total_pages"] <= value["page_limit"] or not value["reflow_attempted"] or value["required_pages"] > value["page_limit"]:
        return None
    output = {"schema": SCHEMA, "stage_id": "final_comprehensive_report_generation",
              "failure_reason": reason, "reflow_attempted": value["reflow_attempted"],
              **{k: value[k] for k in _COUNTS}}
    for key, pattern in (("run_id", r"comprun_[0-9a-f]{32}"),
                         ("release_commit_sha", r"[0-9a-f]{40}")):
        candidate = value.get(key)
        output[key] = candidate if type(candidate) is str and re.fullmatch(pattern, candidate) else "unavailable"
    for key in (*_VERSIONS, "composer_version", "reflow_version"):
        candidate = value.get(key)
        pattern = r"[0-9][0-9A-Za-z.+-]{0,39}" if key in _VERSIONS else r"nico\.[a-z0-9_.-]{1,80}"
        output[key] = candidate if type(candidate) is str and re.fullmatch(pattern, candidate) else "unavailable"
    fonts = value.get("font_registration")
    output["font_registration"] = {
        name: fonts[name] if type(fonts) is dict and fonts.get(name) in
        ("embedded_truetype", "other", "unavailable") else "unavailable"
        for name in _FONTS
    }
    return output


@contextmanager
def pdf_cap_identity(run_id: Any) -> Iterator[None]:
    token = _IDENTITY.set(run_id if type(run_id) is str else None)
    try:
        yield
    finally:
        _IDENTITY.reset(token)


def _runtime_identity() -> dict[str, Any]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from nico.client_pdf_compose_v2 import VERSION as composer_version
    from nico.comprehensive_pdf_reflow_v1 import VERSION as reflow_version

    versions = {}
    for package, key in (("reportlab", "reportlab_version"), ("Pillow", "pillow_version"), ("pypdf", "pypdf_version")):
        try:
            versions[key] = version(package)
        except Exception:
            versions[key] = "unavailable"
    return {
        "run_id": _IDENTITY.get(),
        # Read only known release labels; an invalid native label is not rescued.
        "release_commit_sha": os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("NICO_RELEASE_COMMIT_SHA"),
        "python_version": platform.python_version(), **versions,
        "composer_version": composer_version, "reflow_version": reflow_version,
        # Inspect existing registrations without getFont's lazy registration side effect.
        "font_registration": {name: "embedded_truetype" if isinstance(pdfmetrics._fonts.get(name), TTFont)
                              else "other" if name in pdfmetrics._fonts else "unavailable" for name in _FONTS},
    }


def attach_pdf_cap_diagnostic(
    error: ValueError, *, reason: str, counts: dict[str, int], reflow_attempted: bool
) -> ValueError:
    """Keep the original ValueError even when any diagnostic operation fails."""
    try:
        identity = {}
        try:
            identity = _runtime_identity()
        except Exception:
            pass
        diagnostic = sanitize_pdf_cap_diagnostic({
            **identity, **counts, "schema": SCHEMA, "failure_reason": reason,
            "reflow_attempted": reflow_attempted,
        })
        if diagnostic is not None:
            error.pdf_cap_diagnostic = diagnostic
            logging.getLogger("uvicorn.error").info(
                "NICO_PDF_CAP_FAILURE=%s", json.dumps(diagnostic, sort_keys=True, separators=(",", ":"))
            )
    except Exception:
        pass
    return error
