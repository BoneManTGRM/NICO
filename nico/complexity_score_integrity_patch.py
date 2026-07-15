from __future__ import annotations

import math
from typing import Any

PATCH_VERSION = "nico.complexity_score_integrity.v1"
INVALID_COMPLEXITY_RISKS = {
    "review_required",
    "unavailable",
    "unknown",
    "failed",
    "error",
    "blocked",
    "not_run",
}
COMPLETED_STATUSES = {"completed", "completed_clean", "attached", "passed", "success"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _profile_metrics(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "analyzed_files": _positive_int(
            profile.get("analyzed_file_count")
            or profile.get("files_analyzed")
            or profile.get("source_file_count")
        ),
        "source_loc": _positive_int(
            profile.get("total_loc")
            or profile.get("total_source_loc")
            or profile.get("source_loc")
        ),
        "function_units": _positive_int(
            profile.get("total_functions")
            or profile.get("functions_measured")
            or profile.get("function_count")
        ),
        "risk": str(profile.get("risk_level") or profile.get("risk") or "unknown").strip().lower(),
    }


def _profile_valid(profile: dict[str, Any]) -> bool:
    metrics = _profile_metrics(profile)
    return (
        bool(profile)
        and min(metrics["analyzed_files"], metrics["source_loc"], metrics["function_units"]) > 0
        and metrics["risk"] not in INVALID_COMPLEXITY_RISKS
    )


def _normalize_profile(profile: dict[str, Any], *, origin: str) -> dict[str, Any]:
    normalized = dict(profile)
    metrics = _profile_metrics(normalized)
    normalized.setdefault("analyzed_file_count", metrics["analyzed_files"])
    normalized.setdefault("source_file_count", metrics["analyzed_files"])
    normalized.setdefault("total_loc", metrics["source_loc"])
    normalized.setdefault("total_functions", metrics["function_units"])
    normalized.setdefault("risk_level", metrics["risk"])
    if not normalized.get("hotspots") and isinstance(normalized.get("top_hotspots"), list):
        normalized["hotspots"] = list(normalized["top_hotspots"])
    normalized.setdefault("source", "current_run_scanner_complexity_summary" if "summary" in origin else "checked_out_repository_complexity")
    normalized["selected_profile_origin"] = origin
    if not isinstance(normalized.get("evidence"), list):
        normalized["evidence"] = []
    if not normalized["evidence"] and _profile_valid(normalized):
        normalized["evidence"] = [
            "Complexity evidence verified for this report run: "
            f"{metrics['analyzed_files']} analyzed source file(s), {metrics['source_loc']} LOC, "
            f"and {metrics['function_units']} function-like units."
        ]
    normalized.setdefault("findings", [])
    normalized.setdefault("unavailable", [])
    return normalized


def _candidate_profiles(result: dict[str, Any]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    artifact = _dict(result.get("complexity_artifact"))
    scanner = _dict(result.get("scanner_worker_artifact"))
    bundle = _dict(result.get("scanner_artifacts"))
    candidates = [
        ("complexity_artifact.profile", _dict(artifact.get("profile")), artifact),
        ("result.complexity_engine", _dict(result.get("complexity_engine")), {}),
        ("scanner_worker_artifact.complexity_engine", _dict(scanner.get("complexity_engine")), scanner),
        ("scanner_artifacts.complexity_engine", _dict(bundle.get("complexity_engine")), bundle),
        ("result.complexity_engine_summary", _dict(result.get("complexity_engine_summary")), {}),
        ("scanner_worker_artifact.complexity_engine_summary", _dict(scanner.get("complexity_engine_summary")), scanner),
    ]
    return [(origin, profile, container) for origin, profile, container in candidates if profile]


def _candidate_rank(origin: str, profile: dict[str, Any], container: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    metrics = _profile_metrics(profile)
    valid = int(_profile_valid(profile))
    status = str(profile.get("status") or container.get("status") or "").strip().lower()
    explicit_verified = int(
        profile.get("verified_for_this_report") is True
        or container.get("verified_for_this_report") is True
        or (profile.get("current_run") is True and status in COMPLETED_STATUSES)
    )
    source = str(profile.get("source") or container.get("source") or "").lower()
    full_scope = int("bounded_sample" not in source and "github_api" not in source)
    detail = int("summary" not in origin)
    return (
        valid,
        explicit_verified,
        full_scope,
        detail,
        metrics["analyzed_files"],
        metrics["source_loc"],
    )


def select_strongest_complexity_profile(result: dict[str, Any]) -> tuple[dict[str, Any], str]:
    candidates = _candidate_profiles(result)
    if not candidates:
        return {}, "missing"
    origin, profile, container = max(candidates, key=lambda item: _candidate_rank(*item))
    return _normalize_profile(profile, origin=origin), origin


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in _list(result.get("sections")):
        if isinstance(item, dict) and item.get("id") == section_id:
            return item
    return None


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _remove_stale_complexity_lines(section: dict[str, Any]) -> None:
    fragments = (
        "complexity evidence unavailable for scoring",
        "same-run analyzer did not produce valid measurements",
        "maintainability and complexity conclusions remain unavailable",
        "complexity-dependent architecture and technical-debt conclusions are not verified",
        "invalid_or_zero_complexity_evidence",
    )
    for key in ("evidence", "findings", "unavailable", "verified_claims", "unverified_claims"):
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [
            item for item in values
            if not any(fragment in str(item or "").lower() for fragment in fragments)
        ]


def _patch_evidence_status() -> None:
    from nico import complexity_artifact_integration as integration
    from nico import evidence_status

    def complexity_evidence_present(result: dict[str, Any], architecture: str, velocity: str, ci: str = "") -> bool:
        profile, _ = select_strongest_complexity_profile(result)
        if _profile_valid(profile):
            return True
        summary = _dict(result.get("scanner_artifact_summary"))
        combined = "\n".join((str(summary), architecture, velocity, ci)).lower()
        return "complexity-profile.json" in combined or (
            "complexity evidence" in combined and "attached" in combined
        )

    def apply_complexity_language(result: dict[str, Any], status: dict[str, Any]) -> None:
        tools = _dict(status.get("complexity_tools"))
        tools_complete = bool(tools) and all(
            isinstance(tool, dict) and tool.get("status") == "completed_clean"
            for tool in tools.values()
        )
        if not tools_complete:
            return

        profile, origin = select_strongest_complexity_profile(result)
        valid = _profile_valid(profile)
        metrics = _profile_metrics(profile)
        result["complexity_evidence_marker"] = {
            "status": "verified" if valid else "attached_measurements_pending",
            "artifact": "complexity-profile.json",
            "profile_origin": origin,
            "score_eligible": valid,
            "analyzed_file_count": metrics["analyzed_files"],
            "total_loc": metrics["source_loc"],
            "total_functions": metrics["function_units"],
            "risk_level": metrics["risk"],
            "guardrail": "Artifact presence never substitutes for positive same-run complexity measurements.",
        }

        if valid:
            result["complexity_engine"] = profile
            integration.attach_complexity_artifact_to_report(result)
            detail = (
                "Complexity evidence verified for this report run: "
                f"analyzed_files={metrics['analyzed_files']}, LOC={metrics['source_loc']}, "
                f"function_units={metrics['function_units']}, risk={metrics['risk']}, source={profile.get('source')}."
            )
        else:
            detail = (
                "Complexity artifact is attached, but positive same-run analyzed-file, LOC, and function-unit "
                "measurements are still required before scoring."
            )

        for section_id in ("velocity_complexity", "architecture_debt"):
            section = _section(result, section_id)
            if not section:
                continue
            section.setdefault("evidence", [])
            section.setdefault("unavailable", [])
            if valid:
                _remove_stale_complexity_lines(section)
                _append_unique(section["evidence"], detail)
            else:
                _append_unique(section["unavailable"], detail)
            section["verified_claims"] = list(section.get("evidence") or [])
            section["unverified_claims"] = list(section.get("unavailable") or [])

    evidence_status._complexity_evidence_present = complexity_evidence_present
    evidence_status._apply_complexity_language = apply_complexity_language


def _patch_complexity_artifact_selection() -> None:
    from nico import complexity_artifact_integration as integration

    def strongest_profile(result: dict[str, Any]) -> dict[str, Any] | None:
        profile, _ = select_strongest_complexity_profile(result)
        return profile or None

    integration._complexity_profile = strongest_profile


def _patch_consistency_gate() -> None:
    from nico import report_evidence_consistency_gate as gate

    def complexity_profile(result: dict[str, Any]) -> dict[str, Any]:
        profile, _ = select_strongest_complexity_profile(result)
        return profile

    def complexity_metrics(result: dict[str, Any]) -> dict[str, Any]:
        profile, origin = select_strongest_complexity_profile(result)
        metrics = _profile_metrics(profile)
        artifact = gate._complexity_artifact(result) if origin == "complexity_artifact.profile" else {}
        return {
            "profile": profile,
            "profile_origin": origin,
            "artifact": artifact,
            "analyzed_files": metrics["analyzed_files"],
            "source_loc": metrics["source_loc"],
            "function_units": metrics["function_units"],
            "risk": metrics["risk"],
        }

    def complexity_is_verified(result: dict[str, Any], metrics: dict[str, Any]) -> bool:
        profile = _dict(metrics.get("profile"))
        artifact = _dict(metrics.get("artifact"))
        origin = str(metrics.get("profile_origin") or "")
        if not profile or min(metrics["analyzed_files"], metrics["source_loc"], metrics["function_units"]) <= 0:
            return False
        if metrics["risk"] in INVALID_COMPLEXITY_RISKS:
            return False
        if profile.get("verified_for_this_report") is False or profile.get("current_run") is False:
            return False
        profile_status = str(profile.get("status") or "").lower()
        if profile_status and profile_status not in COMPLETED_STATUSES:
            return False
        if "summary" in origin:
            return profile.get("verified_for_this_report") is True and profile.get("current_run") is True
        if artifact:
            if artifact.get("verified_for_this_report") is not True:
                return False
            if str(artifact.get("status") or "").lower() not in COMPLETED_STATUSES:
                return False
            artifact_run = str(artifact.get("report_run_id") or "")
            result_run = str(result.get("report_run_id") or result.get("run_id") or "")
            if artifact_run and result_run and artifact_run != result_run:
                return False
        profile_run = str(profile.get("report_run_id") or profile.get("run_id") or "")
        result_run = str(result.get("report_run_id") or result.get("run_id") or "")
        return not (profile_run and result_run and profile_run != result_run)

    gate._complexity_profile = complexity_profile
    gate._complexity_metrics = complexity_metrics
    gate._complexity_is_verified = complexity_is_verified


def _patch_valid_complexity_reconciliation() -> None:
    from nico import report_valid_complexity_reconciliation as reconciliation

    def profile(result: dict[str, Any]) -> dict[str, Any]:
        selected, _ = select_strongest_complexity_profile(result)
        return selected

    reconciliation._profile = profile


def _effective_file_complexity(item: dict[str, Any]) -> tuple[int, float]:
    module_complexity = _positive_int(item.get("cyclomatic_complexity"))
    max_function = _positive_int(item.get("max_function_complexity"))
    function_count = _positive_int(item.get("function_count"))
    loc = max(1, _positive_int(item.get("loc")))
    if max_function <= 0:
        divisor = max(1, function_count)
        max_function = min(module_complexity, max(1, math.ceil((module_complexity / divisor) * 1.35)))
    density = round((module_complexity / loc) * 100, 2)
    return max_function, density


def _calibrated_score_profile(
    file_metrics: list[dict[str, Any]],
    churn: dict[str, int],
    owner_concentration: dict[str, float],
    manifest_dependency_count: int,
) -> tuple[int, str, list[str]]:
    findings: list[str] = []
    source_count = len(file_metrics)
    total_loc = sum(_positive_int(item.get("loc")) for item in file_metrics)
    total_module_complexity = sum(_positive_int(item.get("cyclomatic_complexity")) for item in file_metrics)
    effective = [
        (*_effective_file_complexity(item), item)
        for item in file_metrics
    ]
    max_function = max((item[0] for item in effective), default=0)
    density = round((total_module_complexity / max(1, total_loc)) * 100, 2)
    high_function_files = [item for max_fn, _, item in effective if max_fn >= 15]
    elevated_files = [item for max_fn, item_density, item in effective if max_fn >= 10 or item_density >= 18]
    large_complex_files = [
        item for max_fn, item_density, item in effective
        if _positive_int(item.get("loc")) >= 500 and (max_fn >= 10 or item_density >= 18)
    ]
    churn_complexity_overlap = [
        item for max_fn, item_density, item in effective
        if _positive_int(item.get("churn")) >= 500 and (max_fn >= 10 or item_density >= 18)
    ]
    parse_errors = [item for item in file_metrics if item.get("parse_error")]
    owners = {
        str(item.get("primary_owner"))
        for item in file_metrics
        if str(item.get("primary_owner") or "unknown") != "unknown"
    }

    score = 96
    if source_count > 250:
        findings.append(
            "Source-file footprint is large and increases review scope; repository size is not scored as technical debt by itself."
        )
    if total_loc > 50_000:
        findings.append(
            "Total source LOC is high for an Express review and increases review depth; size alone does not reduce maintainability score."
        )

    if max_function >= 40:
        score -= 12
        findings.append("At least one function has very high cyclomatic complexity and should be decomposed or tested heavily.")
    elif max_function >= 25:
        score -= 8
        findings.append("At least one function has high cyclomatic complexity and requires focused review.")
    elif max_function >= 15:
        score -= 5
        findings.append("At least one function has elevated cyclomatic complexity.")
    elif max_function >= 10:
        score -= 2

    if len(high_function_files) >= 20:
        score -= 8
    elif len(high_function_files) >= 10:
        score -= 5
    elif len(high_function_files) >= 5:
        score -= 3
    elif high_function_files:
        score -= 1
    if high_function_files:
        findings.append(
            f"Function-level complexity risk is concentrated in {len(high_function_files)} source file(s)."
        )

    if density >= 25:
        score -= 6
        findings.append("Control-flow density is high relative to source LOC.")
    elif density >= 18:
        score -= 4
        findings.append("Control-flow density is elevated relative to source LOC.")
    elif density >= 12:
        score -= 2

    overlap_count = len({str(item.get("path")) for item in [*large_complex_files, *churn_complexity_overlap]})
    if overlap_count >= 12:
        score -= 6
    elif overlap_count >= 6:
        score -= 4
    elif overlap_count >= 2:
        score -= 2
    if churn_complexity_overlap:
        findings.append(
            f"Complexity and high churn overlap in {len(churn_complexity_overlap)} delivery hotspot file(s)."
        )
    if large_complex_files:
        findings.append(
            f"Large-file and complexity risk overlap in {len(large_complex_files)} source file(s)."
        )

    parse_rate = len(parse_errors) / max(1, source_count)
    if parse_rate >= 0.05:
        score -= 6
        findings.append("Complexity parsing failed for at least 5% of source files.")
    elif parse_rate >= 0.01:
        score -= 3
        findings.append("Complexity parsing failed for at least 1% of source files.")

    if source_count >= 50 and len(owners) <= 1:
        score -= 3
        findings.append("Ownership is concentrated in one observed contributor, creating key-person review risk.")
    elif source_count and sum(1 for value in owner_concentration.values() if value >= 0.9) >= source_count * 0.75:
        score -= 2
        findings.append("Ownership concentration is elevated across the source footprint.")

    if manifest_dependency_count > 120:
        score -= 4
        findings.append("Manifest dependency count is high enough to increase dependency-surface risk.")

    calibrated = max(45, min(96, score))
    risk_level = "low" if calibrated >= 82 else "medium" if calibrated >= 65 else "high"
    return calibrated, risk_level, findings


def _build_calibrated_complexity_profile(repo_dir: Any) -> dict[str, Any]:
    from pathlib import Path
    from collections import Counter
    from nico import complexity_engine as engine

    repo_path = Path(repo_dir).resolve()
    source_files = engine._iter_source_files(repo_path)
    file_metrics = [engine._analyze_file(repo_path, path) for path in source_files]
    churn = engine._git_numstat(repo_path)
    owners, owner_concentration = engine._git_owners(repo_path)
    manifest_dependency_count = engine._manifest_dependency_count(repo_path)
    external_imports = engine._external_imports(file_metrics)

    incoming: Counter[str] = Counter()
    for item in file_metrics:
        for call in item.get("calls", []):
            incoming[str(call)] += 1

    for item in file_metrics:
        path = str(item["path"])
        item["churn"] = churn.get(path, 0)
        item["primary_owner"] = owners.get(path, "unknown")
        item["owner_concentration"] = owner_concentration.get(path, 0)
        max_function, density = _effective_file_complexity(item)
        item["module_cyclomatic_complexity"] = _positive_int(item.get("cyclomatic_complexity"))
        item["max_function_cyclomatic_complexity"] = max_function
        item["complexity_density_per_100_loc"] = density
        item["maintainability_complexity"] = max(max_function, int(round(density)))
        item["hotspot_score"] = round(
            item["maintainability_complexity"] * 8
            + _positive_int(item.get("loc")) / 100
            + math.log1p(_positive_int(item.get("churn"))) * 4,
            2,
        )

    hotspots = sorted(file_metrics, key=lambda item: item.get("hotspot_score", 0), reverse=True)[:12]
    call_edge_count = sum(len(item.get("calls", [])) for item in file_metrics)
    total_loc = sum(_positive_int(item.get("loc")) for item in file_metrics)
    total_functions = sum(_positive_int(item.get("function_count")) for item in file_metrics)
    max_module_complexity = max((_positive_int(item.get("module_cyclomatic_complexity")) for item in file_metrics), default=0)
    max_function_complexity = max((_positive_int(item.get("max_function_cyclomatic_complexity")) for item in file_metrics), default=0)
    total_module_complexity = sum(_positive_int(item.get("module_cyclomatic_complexity")) for item in file_metrics)
    density = round((total_module_complexity / max(1, total_loc)) * 100, 2)
    high_function_count = sum(1 for item in file_metrics if _positive_int(item.get("max_function_cyclomatic_complexity")) >= 15)
    churn_overlap_count = sum(
        1 for item in file_metrics
        if _positive_int(item.get("churn")) >= 500
        and (
            _positive_int(item.get("max_function_cyclomatic_complexity")) >= 10
            or _float(item.get("complexity_density_per_100_loc")) >= 18
        )
    )
    complexity_score, risk_level, findings = _calibrated_score_profile(
        file_metrics,
        churn,
        owner_concentration,
        manifest_dependency_count,
    )

    evidence = [
        f"Complexity engine analyzed {len(file_metrics)} source file(s), {total_loc} source LOC, and {total_functions} function-like units.",
        f"Estimated call graph edges: {call_edge_count}; max function cyclomatic complexity: {max_function_complexity}; maximum module aggregate: {max_module_complexity}.",
        f"Control-flow density: {density} branch points per 100 source LOC; high-function-risk files: {high_function_count}; churn-complexity overlap: {churn_overlap_count}.",
        f"Hotspot candidates identified: {len(hotspots)}; manifest dependency count: {manifest_dependency_count}.",
    ]
    evidence.append(
        f"Git churn data available for {len(churn)} file(s)." if churn
        else "Git churn data unavailable or empty for this checkout."
    )
    evidence.append(
        f"Ownership signal available for {len(owners)} file(s)." if owners
        else "Ownership signal unavailable or empty for this checkout."
    )

    return {
        "artifact_schema": "nico.complexity.v1",
        "scoring_model": "function_risk_density_v2",
        "source_file_count": len(file_metrics),
        "analyzed_file_count": len(file_metrics),
        "total_loc": total_loc,
        "total_functions": total_functions,
        "call_graph_edge_count": call_edge_count,
        "max_file_cyclomatic_complexity": max_module_complexity,
        "max_function_cyclomatic_complexity": max_function_complexity,
        "complexity_density_per_100_loc": density,
        "high_function_risk_file_count": high_function_count,
        "churn_complexity_overlap_count": churn_overlap_count,
        "average_cyclomatic_per_file": round(total_module_complexity / max(1, len(file_metrics)), 2),
        "manifest_dependency_count": manifest_dependency_count,
        "external_import_count": sum(external_imports.values()),
        "top_external_imports": external_imports.most_common(12),
        "hotspots": [
            {
                "path": item.get("path"),
                "hotspot_score": item.get("hotspot_score"),
                "loc": item.get("loc"),
                "cyclomatic_complexity": item.get("module_cyclomatic_complexity"),
                "module_cyclomatic_complexity": item.get("module_cyclomatic_complexity"),
                "max_function_cyclomatic_complexity": item.get("max_function_cyclomatic_complexity"),
                "complexity_density_per_100_loc": item.get("complexity_density_per_100_loc"),
                "churn": item.get("churn"),
                "primary_owner": item.get("primary_owner"),
                "owner_concentration": item.get("owner_concentration"),
            }
            for item in hotspots
        ],
        "churn": {
            "files_with_churn": len(churn),
            "top_churn_files": sorted(churn.items(), key=lambda item: item[1], reverse=True)[:12],
        },
        "ownership": {
            "files_with_owner_signal": len(owners),
            "high_concentration_files": sorted(
                [(path, value) for path, value in owner_concentration.items() if value >= 0.9],
                key=lambda item: item[1],
                reverse=True,
            )[:12],
        },
        "complexity_score": complexity_score,
        "architecture_score": max(45, min(94, complexity_score + 4)),
        "velocity_score": max(45, min(92, complexity_score + 8)),
        "risk_level": risk_level,
        "evidence": evidence,
        "findings": findings,
        "unavailable": [],
        "human_review_required": True,
        "guardrail": "Repository size and development activity are disclosed as review scope. Score deductions are limited to measured function risk, control-flow density, parse gaps, complexity/churn overlap, dependency surface, and key-person risk.",
    }


def _patch_complexity_engine() -> None:
    from nico import complexity_engine as engine

    engine._score_profile = _calibrated_score_profile
    engine.build_complexity_profile = _build_calibrated_complexity_profile


def _patch_complexity_presentation() -> None:
    from nico import hosted_complexity_engine_attachment_patch as attachment
    from nico import hosted_scanner_artifacts as scanner

    original_summary = getattr(
        attachment,
        "_nico_original_build_complexity_attachment_summary_score_integrity",
        attachment.build_complexity_attachment_summary,
    )
    attachment._nico_original_build_complexity_attachment_summary_score_integrity = original_summary

    def build_summary(profile: dict[str, Any] | None) -> dict[str, Any]:
        summary = original_summary(profile)
        raw = profile if isinstance(profile, dict) else {}
        summary["scoring_model"] = raw.get("scoring_model")
        summary["max_function_cyclomatic_complexity"] = _positive_int(raw.get("max_function_cyclomatic_complexity"))
        summary["complexity_density_per_100_loc"] = _float(raw.get("complexity_density_per_100_loc"))
        summary["high_function_risk_file_count"] = _positive_int(raw.get("high_function_risk_file_count"))
        summary["churn_complexity_overlap_count"] = _positive_int(raw.get("churn_complexity_overlap_count"))
        raw_hotspots = raw.get("hotspots") if isinstance(raw.get("hotspots"), list) else []
        for target, source in zip(summary.get("top_hotspots") or [], raw_hotspots):
            if isinstance(target, dict) and isinstance(source, dict):
                target["module_cyclomatic_complexity"] = source.get("module_cyclomatic_complexity")
                target["max_function_cyclomatic_complexity"] = source.get("max_function_cyclomatic_complexity")
                target["complexity_density_per_100_loc"] = source.get("complexity_density_per_100_loc")
        return summary

    def complexity_evidence(profile: dict[str, Any]) -> list[str]:
        evidence = [str(item) for item in profile.get("evidence", []) if item]
        risk = profile.get("risk_level")
        score = profile.get("complexity_score")
        if risk and score is not None:
            evidence.append(f"Complexity engine risk level: {risk}; complexity score={score}/100; model={profile.get('scoring_model') or 'legacy'}.")
        hotspots = profile.get("hotspots") if isinstance(profile.get("hotspots"), list) else []
        if hotspots and isinstance(hotspots[0], dict):
            top = hotspots[0]
            evidence.append(
                "Top complexity hotspot: "
                f"{top.get('path')} hotspot_score={top.get('hotspot_score')}, "
                f"max_function_cyclomatic={top.get('max_function_cyclomatic_complexity')}, "
                f"module_aggregate={top.get('module_cyclomatic_complexity') or top.get('cyclomatic_complexity')}, "
                f"churn={top.get('churn')}."
            )
        return evidence

    def complexity_findings(profile: dict[str, Any]) -> list[str]:
        findings = [str(item) for item in profile.get("findings", []) if item]
        hotspots = profile.get("hotspots") if isinstance(profile.get("hotspots"), list) else []
        for item in hotspots[:5]:
            if not isinstance(item, dict):
                continue
            findings.append(
                "Complexity hotspot: "
                f"{item.get('path')} score={item.get('hotspot_score')}, loc={item.get('loc')}, "
                f"max_function_cyclomatic={item.get('max_function_cyclomatic_complexity')}, "
                f"density={item.get('complexity_density_per_100_loc')}, churn={item.get('churn')}."
            )
        return findings

    attachment.build_complexity_attachment_summary = build_summary
    scanner._complexity_evidence = complexity_evidence
    scanner._complexity_findings = complexity_findings


def _patch_ci_release_selection() -> None:
    from nico import hosted_report_regression_patch as regression

    def latest_runs_by_name(workflow_runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for run in workflow_runs:
            if not isinstance(run, dict):
                continue
            name = str(run.get("name") or run.get("workflow_name") or "").strip()
            if name:
                grouped.setdefault(name, []).append(run)

        def priority(run: dict[str, Any]) -> tuple[int, int, int]:
            conclusion = str(run.get("conclusion") or "").lower()
            status = str(run.get("status") or "").lower()
            branch = str(run.get("head_branch") or run.get("branch") or "").lower()
            event = str(run.get("event") or "").lower()
            conclusive = int(bool(conclusion) or status == "completed")
            default_like = int(branch in {"main", "master"} or run.get("is_default_branch") is True)
            release_like = int(event != "pull_request" and not branch.startswith(("agent/", "codex/", "dependabot/")))
            return conclusive, default_like, release_like

        latest: dict[str, dict[str, Any]] = {}
        for name, runs in grouped.items():
            latest[name] = max(enumerate(runs), key=lambda pair: (*priority(pair[1]), -pair[0]))[1]
        return latest

    regression._latest_runs_by_name = latest_runs_by_name


def install_complexity_score_integrity_patch() -> dict[str, Any]:
    _patch_complexity_engine()
    _patch_complexity_presentation()
    _patch_complexity_artifact_selection()
    _patch_consistency_gate()
    _patch_valid_complexity_reconciliation()
    _patch_evidence_status()
    _patch_ci_release_selection()
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "measured_profile_precedence": True,
        "placeholder_profile_overwrite_blocked": True,
        "function_risk_density_scoring": True,
        "size_only_penalties_removed": True,
        "conclusive_release_ci_selection": True,
        "human_review_required": True,
        "score_inflation_allowed": False,
        "guardrail": "Scores can rise only when measured complexity and release evidence support the change; artifact presence, repository size, and active development cannot create unsupported credit or penalties.",
    }


__all__ = [
    "PATCH_VERSION",
    "install_complexity_score_integrity_patch",
    "select_strongest_complexity_profile",
]
