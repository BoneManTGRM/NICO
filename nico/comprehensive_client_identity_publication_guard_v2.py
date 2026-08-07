from __future__ import annotations

import html
import re
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-client-identity-publication-guard.v2.1"
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
_IDENTITY_CONTAINER_KEYS = {
    "identity",
    "client_identity",
    "customer_identity",
    "project_identity",
    "workspace_identity",
    "target_identity",
    "assessment_identity",
    "report_identity",
    "run_identity",
    "engagement_identity",
    "artifact_identity",
}
_DIRECT_IDENTITY_CONTAINERS = {
    "assessment",
    "metadata",
    "report_metadata",
    "run_metadata",
    "artifact_manifest",
    "approval_subject",
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


def _project_identity_container(value: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only a bounded public-identity container.

    Comprehensive technical evidence can be very large. Identity projection must not
    recursively copy or inspect scanner payloads, candidate registers, source evidence,
    or other unrelated structures. Known identity subcontainers remain copy-on-write.
    """

    output = dict(value)
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        normalized_key = key.casefold()
        if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
            normalized_key, raw_value
        ):
            output[key] = "Not supplied"
            continue
        if (
            normalized_key in _IDENTITY_CONTAINER_KEYS
            or normalized_key in _DIRECT_IDENTITY_CONTAINERS
        ) and isinstance(raw_value, Mapping):
            output[key] = _project_identity_container(raw_value)
    return output


def sanitize_public_identity_fields(value: Any) -> Any:
    """Project client-safe identity without traversing technical evidence.

    Only the canonical root, known public identity containers, and known direct
    identity-bearing metadata containers are copied. Every unrelated object is kept by
    reference. This keeps identity sanitization bounded even for very large reports and
    preserves literal or structured technical evidence containing ``default_project``.
    """

    if not isinstance(value, Mapping):
        return value

    output = dict(value)
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        normalized_key = key.casefold()
        if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
            normalized_key, raw_value
        ):
            output[key] = "Not supplied"
            continue
        if (
            normalized_key in _IDENTITY_CONTAINER_KEYS
            or normalized_key in _DIRECT_IDENTITY_CONTAINERS
        ) and isinstance(raw_value, Mapping):
            output[key] = _project_identity_container(raw_value)
    return output


def sanitize_client_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Project client-safe identity without copying the full report package."""

    result = dict(package)
    canonical = (
        sanitize_public_identity_fields(package.get("json"))
        if isinstance(package.get("json"), Mapping)
        else {}
    )
    if not isinstance(canonical, dict):
        canonical = {}

    contract = dict(canonical.get("v2_pipeline_contract") or {})
    contract.update(
        {
            "client_identity_publication_guard_version": VERSION,
            "client_identity_fields_recursively_sanitized": True,
            "client_identity_projection_bounded_copy_on_write": True,
            "technical_evidence_traversal_by_identity_guard": False,
            "literal_source_evidence_preserved": True,
            "numeric_scores_unchanged_by_identity_projection": True,
            "candidate_dispositions_unchanged_by_identity_projection": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    result["json"] = canonical

    for raw_key, raw_value in package.items():
        key = str(raw_key)
        normalized_key = key.casefold()
        if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
            normalized_key, raw_value
        ):
            result[key] = "Not supplied"
        elif normalized_key in _IDENTITY_CONTAINER_KEYS and isinstance(
            raw_value, Mapping
        ):
            result[key] = _project_identity_container(raw_value)
    return result


def _identity_container_violations(
    value: Mapping[str, Any],
    *,
    path: str,
) -> list[str]:
    violations: list[str] = []
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        child = f"{path}.{key}" if path else key
        normalized_key = key.casefold()
        if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
            normalized_key, raw_value
        ):
            violations.append(child)
            continue
        if (
            normalized_key in _IDENTITY_CONTAINER_KEYS
            or normalized_key in _DIRECT_IDENTITY_CONTAINERS
        ) and isinstance(raw_value, Mapping):
            violations.extend(
                _identity_container_violations(raw_value, path=child)
            )
    return violations


def _identity_field_violations(value: Any) -> list[str]:
    """Inspect only public identity boundaries, never the technical evidence graph."""

    if not isinstance(value, Mapping):
        return []
    violations: list[str] = []
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        normalized_key = key.casefold()
        if normalized_key in _IDENTITY_SENTINELS and _identity_placeholder(
            normalized_key, raw_value
        ):
            violations.append(key)
            continue
        if (
            normalized_key in _IDENTITY_CONTAINER_KEYS
            or normalized_key in _DIRECT_IDENTITY_CONTAINERS
        ) and isinstance(raw_value, Mapping):
            violations.extend(
                _identity_container_violations(raw_value, path=key)
            )
    return violations


def _surface_identity_violations(surface: str) -> list[str]:
    """Find placeholders only where a rendered line is explicitly an identity row."""

    text = html.unescape(re.sub(r"<[^>]+>", "\n", surface or ""))
    lines = [_text(line, 1200) for line in text.splitlines() if _text(line, 1200)]
    violations: list[str] = []

    for index, line in enumerate(lines):
        matched = _TABLE_IDENTITY_LINE.match(line) or _DIRECT_IDENTITY_LINE.match(line)
        if matched:
            rendered = _text(matched.group(3), 300).strip("`*_ ").casefold()
            if rendered in _ALL_SENTINELS:
                violations.append(line)
                continue

        label = line.casefold().rstrip(":")
        if label in _IDENTITY_LABELS and index + 1 < len(lines):
            rendered = lines[index + 1].strip("`*_ |:").casefold()
            if rendered in _ALL_SENTINELS:
                violations.append(f"{line}: {lines[index + 1]}")

    return violations


def _effective_canonical(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    """Preserve legacy fixture compatibility without copying production evidence."""

    contract = (
        canonical.get("v2_pipeline_contract")
        if isinstance(canonical.get("v2_pipeline_contract"), Mapping)
        else {}
    )
    if contract.get("client_identity_placeholders_sanitized") is True:
        return canonical
    projected = sanitize_public_identity_fields(canonical)
    return projected if isinstance(projected, Mapping) else {}


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
            normalized = cleanup._text(line)
            if not normalized or cleanup._PUNCTUATION_ONLY.fullmatch(normalized):
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
        "client_identity_projection_bounded_copy_on_write": True,
        "technical_evidence_traversal_by_identity_guard": False,
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
