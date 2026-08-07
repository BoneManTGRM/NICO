from __future__ import annotations

import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-client-identity-publication-guard.v2"
_MARKER = "__nico_comprehensive_client_identity_publication_guard_v2__"

_IDENTITY_SENTINELS = {
    "customer_id": {"", "default_customer", "unknown_customer"},
    "customer_name": {"", "default_customer", "unknown_customer"},
    "client_id": {"", "default_client", "unknown_client"},
    "client_name": {"", "default_client", "unknown_client"},
    "project_id": {"", "default_project", "unknown_project"},
    "project_name": {"", "default_project", "unknown_project"},
    "workspace_id": {"", "default_workspace", "unknown_workspace"},
    "workspace_name": {"", "default_workspace", "unknown_workspace"},
    "target_id": {"", "default_target", "unknown_target"},
    "target_name": {"", "default_target", "unknown_target"},
}
_ALL_SENTINELS = {
    sentinel
    for sentinels in _IDENTITY_SENTINELS.values()
    for sentinel in sentinels
    if sentinel
}
_IDENTITY_LABELS = {
    "client",
    "client id",
    "client name",
    "customer",
    "customer id",
    "customer name",
    "project",
    "project id",
    "project name",
    "workspace",
    "workspace id",
    "workspace name",
    "target",
    "target id",
    "target name",
}
_DIRECT_IDENTITY_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?"
    r"(client|customer|project|workspace|target)"
    r"(?:\s+(id|name))?\s*[:=]\s*([^|]+?)\s*$",
    re.IGNORECASE,
)
_TABLE_IDENTITY_LINE = re.compile(
    r"^\s*\|\s*"
    r"(client|customer|project|workspace|target)"
    r"(?:\s+(id|name))?\s*\|\s*([^|]+?)\s*\|",
    re.IGNORECASE,
)


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _identity_placeholder(field: str, value: Any) -> bool:
    normalized = _text(value, 300).casefold()
    return normalized in _IDENTITY_SENTINELS.get(field.casefold(), set())


def sanitize_public_identity_fields(value: Any) -> Any:
    """Sanitize exact client-identity fields while preserving literal source evidence.

    Internal sentinel values are valid processing identities, but they are not client
    identities. Only values stored under explicit identity field names are projected
    to ``Not supplied``. Free-form source evidence is intentionally left unchanged,
    because a repository can legitimately contain strings such as ``default_project``.
    """

    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            normalized_key = key.casefold()
            if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
                normalized_key, raw_value
            ):
                output[key] = "Not supplied"
            else:
                output[key] = sanitize_public_identity_fields(raw_value)
        return output
    if isinstance(value, list):
        return [sanitize_public_identity_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_public_identity_fields(item) for item in value)
    return deepcopy(value)


def sanitize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Project public identity fields in the report package without changing evidence text."""

    result = deepcopy(dict(package))
    canonical = (
        sanitize_public_identity_fields(result.get("json"))
        if isinstance(result.get("json"), Mapping)
        else {}
    )
    if not isinstance(canonical, dict):
        canonical = {}

    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_identity_publication_guard_version": VERSION,
            "client_identity_fields_recursively_sanitized": True,
            "literal_source_evidence_preserved": True,
            "numeric_scores_unchanged_by_identity_projection": True,
            "candidate_dispositions_unchanged_by_identity_projection": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical

    for field in _IDENTITY_SENTINELS:
        if field in result and _identity_placeholder(field, result.get(field)):
            result[field] = "Not supplied"
    return result


def _identity_field_violations(value: Any, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            child = f"{path}.{key}" if path else key
            normalized_key = key.casefold()
            if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
                normalized_key, raw_value
            ):
                violations.append(child)
            else:
                violations.extend(_identity_field_violations(raw_value, child))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            violations.extend(_identity_field_violations(item, f"{path}[{index}]"))
    return violations


def _surface_identity_violations(surface: str) -> list[str]:
    """Find placeholders only where a rendered line is explicitly an identity row."""

    text = html.unescape(re.sub(r"<[^>]+>", "\n", surface or ""))
    lines = [_text(line, 1200) for line in text.splitlines() if _text(line, 1200)]
    violations: list[str] = []

    for index, line in enumerate(lines):
        matched = _TABLE_IDENTITY_LINE.match(line) or _DIRECT_IDENTITY_LINE.match(line)
        if matched:
            value = _text(matched.group(3), 300).strip("`*_ ").casefold()
            if value in _ALL_SENTINELS:
                violations.append(line)
                continue

        label = line.casefold().rstrip(":")
        if label in _IDENTITY_LABELS and index + 1 < len(lines):
            value = lines[index + 1].strip("`*_ |:").casefold()
            if value in _ALL_SENTINELS:
                violations.append(f"{line}: {lines[index + 1]}")

    return violations


def _effective_canonical(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve legacy fixture compatibility but fail closed for production contracts."""

    contract = (
        canonical.get("v2_pipeline_contract")
        if isinstance(canonical.get("v2_pipeline_contract"), Mapping)
        else {}
    )
    if contract.get("client_identity_placeholders_sanitized") is True:
        return deepcopy(dict(canonical))
    projected = sanitize_public_identity_fields(canonical)
    return projected if isinstance(projected, dict) else {}


def assert_client_identity_publication_guard(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    """Retain cleanup gates while scoping identity checks to real identity surfaces."""

    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    effective = _effective_canonical(canonical)
    identity_violations = _identity_field_violations(effective)
    if identity_violations:
        raise ValueError(
            "canonical client identity retained placeholder field: "
            + ", ".join(identity_violations[:8])
        )

    pages, extracted = cleanup._pdf_text(pdf)
    for surface_name, surface in (
        ("Markdown", markdown or ""),
        ("HTML", rendered_html or ""),
        ("PDF", extracted),
    ):
        violations = _surface_identity_violations(surface)
        if violations:
            raise ValueError(
                f"client {surface_name} exposed placeholder identity: "
                + "; ".join(violations[:4])
            )

    combined = "\n".join((markdown, html.unescape(rendered_html), extracted))
    lowered = combined.casefold()
    for phrase in cleanup._AMBIGUOUS_SCANNER_LANGUAGE:
        if phrase in lowered:
            raise ValueError(f"client report retained ambiguous scanner language: {phrase}")
    if re.search(
        r"non-success deployments:\s*[.\-–—]*\s*(?:\n|$)",
        combined,
        re.IGNORECASE,
    ):
        raise ValueError("client report retained a blank non-success deployment metric")

    for stage in effective.get("stage_summaries") or []:
        if not isinstance(stage, Mapping):
            continue
        for line in stage.get("evidence") or []:
            value = cleanup._text(line)
            if not value or cleanup._PUNCTUATION_ONLY.fullmatch(value):
                raise ValueError(
                    "client stage evidence retained a blank or punctuation-only value"
                )

    toc = next((page for page in pages if "Table of Contents" in page), "")
    if any(
        cleanup._INTERNAL_DOTTED_LINE.match(cleanup._text(line))
        for line in toc.splitlines()
    ):
        raise ValueError("table of contents exposed an internal dotted canonical key")
    if cleanup._COMPLEXITY_FINDING.search(toc):
        raise ValueError("table of contents used an individual finding as a section title")

    for index, page in enumerate(pages, start=1):
        lines = cleanup._substantive_lines(page)
        if len(lines) <= 2 and any(
            cleanup._INTERNAL_DOTTED_LINE.match(line)
            or cleanup._COMPLEXITY_FINDING.search(line)
            for line in lines
        ):
            raise ValueError(
                f"client PDF retained an accidental orphan detail page at page {index}"
            )
        if re.search(
            r"\b[0-9a-f]{20,63}\s*\n\s*[0-9a-f]\b",
            page,
            re.IGNORECASE,
        ):
            raise ValueError(
                f"client artifact digest wrapped to an isolated character at page {index}"
            )


def install_client_identity_publication_guard_v2() -> dict[str, Any]:
    """Install the scoped identity projection after later report extensions."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup

    current_prepare = completion.prepare_client_report_package
    if not getattr(current_prepare, _MARKER, False):

        @wraps(current_prepare)
        def prepare(package: Mapping[str, Any]) -> dict[str, Any]:
            return sanitize_client_report_package(current_prepare(package))

        setattr(prepare, _MARKER, True)
        setattr(prepare, "_nico_previous", current_prepare)
        completion.prepare_client_report_package = prepare

    current_assert = cleanup.assert_human_review_package_cleanup
    if not getattr(current_assert, _MARKER, False):

        @wraps(current_assert)
        def validate(
            canonical: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> None:
            assert_client_identity_publication_guard(
                canonical,
                markdown,
                rendered_html,
                pdf,
            )

        setattr(validate, _MARKER, True)
        setattr(validate, "_nico_previous", current_assert)
        cleanup.assert_human_review_package_cleanup = validate

    return {
        "status": "installed",
        "version": VERSION,
        "recursive_client_identity_projection_bound": getattr(
            completion.prepare_client_report_package,
            _MARKER,
            False,
        ),
        "scoped_identity_publication_gate_bound": getattr(
            cleanup.assert_human_review_package_cleanup,
            _MARKER,
            False,
        ),
        "literal_source_evidence_preserved": True,
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "assert_client_identity_publication_guard",
    "install_client_identity_publication_guard_v2",
    "sanitize_client_report_package",
    "sanitize_public_identity_fields",
]
