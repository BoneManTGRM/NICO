from __future__ import annotations

from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-spanish-publication-preflight.v93"
_MAX_FAILURE_DETAILS = 50
_MAX_VISITED_NODES = 75_000
_MAX_DEPTH = 18


def _text(value: Any, limit: int = 600) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _spanish_requested(value: Mapping[str, Any]) -> bool:
    identity = value.get("identity") if isinstance(value.get("identity"), Mapping) else {}
    assessment = value.get("assessment") if isinstance(value.get("assessment"), Mapping) else {}
    language = _text(
        value.get("report_language")
        or value.get("locale")
        or identity.get("report_language")
        or identity.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale"),
        40,
    ).casefold()
    return language.startswith("es")


def _iter_report_bound_strings(
    value: Any,
    *,
    key: str = "",
    path: tuple[str, ...] = (),
    depth: int = 0,
    budget: list[int] | None = None,
) -> Iterable[tuple[str, str, str]]:
    """Mirror v87's canonical presentation traversal without copying evidence trees."""

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > _MAX_VISITED_NODES or depth > _MAX_DEPTH:
        return

    # Match the authoritative v87 localization boundary exactly. Raw scanner/canonical
    # evidence and protected identifiers remain immutable and are not Spanish prose.
    if any(segment in canonical._RAW_CANONICAL_SUBTREES for segment in path):
        return
    if key in canonical._PROTECTED_FIELDS:
        return

    if isinstance(value, Mapping):
        for raw_name, item in value.items():
            name = str(raw_name)
            yield from _iter_report_bound_strings(
                item,
                key=name,
                path=(*path, name),
                depth=depth + 1,
                budget=budget,
            )
            if budget[0] > _MAX_VISITED_NODES:
                return
        return

    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_report_bound_strings(
                item,
                key=key,
                path=(*path, f"[{index}]"),
                depth=depth + 1,
                budget=budget,
            )
            if budget[0] > _MAX_VISITED_NODES:
                return
        return

    if isinstance(value, str) and key in canonical._PRESENTATION_PROSE_FIELDS:
        yield ".".join(path) or key, key, value


def inspect_spanish_canonical_publication_preflight(
    canonical_report: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the fully restored canonical report before any client artifact renders.

    This intentionally runs *after* decision-content restoration and count reconciliation.
    Dynamic complexity findings do not necessarily exist in retained stage input; they are
    synthesized while canonical truth is built. Inspecting prior-stage state would therefore
    miss the exact family that caused the production incident.
    """

    if not _spanish_requested(canonical_report):
        return {
            "status": "not_applicable",
            "version": VERSION,
            "spanish_requested": False,
            "failure_count": 0,
            "failure_details": [],
            "canonical_restoration_complete": True,
            "visited_nodes_bounded": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    failures: list[dict[str, str]] = []
    failure_count = 0
    checked = 0
    budget = [0]

    for path, key, source in _iter_report_bound_strings(
        canonical_report,
        path=("canonical_report",),
        budget=budget,
    ):
        checked += 1
        try:
            canonical._translate_presentation_field(source, key)
        except ValueError as exc:
            failure_count += 1
            if len(failures) < _MAX_FAILURE_DETAILS:
                failures.append(
                    {
                        "path": path,
                        "field": key,
                        "source": _text(source, 260),
                        "reason": _text(exc, 360),
                    }
                )

    return {
        "status": "blocked" if failure_count else "complete",
        "version": VERSION,
        "spanish_requested": True,
        "checked_presentation_values": checked,
        "failure_count": failure_count,
        "failure_details": failures,
        "failure_details_truncated": failure_count > len(failures),
        "visited_nodes": min(budget[0], _MAX_VISITED_NODES),
        "visited_nodes_bounded": budget[0] <= _MAX_VISITED_NODES,
        "maximum_visited_nodes": _MAX_VISITED_NODES,
        "maximum_failure_details": _MAX_FAILURE_DETAILS,
        "canonical_restoration_complete": True,
        "presentation_only": True,
        "canonical_evidence_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def assert_spanish_canonical_publication_preflight(
    canonical_report: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = inspect_spanish_canonical_publication_preflight(canonical_report)
    if manifest.get("status") != "blocked":
        return manifest

    details = manifest.get("failure_details") or []
    rendered = " | ".join(
        f"path={item.get('path')}; field={item.get('field')}; reason={item.get('reason')}"
        for item in details
        if isinstance(item, Mapping)
    )
    raise ValueError(
        "spanish_presentation_preflight_failed:"
        f"count={manifest.get('failure_count', 0)}"
        + (f"; {rendered}" if rendered else "")
    )


# Compatibility aliases for callers/tests introduced with the first v93 draft. The
# second argument is ignored intentionally: publication truth is the restored canonical
# model, never the raw prior-stage input.
def inspect_spanish_publication_preflight(
    context: Mapping[str, Any],
    canonical_report: Mapping[str, Any],
) -> dict[str, Any]:
    _ = context
    return inspect_spanish_canonical_publication_preflight(canonical_report)


def assert_spanish_publication_preflight(
    context: Mapping[str, Any],
    canonical_report: Mapping[str, Any],
) -> dict[str, Any]:
    _ = context
    return assert_spanish_canonical_publication_preflight(canonical_report)


__all__ = [
    "VERSION",
    "assert_spanish_canonical_publication_preflight",
    "assert_spanish_publication_preflight",
    "inspect_spanish_canonical_publication_preflight",
    "inspect_spanish_publication_preflight",
]
