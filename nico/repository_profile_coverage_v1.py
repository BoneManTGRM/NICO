"""Coverage of the bounded text profile; never a clean or whole-repository claim."""
from __future__ import annotations

import ast
from typing import Any, Mapping

from nico.full_assessment_complexity_evidence import SOURCE_SUFFIXES, _is_source_path
from nico.hosted_assessment import MAX_FILE_BYTES, MAX_TEXT_FILES


def source_coverage_metrics(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Name the two existing populations without changing their calculation."""
    result = {}
    for name, denominator, percentage, population in (
        ("eligible_source_analysis", "eligible_source_files", "eligible_source_coverage_percent", "complexity_eligible_supported_source_files"),
        ("observed_supported_source_analysis", "observed_source_files", "whole_repository_coverage_percent", "observed_supported_language_source_files_including_complexity_exclusions"),
    ):
        result[name] = {
            "numerator": coverage.get("analyzed_source_files"),
            "denominator": coverage.get(denominator),
            "numerator_population": "analyzed_eligible_source_files",
            "denominator_population": population,
            "percentage": coverage.get(percentage),
            "inventory_complete": coverage.get("inventory_complete") is True,
            "all_repository_languages_covered": False,
        }
    return result


def profile_coverage(profile: Mapping[str, Any], measured: Mapping[str, Any]) -> dict[str, Any]:
    paths = {str(path) for path in profile.get("tree_paths", [])}
    files = profile.get("files") or {}
    sampled = set(files)
    if not sampled <= paths:
        raise ValueError("profile_sample_outside_inventory")
    submodules = list(profile.get("submodule_entries") or [])
    non_files = {row["path"] for row in submodules}
    source = {path for path in paths - non_files if path.lower().endswith(SOURCE_SUFFIXES)}
    eligible = {path for path in source if _is_source_path(path)}
    sampled_eligible = sampled & eligible
    analyzed = int(measured.get("files_analyzed") or 0)
    if analyzed < 0 or analyzed > len(sampled_eligible):
        raise ValueError("profile_analyzed_exceeds_sample")
    # Confirm member identities, not only the numerical inequality. This mirrors
    # the existing analyzer's Python parse rejection; JS/TS remains lexical.
    analyzed_paths = set(sampled_eligible)
    named_parser_notes: list[str] = []
    for path in sorted(sampled_eligible):
        if path.lower().endswith(".py"):
            try:
                ast.parse(files[path])
            except (SyntaxError, ValueError):
                analyzed_paths.discard(path)
                named_parser_notes.append(f"{path}: Python parsing failed; excluded from complexity measurements.")
    reported_paths = measured.get("analyzed_source_paths")
    if reported_paths is not None:
        if not isinstance(reported_paths, list) or len(set(reported_paths)) != len(reported_paths):
            raise ValueError("profile_analysis_membership_invalid")
        reported = set(reported_paths)
        if not reported <= analyzed_paths:
            raise ValueError("profile_analysis_path_outside_sample")
        # The installed TypeScript AST analyzer may omit files it could not
        # parse. Use the actual analyzer's membership, never credit a lexical
        # substitute that did not execute.
        analyzed_paths = reported
    if analyzed != len(analyzed_paths):
        raise ValueError("profile_analyzed_membership_mismatch")
    for row in measured.get("top_coupled_files") or []:
        if not isinstance(row, Mapping) or row.get("path") not in analyzed_paths:
            raise ValueError("profile_analysis_path_outside_sample")
    complete = (profile.get("tree_collection_succeeded") is True
                and profile.get("tree_truncated") is False)
    unavailable = sorted(set(profile.get("unavailable_paths") or []))
    limits = profile.get("profile_limits") or {}
    result = {
        "version": "nico.repository_profile_coverage.v1",
        "inventory_complete": complete,
        "coverage_denominator_scope": "complete_source_inventory" if complete else "observed_paths_only",
        "observed_repository_paths": len(paths),
        "inventory_scope": "parent_repository_tree",
        "submodule_entries": submodules,
        "submodule_contents_acquired": False,
        "lfs_pointer_entries": list(profile.get("lfs_pointer_entries") or []),
        "symlink_paths_not_followed": list(profile.get("symlink_paths_not_followed") or []),
        "git_history_observation": profile.get("git_history_observation"),
        "observed_source_files": len(source),
        "eligible_source_files": len(eligible),
        "sampled_eligible_source_files": len(sampled_eligible),
        "analyzed_source_files": analyzed,
        "analyzed_source_paths": sorted(analyzed_paths),
        "unsampled_eligible_source_files": len(eligible - sampled),
        "sampled_unanalyzed_source_paths": sorted(sampled_eligible - analyzed_paths),
        "complexity_excluded_source_files": len(source - eligible),
        "complexity_excluded_paths": sorted(source - eligible),
        "profiled_text_files": len(sampled),
        "sampled_paths": sorted(sampled),
        "unavailable_paths": unavailable,
        "unavailable_profile_files": len(unavailable),
        "unavailable_item_notes": list(profile.get("unavailable") or []),
        "size_excluded_paths": sorted(set(profile.get("size_excluded_paths") or [])),
        "parser_notes": named_parser_notes + list(measured.get("parse_notes") or []),
        "file_limit": limits.get("file_limit", MAX_TEXT_FILES),
        "per_file_byte_limit": limits.get("per_file_byte_limit", MAX_FILE_BYTES),
        "collection_limits": dict(limits),
        "selection_method": limits.get("selection_method", "Known file paths in configured priority order, then sorted eligible paths, within unchanged file and byte limits."),
        "eligible_source_coverage_percent": (
            round(100 * analyzed / len(eligible), 2) if complete and eligible else None
        ),
        "whole_repository_coverage_percent": (
            round(100 * analyzed / len(source), 2) if complete and source else None
        ),
        "whole_repository_percentage_scope": "Observed supported-language source inventory, including complexity-excluded files; not all repository files or all languages.",
        "qualification": (
            "Coverage concerns eligible source files only; exclusions and unsampled files remain outside measured complexity."
            if complete else
            "The source inventory is incomplete; observed counts cannot establish whole-repository coverage."
        ),
        "absence_of_findings_proven": False,
    }
    result["coverage_metrics"] = source_coverage_metrics(result)
    return result
