from __future__ import annotations

from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-spanish-publication-preflight.v93"
_MAX_FAILURE_DETAILS = 50
_MAX_VISITED_NODES = 75_000
_MAX_DEPTH = 16

# These are the report-bound decision/presentation fields whose prose is expected to
# survive into client-review artifacts. Raw evidence, scanner payloads, and immutable
# machine identifiers are intentionally excluded; the canonical renderer owns those
# separately and must preserve them byte-for-byte.
_REPORT_BOUND_PROSE_FIELDS = {
    "acceptance_criteria",
    "business_impact",
    "decision",
    "description",
    "exit_criteria",
    "impact",
    "interpretation",
    "label",
    "limitations",
    "objective",
    "recommendation",
    "recommended_correction",
    "rollback",
    "score_rationale",
    "summary",
    "title",
    "unavailable_data_notes",
    "verification",
    "why_it_matters",
}


def _text(value: Any, limit: int = 600) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _spanish_requested(context: Mapping[str, Any]) -> bool:
    identity = context.get("identity") if isinstance(context.get("identity"), Mapping) else {}
    value = _text(
        context.get("report_language")
        or context.get("requested_report_language")
        or context.get("requested_locale")
        or context.get("locale")
        or identity.get("report_language")
        or identity.get("requested_report_language")
        or identity.get("requested_locale")
        or identity.get("locale"),
        40,
    ).casefold()
    return value.startswith("es")


def _iter_report_bound_strings(
    value: Any,
    *,
    key: str = "",
    path: tuple[str, ...] = (),
    depth: int = 0,
    budget: list[int] | None = None,
) -> Iterable[tuple[str, str, str]]:
    """Yield bounded report-bound prose without copying retained evidence trees."""

    from nico import comprehensive_spanish_canonical_report_v87 as canonical

    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > _MAX_VISITED_NODES or depth > _MAX_DEPTH:
        return

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

    if isinstance(value, str) and key in _REPORT_BOUND_PROSE_FIELDS:
        yield ".".join(path) or key, key, value


def inspect_spanish_publication_preflight(
    context: Mapping[str, Any],
    prior_stage_results: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate every bounded report-bound Spanish presentation field in one pass.

    The final renderer remains the authority and still fails closed. This preflight is
    deliberately additive: instead of discovering one untranslated generated sentence
    per production rerun, it exercises all report-bound prose visible in the retained
    stage state and returns every missing contract found in the same bounded pass.
    """

    if not _spanish_requested(context):
        return {
            "status": "not_applicable",
            "version": VERSION,
            "spanish_requested": False,
            "failure_count": 0,
            "failure_details": [],
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
        prior_stage_results,
        path=("prior_stage_results",),
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
        "presentation_only": True,
        "canonical_evidence_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def assert_spanish_publication_preflight(
    context: Mapping[str, Any],
    prior_stage_results: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = inspect_spanish_publication_preflight(context, prior_stage_results)
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


__all__ = [
    "VERSION",
    "assert_spanish_publication_preflight",
    "inspect_spanish_publication_preflight",
]
