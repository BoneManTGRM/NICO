from __future__ import annotations

from typing import Any

from nico import comprehensive_native_providers as providers
from nico.comprehensive_decision_grade_model_v5 import (
    VERSION,
    _bounded_int,
    _category_counts,
    _complexity_register,
    _dedupe_records,
    _record,
    _scanner_register,
    _score_band,
    _section,
    _text,
    _tools_for_category,
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_list(scan: dict[str, Any], key: str) -> list[str]:
    return [_text(item, 80).casefold() for item in scan.get(key) or []]


def _tool_groups(scan: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "unavailable": _tool_list(scan, "unavailable_tools"),
        "failed": _tool_list(scan, "failed_tools"),
        "timed_out": _tool_list(scan, "timed_out_tools"),
    }


def _category_tool_groups(tools: dict[str, list[str]], category: str) -> dict[str, list[str]]:
    return {
        key: _tools_for_category(values, category)
        for key, values in tools.items()
    }


def _code_risk_records(
    signals: dict[str, Any],
    commit_sha: str,
) -> tuple[int, list[str], list[dict[str, str]]]:
    code_hits = _bounded_int(signals.get("risk_pattern_hits"))
    samples = [str(item) for item in signals.get("risk_pattern_samples") or [] if str(item).strip()]
    records: list[dict[str, str]] = []
    if code_hits:
        for index, sample in enumerate(samples[:12], start=1):
            location, _, description = sample.partition(": ")
            records.append(
                _record(
                    record_id=f"code-risk-pattern-{index}",
                    priority="P1",
                    category="code",
                    title=description or "Bounded code-risk pattern requires disposition",
                    impact="Unsafe API patterns may create security or reliability defects and require exact-SHA human review.",
                    confidence="moderate",
                    evidence=f"risk_pattern_hits={code_hits}; exact immutable commit={commit_sha}",
                    location=location or "Location not retained by the bounded sample.",
                )
            )
        if not samples:
            records.append(
                _record(
                    record_id="code-risk-patterns",
                    priority="P1",
                    category="code",
                    title=f"{code_hits} bounded code-risk pattern hits require disposition",
                    impact="Unsafe API patterns may create security or reliability defects; the legacy summary did not retain exact locations.",
                    confidence="moderate",
                    evidence=f"risk_pattern_hits={code_hits}; exact immutable commit={commit_sha}",
                    location="Exact locations were not retained by the legacy bounded code-signal summary.",
                )
            )
    return code_hits, samples, records


def _workflow_risk_record(workflow: dict[str, Any]) -> tuple[int, int, list[dict[str, str]]]:
    successful = _bounded_int(workflow.get("successful_runs"))
    non_success = _bounded_int(workflow.get("non_success_runs"))
    records: list[dict[str, str]] = []
    if non_success:
        records.append(
            _record(
                record_id="ci-historical-non-success",
                priority="P1",
                category="ci_cd",
                title=f"{non_success} historical workflow runs were non-successful",
                impact="Unclassified failures obscure release reliability and can hide recurring operational defects.",
                confidence="high",
                evidence=f"successful_runs={successful}; non_success_runs={non_success}; bounded historical window",
                location="GitHub Actions bounded run history",
            )
        )
    return successful, non_success, records


def _finding_records(
    *,
    scan: dict[str, Any],
    complexity: dict[str, Any],
    signals: dict[str, Any],
    workflow: dict[str, Any],
    commit_sha: str,
) -> tuple[list[dict[str, str]], int, list[str], int, int]:
    code_hits, samples, code_records = _code_risk_records(signals, commit_sha)
    successful, non_success, workflow_records = _workflow_risk_record(workflow)
    records = [
        *_scanner_register(scan),
        *_complexity_register(complexity),
        *code_records,
        *workflow_records,
    ]
    return _dedupe_records(records), code_hits, samples, successful, non_success


def _dependency_control(
    dependency: dict[str, Any],
    counts: dict[str, int],
    tools: dict[str, list[str]],
) -> dict[str, Any]:
    score = 94
    findings: list[str] = []
    unavailable: list[str] = []
    if not dependency.get("lockfile_paths"):
        findings.append("No lockfile evidence was found in the captured snapshot.")
        score -= 10
    if counts["material"]:
        findings.append(f"{counts['material']} material dependency finding(s) require immediate disposition.")
        score -= min(45, counts["material"] * 15)
    if counts["review_required"]:
        findings.append(f"{counts['review_required']} dependency candidate(s) require human triage.")
        score -= min(18, counts["review_required"] * 2)
    gaps = tools["unavailable"] + tools["failed"] + tools["timed_out"]
    if gaps:
        unavailable.append("Dependency analyzer coverage incomplete: " + ", ".join(gaps) + ".")
        score -= min(18, 5 * len(set(gaps)))
    return {"score": score, "findings": findings, "unavailable": unavailable}


def _secret_control(
    signals: dict[str, Any],
    counts: dict[str, int],
    tools: dict[str, list[str]],
) -> dict[str, Any]:
    score = 96
    findings: list[str] = []
    unavailable: list[str] = []
    potential_patterns = _bounded_int(signals.get("potential_secret_pattern_hits"))
    if counts["material"]:
        findings.append(f"{counts['material']} verified material secret finding(s) require immediate response.")
        score -= min(60, counts["material"] * 20)
    if counts["review_required"]:
        findings.append(f"{counts['review_required']} secret candidate(s) require human triage.")
        score -= min(24, counts["review_required"] * 3)
    if potential_patterns:
        findings.append(f"{potential_patterns} bounded source-pattern candidate(s) require exact-location verification.")
        score -= min(18, potential_patterns * 3)
    gaps = tools["unavailable"] + tools["failed"] + tools["timed_out"]
    if gaps:
        unavailable.append(
            "Dedicated secret-history coverage incomplete: "
            + ", ".join(gaps)
            + ". No verified exposure is claimed from unavailable tools."
        )
        score -= min(20, 5 * len(set(gaps)))
    return {
        "score": score,
        "findings": findings,
        "unavailable": unavailable,
        "potential_patterns": potential_patterns,
    }


def _static_control(counts: dict[str, int], tools: dict[str, list[str]]) -> dict[str, Any]:
    score = 94
    findings: list[str] = []
    unavailable: list[str] = []
    if counts["material"]:
        findings.append(f"{counts['material']} material static-analysis finding(s) require immediate disposition.")
        score -= min(45, counts["material"] * 15)
    if counts["review_required"]:
        findings.append(f"{counts['review_required']} static-analysis candidate(s) require human triage.")
        score -= min(20, counts["review_required"] * 2)
    if tools["failed"]:
        findings.append(f"Failed static analyzers: {', '.join(tools['failed'])}.")
        score -= min(24, len(tools["failed"]) * 8)
    if tools["timed_out"]:
        findings.append(f"Timed-out static analyzers: {', '.join(tools['timed_out'])}.")
        score -= min(20, len(tools["timed_out"]) * 7)
    if tools["unavailable"]:
        unavailable.append(f"Unavailable static analyzers: {', '.join(tools['unavailable'])}.")
        score -= min(18, len(tools["unavailable"]) * 5)
    return {"score": score, "findings": findings, "unavailable": unavailable}


def _ci_control(workflow: dict[str, Any], successful: int, non_success: int) -> dict[str, Any]:
    score = 92
    findings: list[str] = []
    if non_success:
        findings.append(f"Historical workflow evidence includes {non_success} non-success run(s) requiring cause classification.")
        score -= min(18, non_success)
    if not workflow.get("explicit_permissions_present"):
        findings.append("Workflow configuration did not prove explicit permissions blocks.")
        score -= 7
    if successful == 0:
        findings.append("No successful workflow run was available in the bounded history window.")
        score -= 12
    return {"score": score, "findings": findings}


def _architecture_control(complexity: dict[str, Any]) -> dict[str, Any]:
    measured = complexity.get("complexity_score")
    score = int(measured) if isinstance(measured, (int, float)) else 78
    functions = _bounded_int(complexity.get("functions_measured"))
    high = _bounded_int(complexity.get("high_complexity_functions"))
    ratio = complexity.get("high_complexity_ratio")
    nesting = _bounded_int(complexity.get("deep_nesting_functions"))
    duplicate = _mapping(complexity.get("duplicate_evidence"))
    duplicate_ratio = duplicate.get("duplicate_line_ratio")
    findings: list[str] = []
    if high:
        findings.append(f"{high} high-complexity function or module region(s) require prioritization.")
    if isinstance(ratio, (int, float)) and ratio >= 0.15:
        findings.append(f"High-complexity ratio is {ratio:.1%} across the measured sample.")
    hotspots = complexity.get("hotspots") if isinstance(complexity.get("hotspots"), list) else []
    for hotspot in hotspots[:3]:
        if isinstance(hotspot, dict):
            findings.append(
                f"Hotspot {_text(hotspot.get('path'), 220)}:{_bounded_int(hotspot.get('line')) or 1} "
                f"measured complexity {_bounded_int(hotspot.get('cyclomatic_complexity'))}."
            )
    return {
        "score": score,
        "functions": functions,
        "high": high,
        "ratio": ratio,
        "nesting": nesting,
        "duplicate_ratio": duplicate_ratio,
        "findings": findings,
    }


def _velocity_control(activity: dict[str, Any]) -> dict[str, Any]:
    commits = _bounded_int(activity.get("commits_returned"))
    pulls = _bounded_int(activity.get("pull_requests_returned"))
    merged = _bounded_int(activity.get("merged_pull_requests"))
    complete = bool(commits and pulls)
    return {
        "commits": commits,
        "pulls": pulls,
        "merged": merged,
        "score": 84 if complete else 65,
        "findings": [] if complete else ["Commit or pull-request history was incomplete for delivery-process analysis."],
    }


def _code_section(
    architecture: dict[str, Any],
    records: list[dict[str, str]],
    code_hits: int,
    risk_samples: list[str],
) -> dict[str, Any]:
    code_records = [item["title"] for item in records if item["category"] == "code"]
    evidence_location = (
        "Exact file/line locations are retained for new code-risk samples."
        if risk_samples
        else "No new exact-location code-risk sample was retained in the legacy evidence."
    )
    findings = code_records or ([f"{code_hits} sampled code-risk pattern hit(s) require review."] if code_hits else [])
    return _section(
        "code_audit",
        "Code Audit",
        94 - min(18, code_hits * 2),
        "Exact-commit sampled code signals and repository structure were reviewed.",
        [
            f"Risk pattern hits: {code_hits}.",
            f"Test paths in tree: {_bounded_int(architecture.get('test_path_count'))}.",
            evidence_location,
        ],
        findings,
    )


def _dependency_section(
    dependency: dict[str, Any],
    counts: dict[str, int],
    control: dict[str, Any],
) -> dict[str, Any]:
    return _section(
        "dependency_health",
        "Dependency / Library Ecosystem",
        control["score"],
        "Manifest, lockfile, and dependency-analyzer evidence were reconciled by category.",
        [
            f"Dependency entries: {_bounded_int(dependency.get('dependency_entries'))}.",
            f"Lockfiles: {', '.join(dependency.get('lockfile_paths') or []) or 'none'}.",
            f"Dependency candidates: raw={counts['raw']}; material={counts['material']}; review_required={counts['review_required']}.",
        ],
        control["findings"],
        control["unavailable"],
        material_count=counts["material"],
    )


def _secret_section(
    scan: dict[str, Any],
    counts: dict[str, int],
    control: dict[str, Any],
) -> dict[str, Any]:
    return _section(
        "secrets_review",
        "Secrets Exposure Review",
        control["score"],
        "Secret evidence is classified independently from dependency and static-analysis candidates; unavailable history scanners do not create false secret findings.",
        [
            f"Secret candidates: raw={counts['raw']}; material={counts['material']}; review_required={counts['review_required']}.",
            f"Bounded source-pattern candidates: {control['potential_patterns']}.",
            f"Dedicated secret tools completed: {', '.join(_tools_for_category(scan.get('tools_run') or [], 'secret')) or 'none'}.",
        ],
        control["findings"],
        control["unavailable"],
        material_count=counts["material"],
    )


def _static_section(
    scan: dict[str, Any],
    counts: dict[str, int],
    control: dict[str, Any],
    tools: dict[str, list[str]],
) -> dict[str, Any]:
    return _section(
        "static_analysis",
        "Static Analysis",
        control["score"],
        "Static-analysis results are classified independently from dependency and secret evidence, with failed and unavailable analyzers disclosed separately.",
        [
            f"Static candidates: raw={counts['raw']}; material={counts['material']}; review_required={counts['review_required']}.",
            f"Completed static tools: {', '.join(_tools_for_category(scan.get('tools_run') or [], 'static')) or 'none'}.",
            f"Failed static tools: {', '.join(tools['failed']) or 'none'}.",
        ],
        control["findings"],
        control["unavailable"],
        material_count=counts["material"],
    )


def _ci_section(workflow: dict[str, Any], successful: int, non_success: int, control: dict[str, Any]) -> dict[str, Any]:
    success_rate = workflow.get("job_success_rate")
    return _section(
        "ci_cd",
        "CI/CD Analysis",
        control["score"],
        "Workflow configuration and bounded operational history were reviewed separately; non-success runs require cause classification rather than automatic defect claims.",
        [
            f"Workflow files: {_bounded_int(workflow.get('workflow_file_count'))}.",
            f"Successful runs: {successful}.",
            f"Non-success runs: {non_success}.",
            f"Jobs observed: {_bounded_int(workflow.get('jobs_observed'))}; job success rate: {success_rate if success_rate is not None else 'not available'}.",
        ],
        control["findings"],
    )


def _architecture_section(
    architecture: dict[str, Any],
    complexity: dict[str, Any],
    control: dict[str, Any],
) -> dict[str, Any]:
    ratio = control["ratio"]
    duplicate_ratio = control["duplicate_ratio"]
    ratio_text = f"{ratio:.1%}" if isinstance(ratio, (int, float)) else "not available"
    duplicate_text = f"{duplicate_ratio:.1%}" if isinstance(duplicate_ratio, (int, float)) else "not available"
    return _section(
        "architecture_debt",
        "Architecture & Technical Debt",
        control["score"],
        "Snapshot-bound source footprint, measured complexity, duplication, nesting, and named hotspots were evaluated.",
        [
            f"Source files: {_bounded_int(architecture.get('source_file_count'))}.",
            f"Files analyzed for complexity: {_bounded_int(complexity.get('files_analyzed'))}.",
            f"Functions or module regions measured: {control['functions']}.",
            f"High-complexity regions: {control['high']}; ratio: {ratio_text}.",
            f"Deep nesting regions: {control['nesting']}.",
            f"Duplicate-line ratio: {duplicate_text}.",
        ],
        control["findings"],
        list(complexity.get("unavailable_data_notes") or []),
    )


def _velocity_section(control: dict[str, Any]) -> dict[str, Any]:
    return _section(
        "velocity_complexity",
        "Velocity / Complexity",
        control["score"],
        "Commit, pull-request, workflow, source-footprint, and complexity evidence inform work-vs-expected review without claiming individual developer performance.",
        [
            f"Commits returned: {control['commits']}.",
            f"Pull requests returned: {control['pulls']}.",
            f"Merged pull requests: {control['merged']}.",
        ],
        control["findings"],
    )


def _sections(
    *,
    architecture: dict[str, Any],
    dependency: dict[str, Any],
    workflow: dict[str, Any],
    complexity: dict[str, Any],
    scan: dict[str, Any],
    records: list[dict[str, str]],
    code_hits: int,
    risk_samples: list[str],
    successful: int,
    non_success: int,
    counts: dict[str, dict[str, int]],
    category_tools: dict[str, dict[str, list[str]]],
    controls: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        _code_section(architecture, records, code_hits, risk_samples),
        _dependency_section(dependency, counts["dependency"], controls["dependency"]),
        _secret_section(scan, counts["secret"], controls["secret"]),
        _static_section(scan, counts["static"], controls["static"], category_tools["static"]),
        _ci_section(workflow, successful, non_success, controls["ci"]),
        _architecture_section(architecture, complexity, controls["architecture"]),
        _velocity_section(controls["velocity"]),
    ]


def _final_result(
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
    repo: dict[str, Any],
    scan: dict[str, Any],
    tools: dict[str, list[str]],
    counts: dict[str, dict[str, int]],
    records: list[dict[str, str]],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    scored = [int(item["presented_score"]) for item in sections if isinstance(item.get("presented_score"), int)]
    overall = round(sum(scored) / len(scored)) if scored else 0
    level = "Senior" if overall >= 82 else "Mid" if overall >= 58 else "Junior"
    unavailable_notes = sorted(set((repo.get("unavailable_data_notes") or []) + (scan.get("unavailable_data_notes") or [])))
    score_affecting = sum(len(item.get("findings") or []) + len(item.get("unavailable") or []) for item in sections)
    material = sum(counts[category]["material"] for category in ("dependency", "secret", "static"))
    review_required = sum(counts[category]["review_required"] for category in ("dependency", "secret", "static"))
    readiness = max(0, 100 - min(50, len(unavailable_notes) * 5 + len(tools["unavailable"]) * 5 + len(tools["failed"]) * 6))
    coverage = max(0, 100 - min(60, len(unavailable_notes) * 5 + len(tools["unavailable"]) * 7 + len(tools["failed"]) * 7))
    band = _score_band(overall)
    return {
        "status": "complete",
        "service_id": "comprehensive",
        "repository": repository,
        "commit_sha": commit_sha,
        "run_id": run_id,
        "executive_summary": f"Core technical evidence for {repository} at {commit_sha} produced an evidence-bound {level} maturity signal ({overall}/100). Technical score, evidence assurance, and client-delivery authorization are reported independently.",
        "maturity_signal": {
            "level": level,
            "score": overall,
            "source_score": overall,
            "presented_score": overall,
            "score_band": band["score_band"],
            "score_band_label": band["score_band_label"],
            "evidence_readiness_score": readiness,
        },
        "evidence_coverage": {
            "calculated": True,
            "percent": coverage,
            "label": "Automated evidence coverage",
        },
        "sections": sections,
        "findings_register": records,
        "limitation_metrics": {
            "assessment_wide_records": len(unavailable_notes),
            "score_affecting_records": score_affecting,
            "material_findings": material,
            "review_required_findings": review_required,
        },
        "unavailable_data_notes": unavailable_notes,
        "decision_grade_schema": VERSION,
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }


def build_decision_grade_assessment(
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
    repo: dict[str, Any],
    complexity: dict[str, Any],
    scan: dict[str, Any],
) -> dict[str, Any]:
    architecture = _mapping(repo.get("architecture_evidence"))
    dependency = _mapping(repo.get("dependency_evidence"))
    activity = _mapping(repo.get("activity_evidence"))
    workflow = _mapping(repo.get("workflow_evidence"))
    signals = _mapping(repo.get("code_signal_evidence"))
    tools = _tool_groups(scan)
    counts = {
        category: _category_counts(scan, category)
        for category in ("dependency", "secret", "static")
    }
    category_tools = {
        category: _category_tool_groups(tools, category)
        for category in ("dependency", "secret", "static")
    }
    records, code_hits, risk_samples, successful, non_success = _finding_records(
        scan=scan,
        complexity=complexity,
        signals=signals,
        workflow=workflow,
        commit_sha=commit_sha,
    )
    controls = {
        "dependency": _dependency_control(dependency, counts["dependency"], category_tools["dependency"]),
        "secret": _secret_control(signals, counts["secret"], category_tools["secret"]),
        "static": _static_control(counts["static"], category_tools["static"]),
        "ci": _ci_control(workflow, successful, non_success),
        "architecture": _architecture_control(complexity),
        "velocity": _velocity_control(activity),
    }
    sections = _sections(
        architecture=architecture,
        dependency=dependency,
        workflow=workflow,
        complexity=complexity,
        scan=scan,
        records=records,
        code_hits=code_hits,
        risk_samples=risk_samples,
        successful=successful,
        non_success=non_success,
        counts=counts,
        category_tools=category_tools,
        controls=controls,
    )
    return _final_result(
        repository=repository,
        commit_sha=commit_sha,
        run_id=run_id,
        repo=repo,
        scan=scan,
        tools=tools,
        counts=counts,
        records=records,
        sections=sections,
    )


def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = providers._repo(context)
    complexity = providers._complexity(context)
    scan = providers._scan(context)
    if not repo or scan.get("status") != "complete":
        return providers._result(context, "blocked", reason="complete_repository_and_scanner_evidence_required")
    assessment = build_decision_grade_assessment(
        repository=context["repository"],
        commit_sha=context["commit_sha"],
        run_id=context["run_id"],
        repo=repo,
        complexity=complexity,
        scan=scan,
    )
    maturity = assessment["maturity_signal"]
    metrics = assessment["limitation_metrics"]
    return providers._result(
        context,
        summary="Canonical decision-grade scoring completed with technical score, evidence assurance, and delivery authorization separated.",
        assessment=assessment,
        evidence={
            "maturity_level": maturity["level"],
            "technical_score": maturity["presented_score"],
            "technical_band": maturity["score_band_label"],
            "scored_sections": len(assessment["sections"]),
            "assessment_wide_limitation_records": metrics["assessment_wide_records"],
            "score_affecting_limitation_records": metrics["score_affecting_records"],
            "finding_register_count": len(assessment["findings_register"]),
        },
    )


__all__ = ["VERSION", "build_decision_grade_assessment", "canonical_scoring_provider"]
