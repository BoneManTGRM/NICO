from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable, Mapping

from nico.client_assessment_truth_v3 import normalize_repository_path

VERSION = "nico.comprehensive_source_anchor_location.v57"
_MARKER = "_nico_comprehensive_source_anchor_location_v57"
_LOCATION_RE = re.compile(
    r"^(?P<path>.*?):(?P<line>\d+)(?:-(?P<end_line>\d+))?(?::(?P<column>\d+))?$"
)
_SOURCE_PATH_RE = re.compile(
    r"\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|java|kt|swift|go|rs|rb|php|cs|c|cc|cpp|h|hpp|sh|yml|yaml|toml|json)$",
    re.IGNORECASE,
)


def split_repository_source_location(
    value: Any,
) -> tuple[str, int | None, int | None, int | None]:
    """Split a repository source anchor without retaining a range in the path.

    Complexity evidence can retain locations such as ``module.py:64-249`` or
    ``module.py:64-249:64``. Earlier path normalization treated ``:64-249`` as
    part of the filename. The remediation register then assigned two identities to
    the same function: one anchored to ``module.py`` and one to
    ``module.py:64-249``. Keep the source range as metadata, never as path text.
    """

    normalized = normalize_repository_path(value or "")
    match = _LOCATION_RE.match(normalized)
    if not match:
        return normalized, None, None, None
    path = normalize_repository_path(match.group("path"))
    if not _SOURCE_PATH_RE.search(path):
        return normalized, None, None, None
    return (
        path,
        int(match.group("line")),
        int(match.group("end_line")) if match.group("end_line") else None,
        int(match.group("column")) if match.group("column") else None,
    )


def _candidate_locations(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("path"),
        item.get("file_path"),
        item.get("source_path"),
        item.get("location"),
    )


def _install_v3_parser() -> bool:
    from nico import client_finding_remediation_register_v3 as module

    current: Callable[[Mapping[str, Any]], tuple[str, int | None, int | None, int | None]] = (
        module._parse_location
    )
    if getattr(current, _MARKER, False):
        return True

    @wraps(current)
    def parsed(
        item: Mapping[str, Any],
    ) -> tuple[str, int | None, int | None, int | None]:
        path, line, column, end_line = current(item)
        candidates = (path, *_candidate_locations(item))
        for candidate in candidates:
            canonical_path, candidate_line, candidate_end, candidate_column = (
                split_repository_source_location(candidate)
            )
            if candidate_line is None:
                continue
            path = canonical_path
            if line is None:
                line = candidate_line
            if end_line is None:
                end_line = candidate_end
            if column is None:
                column = candidate_column
        return path, line, column, end_line

    setattr(parsed, _MARKER, True)
    setattr(parsed, "_nico_previous", current)
    module._parse_location = parsed
    return module._parse_location is parsed


def _install_two_value_parser(module: Any) -> bool:
    current: Callable[[Mapping[str, Any]], tuple[str, int | None]] = module._parse_location
    if getattr(current, _MARKER, False):
        return True

    @wraps(current)
    def parsed(item: Mapping[str, Any]) -> tuple[str, int | None]:
        path, line = current(item)
        candidates = (path, *_candidate_locations(item))
        for candidate in candidates:
            canonical_path, candidate_line, _candidate_end, _candidate_column = (
                split_repository_source_location(candidate)
            )
            if candidate_line is None:
                continue
            path = canonical_path
            if line is None:
                line = candidate_line
        return path, line

    setattr(parsed, _MARKER, True)
    setattr(parsed, "_nico_previous", current)
    module._parse_location = parsed
    return module._parse_location is parsed


def install_comprehensive_source_anchor_location_v57() -> dict[str, Any]:
    """Bind canonical source-anchor parsing before every register publication pass."""

    from nico import client_finding_remediation_register_v4 as v4
    from nico import client_finding_remediation_register_v5 as v5

    v3_bound = _install_v3_parser()
    v4_bound = _install_two_value_parser(v4)
    v5_bound = _install_two_value_parser(v5)
    return {
        "status": "installed" if all((v3_bound, v4_bound, v5_bound)) else "blocked",
        "version": VERSION,
        "v3_parser_bound": v3_bound,
        "v4_parser_bound": v4_bound,
        "v5_parser_bound": v5_bound,
        "ranged_source_anchor_path_canonicalized": True,
        "source_range_retained_as_metadata": True,
        "temporary_observation_workflow_retained": False,
        "scores_changed_to_satisfy_gate": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_source_anchor_location_v57",
    "split_repository_source_location",
]
