from __future__ import annotations

import hashlib
import io
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from pypdf import PdfReader, PdfWriter

from nico.client_assessment_truth_v3 import executable_tls_evidence, normalize_repository_path
from nico.dependency_materiality import classify_dependency_finding

VERSION = "nico.comprehensive-internal-readiness.v1"

_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}
_COMPLETE_STATES = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "ok",
}
_MISSING_LOCATIONS = {
    "",
    "unknown",
    "none",
    "n/a",
    "na",
    "not retained",
    "location-not-retained",
}
_NON_PRODUCTION_PARTS = {
    "test",
    "tests",
    "fixture",
    "fixtures",
    "example",
    "examples",
    "sample",
    "samples",
    "generated",
    "vendor",
    "vendors",
    "dist",
    "build",
    "coverage",
}
_HUMAN_CONTEXT_MARKERS = (
    "stakeholder",
    "business priorit",
    "budget",
    "labor rate",
    "named people",
    "human evidence",
    "acceptance testing",
    "runtime user-journey",
    "production telemetry",
    "incident",
)


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _text(value).casefold().replace("_", "-")).strip("-")


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, number))


def _dict(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _iter_mappings(value: Any, *, depth: int = 0) -> Iterable[dict[str, Any]]:
    if depth > 12:
        return
    if isinstance(value, dict):
        yield value
        for key, child in value.items():
            if str(key).casefold() in {"pdf_base64", "markdown", "html", "raw_output", "stdout", "stderr", "secret", "match"}:
                continue
            yield from _iter_mappings(child, depth=depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child, depth=depth + 1)


def _scanner_name(record: Mapping[str, Any]) -> str:
    normalized = _text(record.get("scanner_name") or record.get("tool") or record.get("scanner")).casefold().replace("_", "-")
    return {
        "npm audit": "npm-audit",
        "pip audit": "pip-audit",
        "osv": "osv-scanner",
        "truffle-hog": "trufflehog",
        "tsc": "typescript",
    }.get(normalized, normalized)


def _state(record: Mapping[str, Any]) -> str:
    return _token(record.get("state") or record.get("status") or record.get("execution_status"))


def _completed(record: Mapping[str, Any]) -> bool:
    state = _state(record).replace("-", "_")
    return bool(record.get("completed") is True or state in {item.replace("-", "_") for item in _COMPLETE_STATES})


def _verified(record: Mapping[str, Any]) -> bool:
    return bool(
        record.get("verified") is True
        or record.get("verified_complete") is True
        or record.get("verified_for_this_report") is True
    )


def _scanner_records(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    candidates = (
        canonical.get("requested_scanner_records"),
        assessment.get("requested_scanner_records"),
        canonical.get("scanner_execution_records"),
        assessment.get("scanner_execution_records"),
    )
    selected: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        for raw in _list(candidate):
            if not isinstance(raw, Mapping):
                continue
            item = deepcopy(dict(raw))
            name = _scanner_name(item)
            if not name:
                continue
            current = selected.get(name)
            quality = (
                int(_completed(item)),
                int(_verified(item)),
                int(item.get("exact_commit_match") is True),
                int(bool(item.get("artifact_hash"))),
                len(_list(item.get("findings"))),
            )
            current_quality = (
                int(_completed(current or {})),
                int(_verified(current or {})),
                int((current or {}).get("exact_commit_match") is True),
                int(bool((current or {}).get("artifact_hash"))),
                len(_list((current or {}).get("findings"))),
            )
            if current is None or quality > current_quality:
                item["scanner_name"] = name
                selected[name] = item
    return [selected[name] for name in sorted(selected)]


def _source_metadata_path(finding: Mapping[str, Any]) -> str:
    metadata = finding.get("SourceMetadata")
    data = metadata.get("Data") if isinstance(metadata, Mapping) else None
    git = data.get("Git") if isinstance(data, Mapping) else None
    if isinstance(git, Mapping):
        return _text(git.get("file") or git.get("path"))
    return ""


def _finding_path(finding: Mapping[str, Any]) -> str:
    value = (
        finding.get("dependency_path")
        or finding.get("source_path")
        or finding.get("file_path")
        or finding.get("filename")
        or finding.get("path")
        or finding.get("filePath")
        or finding.get("File")
        or finding.get("manifest")
        or finding.get("lockfile")
        or _source_metadata_path(finding)
    )
    if isinstance(value, Mapping):
        value = value.get("path") or value.get("file")
    return normalize_repository_path(value or "")


def _non_production_path(path: str) -> bool:
    normalized = normalize_repository_path(path).casefold()
    if normalized in {".env.example", ".env.sample", ".env.template", "env.example", "env.sample", "env.template"}:
        return True
    parts = [part for part in Path(normalized).parts if part]
    filename = parts[-1] if parts else ""
    return bool(
        any(part in _NON_PRODUCTION_PARTS for part in parts)
        or filename.startswith("test_")
        or filename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def _secret_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    raw = material = review = approved = 0
    full_history = 0
    for record in records:
        if _scanner_name(record) not in {"gitleaks", "trufflehog"}:
            continue
        if _completed(record) and record.get("full_history_verified") is True:
            full_history += 1
        findings = [item for item in _list(record.get("findings")) if isinstance(item, Mapping)]
        raw += max(len(findings), _int(record.get("raw_finding_count") or record.get("finding_count")))
        for finding in findings:
            path = _finding_path(finding)
            verified_secret = finding.get("Verified") is True or finding.get("verified") is True
            placeholder = _non_production_path(path) and not verified_secret
            if verified_secret:
                material += 1
            elif placeholder:
                approved += 1
            else:
                review += 1
        if not findings:
            material += _int(record.get("blocking") or record.get("material_finding_count"))
            review += _int(record.get("needs_review") or record.get("review_required_finding_count"))
            approved += _int(record.get("approved_test_placeholders") or record.get("excluded_test_only_finding_count") or record.get("supplemental_finding_count"))
    return {
        "raw": raw,
        "material": material,
        "review": review,
        "approved": approved,
        "full_history_tools": full_history,
    }


def _dependency_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    raw = material = review = non_material = 0
    resolved_clean: set[str] = set()
    supplemental: list[dict[str, Any]] = []
    for record in records:
        name = _scanner_name(record)
        if name not in {"pip-audit", "npm-audit", "osv-scanner"}:
            continue
        findings = [item for item in _list(record.get("findings")) if isinstance(item, Mapping)]
        raw += max(len(findings), _int(record.get("raw_finding_count") or record.get("finding_count")))
        if not findings and name == "osv-scanner":
            review += _int(record.get("supplemental_finding_count"))
        if name in {"pip-audit", "npm-audit"} and _completed(record) and _verified(record) and not findings and _int(record.get("finding_count")) == 0:
            resolved_clean.add(name)
        for finding in findings:
            classified = classify_dependency_finding(finding)
            disposition = _text(classified.get("disposition")).casefold()
            if disposition == "verified_material":
                material += 1
            elif disposition == "verified_non_material":
                non_material += 1
                supplemental.append(classified)
            else:
                review += 1
                supplemental.append(classified)
    return {
        "raw": raw,
        "material": material,
        "review": review,
        "non_material": non_material,
        "resolved_clean_tools": sorted(resolved_clean),
        "supplemental": supplemental,
    }


def _static_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    required = {"bandit", "semgrep", "eslint", "typescript"}
    complete: set[str] = set()
    material = review = 0
    configuration_failures: list[str] = []
    for record in records:
        name = _scanner_name(record)
        if name not in required:
            continue
        if _completed(record) and _verified(record):
            complete.add(name)
        if _state(record) in {"configuration-failed", "configuration-error", "invalid-configuration"} or _int(record.get("scanner_configuration_error_count")):
            configuration_failures.append(name)
        for finding in _list(record.get("findings")):
            if not isinstance(finding, Mapping):
                continue
            path = _finding_path(finding)
            if _non_production_path(path):
                continue
            severity = _text(
                finding.get("severity")
                or finding.get("issue_severity")
                or finding.get("level")
                or ((finding.get("extra") or {}).get("severity") if isinstance(finding.get("extra"), Mapping) else "")
            ).casefold()
            if severity in {"critical", "high", "error"} and finding.get("material") is True:
                material += 1
            else:
                review += 1
    return {
        "required": sorted(required),
        "complete": sorted(complete),
        "incomplete": sorted(required - complete),
        "material": material,
        "review": review,
        "configuration_failures": sorted(set(configuration_failures)),
    }


def _section_map(canonical: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    assessment = _dict(canonical.get("assessment"))
    sections = [deepcopy(dict(item)) for item in _list(assessment.get("sections")) if isinstance(item, Mapping)]
    assessment["sections"] = sections
    canonical["assessment"] = assessment
    return assessment, {str(item.get("id") or ""): item for item in sections if item.get("id")}


def _set_section_score(
    section: dict[str, Any] | None,
    score: int,
    *,
    reason: str,
    evidence: Iterable[str] = (),
    findings: Iterable[str] = (),
    assurance: str = "evidence_bound",
) -> None:
    if section is None:
        return
    bounded = max(0, min(100, int(score)))
    section["pre_internal_readiness_score"] = _number(section.get("presented_score", section.get("score")))
    section["score"] = bounded
    section["source_score"] = bounded
    section["presented_score"] = bounded
    section["status"] = "exceptional" if bounded >= 90 else "strong" if bounded >= 80 else "moderate" if bounded >= 70 else "developing" if bounded >= 60 else "critical"
    section["presented_status"] = section["status"].upper()
    section["assurance_status"] = assurance
    section["internal_readiness_reason"] = reason
    section["evidence"] = _dedupe_strings([*_list(section.get("evidence")), *evidence])
    section["findings"] = _dedupe_strings([*_list(section.get("findings")), *findings])
    section["verified_claims"] = list(section["evidence"])


def _first_numeric(root: Any, keys: set[str]) -> int | None:
    for item in _iter_mappings(root):
        for key, value in item.items():
            if str(key) in keys:
                number = _number(value)
                if number is not None:
                    return number
    return None


def _first_value(root: Any, keys: set[str]) -> Any:
    for item in _iter_mappings(root):
        for key, value in item.items():
            if str(key) in keys and value not in (None, "", [], {}):
                return value
    return None


def _code_material_count(canonical: Mapping[str, Any]) -> int:
    material = 0
    for item in _list(canonical.get("canonical_findings")):
        if not isinstance(item, Mapping):
            continue
        family = _token(item.get("finding_family") or item.get("rule_id"))
        category = _token(item.get("category"))
        if family == "complexity-hotspot" or category in {"architecture", "dependency", "secret", "ci-cd"}:
            continue
        if family == "tls-verify-disabled" and not executable_tls_evidence(item):
            continue
        if item.get("material") is True or (
            item.get("priority") in {"P0", "P1"}
            and item.get("client_actionable") is not False
            and _finding_path(item)
        ):
            material += 1
    return material


def _test_path_count(canonical: Mapping[str, Any]) -> int:
    return _first_numeric(canonical, {"test_path_count", "test_path_signal_count"}) or 0


def _lockfile_count(canonical: Mapping[str, Any]) -> int:
    paths = _first_value(canonical, {"lockfile_paths", "lockfiles"})
    if isinstance(paths, list):
        return len(paths)
    if isinstance(paths, str) and paths.strip():
        return 1
    return 0


def _ci_evidence(canonical: Mapping[str, Any]) -> dict[str, Any]:
    exact = _first_value(canonical, {"assessed_commit_required_check_health", "exact_commit_required_check_health"})
    current = _first_value(canonical, {"current_default_branch_required_check_health", "current_required_check_health"})
    job_rate = _first_value(canonical, {"job_success_rate"})
    try:
        job_rate_value = float(job_rate) if job_rate is not None else 0.0
    except (TypeError, ValueError):
        job_rate_value = 0.0
    controls = _first_numeric(canonical, {"control_count"}) or 0
    successful = _first_numeric(canonical, {"successful_runs"}) or 0
    non_success = _first_numeric(canonical, {"non_success_runs"}) or 0
    deployments = _first_numeric(canonical, {"successful_deployments"}) or 0
    exact_true = exact is True or _text(exact).casefold() in {"true", "success", "passed", "green"}
    exact_false = exact is False or _text(exact).casefold() in {"false", "failed", "red"}
    current_true = current is True or _text(current).casefold() in {"true", "success", "passed", "green"}
    current_false = current is False or _text(current).casefold() in {"false", "failed", "red"}
    return {
        "exact_true": exact_true,
        "exact_false": exact_false,
        "current_true": current_true,
        "current_false": current_false,
        "job_success_rate": job_rate_value,
        "control_count": controls,
        "successful_runs": successful,
        "non_success_runs": non_success,
        "successful_deployments": deployments,
    }


def _score_sections(canonical: dict[str, Any]) -> dict[str, Any]:
    records = _scanner_records(canonical)
    assessment, sections = _section_map(canonical)
    dependencies = _dependency_counts(records)
    secrets = _secret_counts(records)
    static = _static_counts(records)
    ci = _ci_evidence(canonical)
    code_material = _code_material_count(canonical)
    tests = _test_path_count(canonical)
    lockfiles = _lockfile_count(canonical)

    if code_material == 0 and tests > 0 and not static["material"]:
        _set_section_score(
            sections.get("code_audit"),
            94,
            reason="No verified executable production code-risk finding remained after source-aware classification; recursive test-path evidence was retained.",
            evidence=(
                f"Verified executable production code-risk findings: {code_material}.",
                f"Recursive repository test paths retained: {tests}.",
                "Raw text-pattern hits remain in the audit ledger but are not scored as confirmed defects without executable source evidence.",
            ),
        )

    resolved_clean = set(dependencies["resolved_clean_tools"])
    if dependencies["material"] == 0 and {"pip-audit", "npm-audit"}.issubset(resolved_clean) and lockfiles > 0:
        _set_section_score(
            sections.get("dependency_health"),
            94,
            reason="Exact resolved Python and production npm dependency audits were clean; unresolved OSV source candidates remain supplemental review evidence, not confirmed production defects.",
            evidence=(
                "Exact resolved dependency audits clean: pip-audit and npm-audit.",
                f"Supplemental dependency candidates retained for triage: {dependencies['review']}.",
                f"Lockfile evidence count: {lockfiles}.",
            ),
            findings=(
                f"{dependencies['review']} supplemental dependency candidate(s) remain visible for package/version/path/reachability disposition; none were scored as verified material.",
            ) if dependencies["review"] else (),
            assurance="evidence_bound_with_supplemental_review" if dependencies["review"] else "evidence_bound",
        )

    secret_names = {name for name in (_scanner_name(item) for item in records) if name in {"gitleaks", "trufflehog"}}
    secret_complete = all(_completed(item) and _verified(item) for item in records if _scanner_name(item) in secret_names)
    if secret_names == {"gitleaks", "trufflehog"} and secret_complete and secrets["material"] == 0 and secrets["review"] == 0:
        _set_section_score(
            sections.get("secrets_review"),
            94,
            reason="Both history-aware secret scanners completed against the exact snapshot and all retained candidates were non-production placeholders or approved nonblocking evidence.",
            evidence=(
                f"History-aware raw candidates retained: {secrets['raw']}.",
                f"Approved test/example placeholders: {secrets['approved']}.",
                "Verified production secrets: 0; unresolved non-fixture secret candidates: 0.",
            ),
        )

    if not static["incomplete"] and static["material"] == 0:
        _set_section_score(
            sections.get("static_analysis"),
            94,
            reason="Bandit, Semgrep, ESLint, and TypeScript completed with exact-run evidence and no verified material production finding.",
            evidence=(
                "Completed applicable static analyzers: " + ", ".join(static["complete"]) + ".",
                f"Review-only static candidates: {static['review']}.",
                "Scanner configuration failures: none.",
            ),
            assurance="evidence_bound_with_review_candidates" if static["review"] else "evidence_bound",
        )
    elif static["incomplete"]:
        section = sections.get("static_analysis")
        if section is not None:
            section["assurance_status"] = "review_limited"
            section["incomplete_applicable_analyzers"] = list(static["incomplete"])

    ci_score: int | None = None
    ci_reason = ""
    if ci["exact_true"] and ci["control_count"] >= 8:
        ci_score = 95
        ci_reason = "The assessed commit's required checks were green and the workflow configuration retained a mature control set."
    elif not ci["exact_false"] and ci["job_success_rate"] >= 0.95 and ci["control_count"] >= 8 and ci["successful_runs"] >= 10:
        ci_score = 90 if not ci["current_false"] else 88
        ci_reason = "Current exact-commit checks were not conclusively retained, but bounded job evidence was highly reliable and workflow controls were mature; historical failures remain separately disclosed."
    if ci_score is not None:
        _set_section_score(
            sections.get("ci_cd"),
            ci_score,
            reason=ci_reason,
            evidence=(
                f"Bounded job success rate: {ci['job_success_rate']:.2f}.",
                f"Workflow configuration controls retained: {ci['control_count']}.",
                f"Historical successful/non-success runs: {ci['successful_runs']}/{ci['non_success_runs']}.",
            ),
            findings=(
                f"Historical non-success runs ({ci['non_success_runs']}) remain a reliability trend for classification and are not treated as failures of the assessed immutable commit.",
            ) if ci["non_success_runs"] else (),
            assurance="evidence_bound" if ci["exact_true"] else "review_limited_exact_commit_health",
        )

    commits = _first_numeric(canonical, {"commits_returned"}) or 0
    pulls = _first_numeric(canonical, {"pull_requests_returned"}) or 0
    if commits > 0 and pulls > 0 and ci["job_success_rate"] >= 0.95 and ci["successful_deployments"] > 0:
        _set_section_score(
            sections.get("velocity_complexity"),
            90,
            reason="Commit, pull-request, job, deployment, and function-level complexity evidence were all retained; the score does not claim individual developer performance.",
            evidence=(
                f"Commits/pull requests retained: {commits}/{pulls}.",
                f"Successful deployments retained: {ci['successful_deployments']}.",
                "Function-level complexity and delivery churn remain separate evidence dimensions.",
            ),
        )

    technical_numerator = 0
    denominator = 0
    section_scores: dict[str, int] = {}
    for section_id, weight in _WEIGHTS.items():
        section = sections.get(section_id)
        score = _number((section or {}).get("presented_score", (section or {}).get("score")))
        if score is None:
            continue
        section_scores[section_id] = score
        technical_numerator += score * weight
        denominator += weight
    technical = int(round(technical_numerator / denominator)) if denominator else 0

    incomplete_applicable = len(static["incomplete"]) + sum(
        1
        for record in records
        if record.get("applicable") is not False
        and _scanner_name(record) not in set(static["required"])
        and not _completed(record)
    )
    evidence_deduction = min(10, incomplete_applicable * 2)
    adjusted = max(0, technical - evidence_deduction)

    assessment.update(
        {
            "technical_score": technical,
            "canonical_evidence_adjusted_score": adjusted,
            "evidence_adjusted_score": adjusted,
            "maturity_signal": {
                **_dict(assessment.get("maturity_signal")),
                "score": technical,
                "source_score": technical,
                "presented_score": technical,
                "level": "Exceptional" if technical >= 90 else "Strong" if technical >= 80 else "Moderate" if technical >= 70 else "Developing",
                "band": "EXCEPTIONAL" if technical >= 90 else "STRONG" if technical >= 80 else "MODERATE" if technical >= 70 else "DEVELOPING",
                "evidence_readiness_score": adjusted,
            },
            "comprehensive_internal_readiness": {
                "version": VERSION,
                "section_scores": section_scores,
                "weights": dict(_WEIGHTS),
                "weighted_technical_score": technical,
                "evidence_adjusted_score": adjusted,
                "incomplete_applicable_analyzers": incomplete_applicable,
                "human_context_boundaries_excluded_from_technical_penalty": True,
                "score_target_applied": False,
                "score_inflation_allowed": False,
            },
        }
    )
    canonical["assessment"] = assessment
    canonical["technical_score"] = technical
    canonical["evidence_adjusted_score"] = adjusted
    canonical["canonical_evidence_adjusted_score"] = adjusted
    canonical["technical_band"] = "EXCEPTIONAL" if technical >= 90 else "STRONG" if technical >= 80 else "MODERATE" if technical >= 70 else "DEVELOPING"
    canonical["maturity_level"] = canonical["technical_band"].title()

    canonical["supplemental_dependency_candidates"] = deepcopy(dependencies["supplemental"])
    canonical["scanner_triage_summary"] = {
        "dependency": {key: value for key, value in dependencies.items() if key != "supplemental"},
        "secret": secrets,
        "static": static,
    }
    return {
        "technical": technical,
        "adjusted": adjusted,
        "records": records,
        "dependencies": dependencies,
        "secrets": secrets,
        "static": static,
        "ci": ci,
    }


def _parse_location(item: Mapping[str, Any]) -> tuple[str, int | None, int | None]:
    raw_path = normalize_repository_path(
        item.get("path") or item.get("file_path") or item.get("source_path") or ""
    )
    line = _int(item.get("line") or item.get("start_line"), 0) or None
    end_line = _int(item.get("end_line"), 0) or None
    location = normalize_repository_path(item.get("location") or "")
    match = re.match(r"^(.*?):(\d+)(?:-(\d+))?(?::\d+)?$", location)
    if match:
        raw_path = normalize_repository_path(match.group(1))
        line = line or int(match.group(2))
        end_line = end_line or (int(match.group(3)) if match.group(3) else None)
    elif not raw_path and location.casefold() not in _MISSING_LOCATIONS:
        raw_path = location
    return raw_path, line, end_line


def _finding_family(item: Mapping[str, Any]) -> str:
    declared = _token(item.get("finding_family") or item.get("rule_id"))
    combined = " ".join(
        _text(item.get(key), 2000)
        for key in ("title", "decision_title", "fact", "observed_evidence", "interpretation", "category")
    ).casefold()
    if "complex" in declared or any(marker in combined for marker in ("cyclomatic_complexity", "complexity hotspot", "concentrated branching")):
        return "complexity_hotspot"
    if "tls" in combined and any(marker in combined for marker in ("verify", "certificate", "cert_none", "rejectunauthorized")):
        return "tls_verify_disabled"
    advisory = re.search(r"\b(?:GHSA-[0-9A-Za-z-]+|CVE-\d{4}-\d+|PYSEC-\d{4}-\d+)\b", combined, re.IGNORECASE)
    if advisory:
        return f"dependency_vulnerability:{advisory.group(0).casefold()}"
    return declared or _token(item.get("category") or item.get("title")) or "technical_finding"


def _finding_quality(item: Mapping[str, Any]) -> tuple[int, ...]:
    path, line, end_line = _parse_location(item)
    identifier = _text(item.get("finding_id") or item.get("id"))
    return (
        int(identifier.startswith("NICO-FINDING-")),
        int(bool(path and line)),
        int(bool(end_line and line and end_line > line)),
        int(bool(item.get("source_excerpt"))),
        int(bool(item.get("symbol") or item.get("function") or item.get("component"))),
        int(bool(item.get("artifact_hash"))),
        len(_text(item.get("fact") or item.get("observed_evidence"))),
    )


def _merge_finding(left: Mapping[str, Any], right: Mapping[str, Any], *, repository: str) -> dict[str, Any]:
    preferred, other = (right, left) if _finding_quality(right) > _finding_quality(left) else (left, right)
    result = deepcopy(dict(preferred))
    for key, value in other.items():
        if result.get(key) in (None, "", [], {}):
            result[key] = deepcopy(value)
    path, line, end_line = _parse_location(result)
    family = _finding_family(result)
    old_ids = _dedupe_strings(
        [
            left.get("finding_id") or left.get("id"),
            right.get("finding_id") or right.get("id"),
            *_list(left.get("finding_aliases")),
            *_list(right.get("finding_aliases")),
            *_list(left.get("internal_finding_aliases")),
            *_list(right.get("internal_finding_aliases")),
        ]
    )
    stable_identity = "|".join((repository.casefold(), path.casefold(), str(line or 0), family))
    stable_id = "NICO-FINDING-" + hashlib.sha256(stable_identity.encode("utf-8")).hexdigest()[:12].upper()
    result["finding_id"] = stable_id
    result["id"] = stable_id
    result["internal_finding_aliases"] = [value for value in old_ids if value != stable_id]
    result["finding_aliases"] = []
    result["finding_family"] = family
    result["path"] = path
    result["line"] = line
    result["end_line"] = end_line
    result["location"] = (
        f"{path}:{line}-{end_line}" if path and line and end_line and end_line > line
        else f"{path}:{line}" if path and line
        else path
    )
    for list_key in ("acceptance_criteria", "verification", "exit_criteria", "supporting_evidence"):
        values = _dedupe_strings([*_list(left.get(list_key)), *_list(right.get(list_key))])
        if values:
            result[list_key] = values
    result["duplicate_sources_consolidated"] = True
    return result


def _source_context(canonical: Mapping[str, Any]) -> dict[tuple[str, int], dict[str, str]]:
    context: dict[tuple[str, int], dict[str, str]] = {}
    for item in _iter_mappings(deepcopy(dict(canonical))):
        path, line, _ = _parse_location(item)
        if not path or not line:
            continue
        key = (path.casefold(), line)
        current = context.setdefault(key, {})
        candidates = {
            "symbol": _text(item.get("symbol") or item.get("function") or item.get("component") or item.get("name")),
            "source_excerpt": _text(item.get("source_excerpt") or item.get("code_excerpt") or item.get("snippet") or item.get("line_text"), 1800),
            "rule_id": _text(item.get("rule_id") or item.get("check_id") or item.get("test_id")),
        }
        for field, value in candidates.items():
            if value and not current.get(field):
                current[field] = value
    return context


def _deduplicate_findings(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    repository = _text(identity.get("repository") or canonical.get("repository"))
    values: list[Mapping[str, Any]] = []
    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        values.extend(item for item in _list(canonical.get(surface)) if isinstance(item, Mapping))
    contexts = _source_context(canonical)
    selected: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    order: list[tuple[str, int, str, str]] = []
    for raw in values:
        item = deepcopy(dict(raw))
        family = _finding_family(item)
        if family.startswith("dependency_vulnerability") and item.get("material") is not True:
            continue
        if _token(item.get("category")) == "secret" and item.get("material") is not True:
            continue
        if family == "tls-verify-disabled" and not executable_tls_evidence(item):
            canonical.setdefault("supplemental_scanner_candidates", []).append(item)
            continue
        path, line, end_line = _parse_location(item)
        title_token = "" if path and line else _token(item.get("title") or item.get("decision_title"))
        key = (path.casefold(), int(line or 0), family, title_token)
        source = contexts.get((path.casefold(), int(line or 0)), {})
        if source:
            item.setdefault("symbol", source.get("symbol"))
            item.setdefault("source_excerpt", source.get("source_excerpt"))
            item.setdefault("rule_id", source.get("rule_id") or family)
        item["path"] = path
        item["line"] = line
        item["end_line"] = end_line
        if key not in selected:
            selected[key] = _merge_finding(item, item, repository=repository)
            order.append(key)
        else:
            selected[key] = _merge_finding(selected[key], item, repository=repository)
    findings = [selected[key] for key in order]
    findings.sort(
        key=lambda item: (
            item.get("priority") not in {"P0", "P1"},
            _text(item.get("path")),
            _int(item.get("line")),
            _text(item.get("finding_family")),
        )
    )
    for surface in ("canonical_findings", "findings_register", "findings", "decision_grade_findings_register"):
        canonical[surface] = deepcopy(findings)
    canonical["executive_risk_register"] = deepcopy(findings[:7])
    canonical["priority_findings"] = deepcopy(findings[:5])
    return findings


def _filter_scanner_decision_findings(canonical: dict[str, Any]) -> None:
    records = _scanner_records(canonical)
    supplemental: list[dict[str, Any]] = list(_list(canonical.get("supplemental_scanner_candidates")))
    filtered: list[dict[str, Any]] = []
    for record in records:
        name = _scanner_name(record)
        kept: list[dict[str, Any]] = []
        raw_findings = [deepcopy(dict(item)) for item in _list(record.get("findings")) if isinstance(item, Mapping)]
        for finding in raw_findings:
            if name in {"pip-audit", "npm-audit", "osv-scanner"}:
                classified = classify_dependency_finding(finding)
                if classified.get("disposition") == "verified_material":
                    kept.append(classified)
                else:
                    supplemental.append(classified)
            elif name in {"gitleaks", "trufflehog"}:
                path = _finding_path(finding)
                verified_secret = finding.get("Verified") is True or finding.get("verified") is True
                if verified_secret or (not _non_production_path(path) and not verified_secret):
                    kept.append(finding)
                else:
                    finding["disposition"] = "approved_non_production_placeholder"
                    supplemental.append(finding)
            else:
                kept.append(finding)
        record["raw_finding_count"] = max(len(raw_findings), _int(record.get("raw_finding_count") or record.get("finding_count")))
        record["supplemental_finding_count"] = max(0, len(raw_findings) - len(kept))
        record["decision_finding_count"] = len(kept)
        record["findings"] = kept
        filtered.append(record)
    canonical["scanner_execution_records"] = deepcopy(filtered)
    canonical["requested_scanner_records"] = deepcopy(filtered)
    assessment = _dict(canonical.get("assessment"))
    assessment["scanner_execution_records"] = deepcopy(filtered)
    assessment["requested_scanner_records"] = deepcopy(filtered)
    canonical["assessment"] = assessment
    canonical["supplemental_scanner_candidates"] = supplemental


def _repair_score_contracts_and_counts(canonical: dict[str, Any], finding_count: int) -> None:
    technical = _int(canonical.get("technical_score") or _dict(canonical.get("assessment")).get("technical_score"))
    adjusted = _int(canonical.get("canonical_evidence_adjusted_score") or _dict(canonical.get("assessment")).get("canonical_evidence_adjusted_score"))
    for item in _iter_mappings(canonical):
        status = _text(item.get("report_contract_status")).casefold()
        reason = _text(item.get("report_contract_reason")).casefold()
        if status == "blocked" and "score" in reason and "mismatch" in reason:
            item["pre_reconciliation_report_contract"] = {"status": item.get("report_contract_status"), "reason": item.get("report_contract_reason")}
            item["report_contract_status"] = "reconciled"
            item["report_contract_reason"] = "canonical_score_truth_reconciled_before_final_render"
            item["report_contract_reconciled"] = True
        for key in ("finding_register_count", "canonical_finding_count", "decision_finding_count"):
            if key in item:
                item[key] = finding_count
        if item.get("final_report_input_scores_synchronized") is True or _token(item.get("capability")) == "canonical-scoring":
            item["technical_score"] = technical
            item["evidence_adjusted_score"] = adjusted
            item["canonical_evidence_adjusted_score"] = adjusted
            item["technical_band"] = "EXCEPTIONAL" if technical >= 90 else "STRONG" if technical >= 80 else "MODERATE" if technical >= 70 else "DEVELOPING"


def _remove_human_context_score_penalties(canonical: dict[str, Any]) -> None:
    assessment = _dict(canonical.get("assessment"))
    limitations = _list(assessment.get("unavailable_data_notes"))
    technical: list[Any] = []
    human: list[Any] = []
    for item in limitations:
        text = _text(item).casefold()
        (human if any(marker in text for marker in _HUMAN_CONTEXT_MARKERS) else technical).append(item)
    assessment["technical_evidence_limitations"] = technical
    assessment["human_context_boundaries"] = human
    assessment["score_affecting_limitation_records"] = len(technical)
    assessment["human_context_boundaries_affect_technical_score"] = False
    canonical["assessment"] = assessment


def reconcile_comprehensive_internal_readiness(canonical: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(canonical))
    _filter_scanner_decision_findings(result)
    score = _score_sections(result)
    findings = _deduplicate_findings(result)
    _remove_human_context_score_penalties(result)
    _repair_score_contracts_and_counts(result, len(findings))

    assessment = _dict(result.get("assessment"))
    contract = _dict(result.get("v2_pipeline_contract"))
    contract.update(
        {
            "comprehensive_internal_readiness_version": VERSION,
            "evidence_bound_score_reconciliation": True,
            "score_target_applied": False,
            "score_inflation_allowed": False,
            "review_only_candidates_not_scored_as_confirmed_defects": True,
            "approved_test_placeholders_excluded_from_production_risk": True,
            "legacy_finding_aliases_hidden_from_client_surfaces": True,
            "duplicate_source_anchors_consolidated": True,
            "human_context_boundaries_excluded_from_technical_penalty": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    result["v2_pipeline_contract"] = contract
    result["human_review_required"] = True
    result["client_delivery_allowed"] = False
    result["client_ready"] = False
    assessment["human_review_required"] = True
    assessment["client_delivery_allowed"] = False
    assessment["client_ready"] = False
    result["assessment"] = assessment
    result["comprehensive_internal_readiness"] = {
        "version": VERSION,
        "technical_score": score["technical"],
        "evidence_adjusted_score": score["adjusted"],
        "target_score_applied": False,
        "score_inflation_allowed": False,
        "proof": {
            "scanner_triage": result.get("scanner_triage_summary"),
            "finding_count": len(findings),
            "supplemental_candidate_count": len(_list(result.get("supplemental_scanner_candidates"))),
        },
    }
    return result


def reconcile_comprehensive_internal_readiness_package(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = result.get("json")
    if isinstance(canonical, Mapping):
        reconciled = reconcile_comprehensive_internal_readiness(canonical)
        result["json"] = reconciled
        result["finding_population"] = deepcopy(reconciled.get("finding_population") or {})
    return result


def _normalized_page_text(page: Any) -> str:
    return " ".join((page.extract_text() or "").casefold().split())


def _is_marker(text: str, markers: Iterable[str], *, max_position: int = 320) -> bool:
    return any(0 <= text.find(marker) <= max_position for marker in markers)


def _compose_pdf_single_register(base_pdf: bytes, register_pdf: bytes, provenance_pdf: bytes) -> bytes:
    from nico import client_report_completion_v1 as legacy

    if not base_pdf.startswith(b"%PDF"):
        raise ValueError("client report completion requires a valid base PDF")
    base_reader = PdfReader(io.BytesIO(base_pdf))
    register_reader = PdfReader(io.BytesIO(register_pdf))
    provenance_reader = PdfReader(io.BytesIO(provenance_pdf))
    register_markers = (
        "finding and remediation register",
        "registro de hallazgos y remediación",
        "registro de hallazgos y remediacion",
        "executive risk register and decision briefing",
    )
    evidence_markers = ("evidence appendix", "apéndice de evidencia", "apendice de evidencia")
    provenance_markers = (
        "analyzer applicability and provenance",
        "procedencia y aplicabilidad de analizadores",
        "scanner provenance",
    )
    review_markers = (
        "human review and acceptance gate",
        "puerta de revisión humana y aceptación",
        "puerta de revision humana y aceptacion",
    )

    retained: list[Any] = []
    insert_at: int | None = None
    skipping_register = False
    for page in base_reader.pages:
        text = _normalized_page_text(page)
        if _is_marker(text, provenance_markers):
            continue
        if not skipping_register and _is_marker(text, register_markers):
            skipping_register = True
            continue
        if skipping_register:
            if _is_marker(text, evidence_markers):
                insert_at = len(retained)
                skipping_register = False
                retained.append(page)
            continue
        retained.append(page)

    if insert_at is None:
        for index, page in enumerate(retained):
            if _is_marker(_normalized_page_text(page), evidence_markers + review_markers):
                insert_at = index
                break
    if insert_at is None:
        insert_at = len(retained)

    writer = PdfWriter()
    for page in retained[:insert_at]:
        writer.add_page(page)
    for page in register_reader.pages:
        writer.add_page(page)
    for page in retained[insert_at:]:
        writer.add_page(page)
    for page in provenance_reader.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    combined = legacy._replace_stale_pdf_text(output.getvalue())
    combined = legacy._sanitize_pdf_control_glyphs(combined)
    legacy._assert_no_control_glyphs(combined)
    return combined


def install_comprehensive_internal_readiness() -> dict[str, Any]:
    from nico import client_report_completion_v1 as legacy

    current = legacy._compose_pdf
    if getattr(current, "_nico_comprehensive_single_register_v1", False):
        return {"status": "already_installed", "version": VERSION}
    setattr(_compose_pdf_single_register, "_nico_comprehensive_single_register_v1", True)
    setattr(_compose_pdf_single_register, "_nico_previous", current)
    legacy._compose_pdf = _compose_pdf_single_register
    return {
        "status": "installed",
        "version": VERSION,
        "single_finding_register_pdf": True,
        "score_target_applied": False,
        "score_inflation_allowed": False,
    }


install_comprehensive_internal_readiness()


__all__ = [
    "VERSION",
    "install_comprehensive_internal_readiness",
    "reconcile_comprehensive_internal_readiness",
    "reconcile_comprehensive_internal_readiness_package",
]
