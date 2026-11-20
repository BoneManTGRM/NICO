"""Bounded page-budget evidence, retained only when composition fails."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from importlib.metadata import version
import base64
import hashlib
import io
import json
import logging
import math
import os
import platform
import re
from typing import Any, Iterator

SCHEMA = "nico.pdf-cap-failure.v1"
_IDENTITY = ContextVar("pdf_cap_failure_identity", default=None)
_TRACE = ContextVar("pdf_cap_failure_boundaries", default=None)
_PDF_BOUNDARIES = ('premium_return', 'sanitizer_input', 'sanitizer_output', 'composer_input')
_ARGUMENT_BOUNDARIES = ('render_arguments', 'premium_render_arguments')
_HASH_LIMIT = 64 * 1024 * 1024
_JSON_SCALAR_LIMIT = 256 * 1024
_JSON_NODE_LIMIT = 100_000
_JSON_DEPTH_LIMIT = 32
_PDF_BYTE_LIMIT = 16 * 1024 * 1024
_PDF_PAGE_LIMIT = 1_000


def _bounded_int(value: Any) -> bool:
    return type(value) is int and 0 <= value <= 1_000_000


def _sanitize_trace(value: Any) -> dict[str, Any] | None:
    if type(value) is not dict or any(k not in (*_PDF_BOUNDARIES, *_ARGUMENT_BOUNDARIES) for k in value):
        return None
    output = {}
    for name, entry in value.items():
        if (type(entry) is not dict or set(entry) != {'calls', 'first', 'latest'}
                or not _bounded_int(entry['calls']) or entry['calls'] < 1):
            return None
        clean = {'calls': entry['calls']}
        for position in ('first', 'latest'):
            item = entry[position]
            hashes = ('sha256',) if name in _PDF_BOUNDARIES else (
                'identity_sha256', 'assessment_sha256', 'supplied_stages_sha256', 'effective_stages_sha256')
            counts = ('pages',) if name in _PDF_BOUNDARIES else ('supplied_stage_count', 'effective_stage_count')
            fields = set((*hashes, *counts)) | ({'compact_final_pdf'} if name in _ARGUMENT_BOUNDARIES else set())
            if (type(item) is not dict or set(item) != fields
                    or any(type(item[k]) is not str or not re.fullmatch(r'[0-9a-f]{64}', item[k]) for k in hashes)
                    or any(not _bounded_int(item[k]) for k in counts)):
                return None
            if name in _ARGUMENT_BOUNDARIES and (type(item['compact_final_pdf']) is not bool
                    or item['effective_stage_count'] != (0 if name == 'render_arguments' and item['compact_final_pdf'] else item['supplied_stage_count'])):
                return None
            clean[position] = dict(item)
        output[name] = clean
    return output


def _record(name: str, observation: dict[str, Any]) -> None:
    state = _TRACE.get()
    if state is None:
        return
    previous = state.get(name)
    entry = {'calls': min(previous['calls'] + 1, 1_000_000) if previous else 1,
             'first': previous['first'] if previous else observation, 'latest': observation}
    # Copy on write keeps inherited contexts isolated. No PDF or arguments retained.
    candidate = _sanitize_trace({**state, name: entry})
    if candidate is not None:
        _TRACE.set(candidate)


def record_pdf_boundary(name: str, pdf: Any, *, pages: int | None = None, encoded: bool = False) -> None:
    """Observe in memory only; persistence/logging remains cap-failure-only."""
    if _TRACE.get() is None or name not in _PDF_BOUNDARIES:
        return
    try:
        if encoded:
            # Check before base64's ASCII conversion and allocation of decoded bytes.
            if type(pdf) not in (str, bytes) or len(pdf) > 4 * ((_PDF_BYTE_LIMIT + 2) // 3):
                return
            pdf = base64.b64decode(pdf, validate=True)
        if type(pdf) is not bytes or len(pdf) > _PDF_BYTE_LIMIT or not pdf.startswith(b'%PDF'):
            return
        if pages is not None and (type(pages) is not int or not 0 <= pages <= _PDF_PAGE_LIMIT):
            return
        if pages is None:
            from pypdf import PdfReader
            pages = len(PdfReader(io.BytesIO(pdf)).pages)
        if not 0 <= pages <= _PDF_PAGE_LIMIT:
            return
        _record(name, {'pages': pages, 'sha256': hashlib.sha256(pdf).hexdigest()})
    except Exception:
        pass


def _preflight_json(value: Any) -> None:
    """Bound traversal and encoder scalar allocations before JSON encoding starts.

    The size estimate deliberately overcounts escaping and separators. Only exact
    builtin types (and OrderedDict) are inspected, avoiding user-defined hooks.
    """
    nodes = 0
    size = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes, size
        nodes += 1
        if nodes > _JSON_NODE_LIMIT or depth > _JSON_DEPTH_LIMIT:
            raise ValueError('diagnostic_json_structure_budget')
        kind = type(item)
        if kind is str:
            if len(item) > _JSON_SCALAR_LIMIT:
                raise ValueError('diagnostic_json_scalar_budget')
            size += 12 * len(item) + 3
        elif item is None or kind is bool:
            size += 6
        elif kind is int:
            if item.bit_length() > 256:
                raise ValueError('diagnostic_json_integer_budget')
            size += 80
        elif kind is float and math.isfinite(item):
            size += 32
        elif kind in (dict, OrderedDict, list, tuple):
            if len(item) > _JSON_NODE_LIMIT - nodes:
                raise ValueError('diagnostic_json_structure_budget')
            size += 3
            if kind in (dict, OrderedDict):
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError('diagnostic_json_key_type')
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
        else:
            raise ValueError('diagnostic_json_type')
        if size > _HASH_LIMIT:
            raise ValueError('diagnostic_hash_budget')

    visit(value, 0)


def _ordered_hash(value: Any) -> str:
    _preflight_json(value)
    digest = hashlib.sha256()
    size = 0
    # Preserve mapping insertion order and list order; never repr/default=str.
    for chunk in json.JSONEncoder(ensure_ascii=True, allow_nan=False, separators=(',', ':')).iterencode(value):
        data = chunk.encode('utf-8')
        size += len(data)
        if size > _HASH_LIMIT:
            raise ValueError('diagnostic_hash_budget')
        digest.update(data)
    return digest.hexdigest()


def record_render_arguments(identity: Any, assessment: Any, supplied: Any, effective: Any, compact: bool,
                            *, boundary: str = 'render_arguments') -> None:
    if _TRACE.get() is None or boundary not in _ARGUMENT_BOUNDARIES:
        return
    try:
        _record(boundary, {
            'identity_sha256': _ordered_hash(identity), 'assessment_sha256': _ordered_hash(assessment),
            'supplied_stages_sha256': _ordered_hash(supplied), 'effective_stages_sha256': _ordered_hash(effective),
            'supplied_stage_count': len(supplied), 'effective_stage_count': len(effective),
            'compact_final_pdf': compact,
        })
    except Exception:
        pass


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
    if not 0 < after <= before <= value["base_pages"] or value["page_limit"] < 1:
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
    if 'boundary_trace' in value:
        trace = _sanitize_trace(value['boundary_trace'])
        if trace is None:
            return None
        if trace:
            output['boundary_trace'] = trace
    return output


@contextmanager
def pdf_cap_identity(run_id: Any) -> Iterator[None]:
    token = _IDENTITY.set(run_id if type(run_id) is str else None)
    trace_token = _TRACE.set({})
    try:
        yield
    finally:
        _TRACE.reset(trace_token)
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
            **({'boundary_trace': _TRACE.get()} if _TRACE.get() else {}),
        })
        if diagnostic is not None:
            error.pdf_cap_diagnostic = diagnostic
            logging.getLogger("uvicorn.error").info(
                "NICO_PDF_CAP_FAILURE=%s", json.dumps(diagnostic, sort_keys=True, separators=(",", ":"))
            )
    except Exception:
        pass
    return error
