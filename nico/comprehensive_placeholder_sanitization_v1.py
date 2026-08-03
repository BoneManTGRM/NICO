from __future__ import annotations

import html
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-placeholder-sanitization.v1"
_MARKER = "_nico_comprehensive_placeholder_sanitization_v1"
_PLACEHOLDER_RE = re.compile(r"<\s*arrow\s*>", re.IGNORECASE)
_IDENTIFIER_FIELDS = {
    "name",
    "symbol",
    "function",
    "function_name",
    "component",
    "component_name",
}
_TITLE_FIELDS = {
    "title",
    "decision_title",
    "finding_title",
    "priority_decision",
}


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _has_placeholder(value: Any) -> bool:
    return bool(_PLACEHOLDER_RE.search(html.unescape(str(value or ""))))


def _identifier_placeholder(value: Any) -> bool:
    normalized = _text(value, 500).casefold()
    return normalized in {"<arrow>", "arrow", "anonymous arrow"} or _has_placeholder(value)


def _clean_title(value: Any, record: Mapping[str, Any]) -> str:
    title = _text(value, 900)
    if not _has_placeholder(title):
        return title
    alternate = _text(record.get("title"), 900)
    if alternate and not _has_placeholder(alternate):
        return alternate
    return _PLACEHOLDER_RE.sub("anonymous callback", title)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        source = deepcopy(dict(value))
        output: dict[str, Any] = {}
        for raw_key, raw_value in source.items():
            key = str(raw_key)
            normalized_key = key.casefold()
            if isinstance(raw_value, Mapping) or isinstance(raw_value, (list, tuple)):
                output[key] = _sanitize_value(raw_value)
                continue
            if isinstance(raw_value, str):
                if normalized_key in _IDENTIFIER_FIELDS and _identifier_placeholder(raw_value):
                    output[key] = "anonymous callback"
                elif normalized_key in _TITLE_FIELDS:
                    output[key] = _clean_title(raw_value, source)
                else:
                    output[key] = _PLACEHOLDER_RE.sub(
                        "anonymous callback",
                        raw_value,
                    )
                continue
            output[key] = deepcopy(raw_value)
        return output
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _PLACEHOLDER_RE.sub("anonymous callback", value)
    return deepcopy(value)


def sanitize_canonical_placeholder_identifiers(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Remove parser placeholders without changing scores, findings, or source anchors."""

    result = _sanitize_value(canonical)
    if not isinstance(result, dict):
        result = {}
    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "parser_placeholder_sanitization_version": VERSION,
            "parser_placeholders_removed_from_canonical_truth": True,
            "anonymous_callbacks_retain_exact_source_anchors": True,
            "numeric_scores_unchanged_by_placeholder_sanitization": True,
            "scanner_dispositions_unchanged_by_placeholder_sanitization": True,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def _placeholder_locations(value: Any, path: str = "") -> list[str]:
    locations: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            locations.extend(_placeholder_locations(item, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            locations.extend(_placeholder_locations(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _has_placeholder(value):
        locations.append(path or "root")
    return locations


def assert_parser_placeholders_absent(value: Any, *, surface: str) -> None:
    locations = _placeholder_locations(value)
    if locations:
        raise ValueError(
            f"{surface} retained parser placeholder <arrow> at "
            + ", ".join(locations[:8])
        )


def _assert_text_surfaces(
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    from pypdf import PdfReader

    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    assert_parser_placeholders_absent(markdown, surface="client Markdown")
    assert_parser_placeholders_absent(rendered_html, surface="client HTML")
    assert_parser_placeholders_absent(extracted, surface="client PDF")


def install_comprehensive_placeholder_sanitization() -> dict[str, Any]:
    """Bind sanitization into existing completion globals before final composition."""

    from nico import client_report_completion_v2 as completion

    current_sync = completion.synchronize_canonical_finding_surfaces
    if not getattr(current_sync, _MARKER, False):

        @wraps(current_sync)
        def synchronize(
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
        ) -> dict[str, Any]:
            return sanitize_canonical_placeholder_identifiers(
                current_sync(canonical, register)
            )

        setattr(synchronize, _MARKER, True)
        setattr(synchronize, "_nico_previous", current_sync)
        completion.synchronize_canonical_finding_surfaces = synchronize

    current_reconcile = completion.reconcile_authoritative_scanner_truth
    if not getattr(current_reconcile, _MARKER, False):

        @wraps(current_reconcile)
        def reconcile(canonical: Mapping[str, Any]) -> dict[str, Any]:
            return sanitize_canonical_placeholder_identifiers(
                current_reconcile(canonical)
            )

        setattr(reconcile, _MARKER, True)
        setattr(reconcile, "_nico_previous", current_reconcile)
        completion.reconcile_authoritative_scanner_truth = reconcile

    current_validate = completion._validate_final_surfaces
    if not getattr(current_validate, _MARKER, False):

        @wraps(current_validate)
        def validate(
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> dict[str, Any]:
            assert_parser_placeholders_absent(
                canonical,
                surface="canonical report JSON",
            )
            assert_parser_placeholders_absent(
                register,
                surface="finding remediation register",
            )
            _assert_text_surfaces(markdown, rendered_html, pdf)
            result = dict(
                current_validate(
                    canonical,
                    register,
                    markdown,
                    rendered_html,
                    pdf,
                )
            )
            result.update(
                {
                    "parser_placeholders_absent": True,
                    "anonymous_callback_source_anchors_retained": True,
                }
            )
            return result

        setattr(validate, _MARKER, True)
        setattr(validate, "_nico_previous", current_validate)
        completion._validate_final_surfaces = validate

    return {
        "status": "installed",
        "version": VERSION,
        "canonical_sync_bound": getattr(
            completion.synchronize_canonical_finding_surfaces,
            _MARKER,
            False,
        ),
        "scanner_reconciliation_bound": getattr(
            completion.reconcile_authoritative_scanner_truth,
            _MARKER,
            False,
        ),
        "final_surface_gate_bound": getattr(
            completion._validate_final_surfaces,
            _MARKER,
            False,
        ),
        "scores_unchanged": True,
        "scanner_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_parser_placeholders_absent",
    "install_comprehensive_placeholder_sanitization",
    "sanitize_canonical_placeholder_identifiers",
]
