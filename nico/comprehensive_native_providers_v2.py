from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI

from nico import comprehensive_native_providers as legacy
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

VERSION = "nico.comprehensive-native-providers.v2"

_DEPENDENCY_TOOLS = ("pip-audit", "npm-audit", "osv-scanner")
_STATIC_TOOLS = ("bandit", "semgrep", "eslint", "typescript")
_SECRET_TOOLS = ("gitleaks", "trufflehog")


def _bounded(value: float | int) -> int:
    return max(0, min(100, int(round(value))))


def _tool_results(scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results = scan.get("scanner_results") if isinstance(scan.get("scanner_results"), list) else []
    output: dict[str, dict[str, Any]] = {}
    for raw in results:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("scanner_name") or raw.get("tool") or raw.get("scanner") or "").strip().casefold()
        if name:
            output[name] = raw
    return output


def _summary_by_tool(scan: dict[str, Any]) -> dict[str, dict[str, int]]:
    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), dict) else {}
    values = summary.get("by_tool") if isinstance(summary.get("by_tool"), dict) else {}
    output: dict[str, dict[str, int]] = {}
    for name, raw in values.items():
        if not isinstance(raw, dict):
            continue
        output[str(name).casefold()] = {
            key: int(raw.get(key) or 0)
            for key in ("raw", "material", "review_required", "approved_or_nonblocking", "excluded_test_only")
        }
    return output


def _group_counts(scan: dict[str, Any], tools: tuple[str, ...]) -> dict[str, int]:
    by_tool = _summary_by_tool(scan)
    results = _tool_results(scan)
    counts = {key: 0 for key in ("raw", "material", "review_required", "approved_or_nonblocking", "excluded_test_only")}
    for tool in tools:
        record = by_tool.get(tool, {})
        for key in counts:
            counts[key] += int(record.get(key) or 0)
        payload = results.get(tool, {})
        counts["approved_or_nonblocking"] += int(payload.get("verified_example_placeholder_count") or 0)
        raw_disposition = payload.get("secret_candidate_disposition")
        if isinstance(raw_disposition, dict):
            counts["raw"] = max(
                counts["raw"],
                int(raw_disposition.get("raw_candidate_count") or 0),
            )
    return counts


def _incomplete_tools(scan: dict[str, Any], tools: tuple[str, ...]) -> list[str]:
    results = _tool_results(scan)
    incomplete: list[str] = []
    for tool in tools:
        record = results.get(tool)
        if not record:
            incomplete.append(tool)
            continue
        complete = (
            str(record.get("status") or "").casefold() == "completed"
            and record.get("completed") is True
            and record.get("verified") is True
            and record.get("exact_commit_match") is True
            and record.get("raw_artifact_retention_complete") is True
        )
        if not complete:
            incomplete.append(tool)
    return incomplete


def _finding_penalty(counts: dict[str, int], *, material_weight: int, review_weight: int, cap: int) -> int:
    return min(
        cap,
        counts["material"] * material_weight + counts["review_required"] * review_weight,
    )


def _scanner_section(
    section_id: str,
    label: str,
    scan: dict[str, Any],
    tools: tuple[str, ...],
    *,
    summary: str,
    material_weight: int,
    review_weight: int,
    maximum_penalty: int,
) -> dict[str, Any]:
    counts = _group_counts(scan, tools)
    incomplete = _incomplete_tools(scan, tools)
    penalty = _finding_penalty(
        counts,
        material_weight=material_weight,
        review_weight=review_weight,
        cap=maximum_penalty,
    )
    score = _bounded(96 - penalty - min(24, len(incomplete) * 8))
    findings: list[str] = []
    unavailable: list[str] = []
    if counts["material"]:
        findings.append(f"{counts['material']} verified material finding(s) require disposition.")
    if counts["review_required"]:
        findings.append(f"{counts['review_required']} review-required candidate(s) remain unconfirmed.")
    if incomplete:
        unavailable.append(f"Incomplete applicable analyzers: {', '.join(incomplete)}.")
    evidence = [
        f"Applicable analyzers: {', '.join(tools)}.",
        f"Raw candidates: {counts['raw']}.",
        f"Verified material: {counts['material']}.",
        f"Review required: {counts['review_required']}.",
        f"Approved/nonblocking: {counts['approved_or_nonblocking']}.",
        f"Excluded non-production/test-only: {counts['excluded_test_only']}.",
    ]
    return legacy._section(section_id, label, score, summary, evidence, findings, unavailable)


def _ci_score(workflow: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    score = 70
    evidence: list[str] = []
    findings: list[str] = []
    workflow_files = int(workflow.get("workflow_file_count") or 0)
    successful = int(workflow.get("successful_runs") or 0)
    non_success = int(workflow.get("non_success_runs") or 0)
    job_rate_raw = workflow.get("job_success_rate")
    job_rate = float(job_rate_raw) if isinstance(job_rate_raw, (int, float)) else 0.0
    controls = workflow.get("configuration_controls") if isinstance(workflow.get("configuration_controls"), dict) else {}
    control_count = int(controls.get("control_count") or sum(value is True for value in controls.values()))
    deployments = int(workflow.get("deployments_observed") or 0)
    successful_deployments = int(workflow.get("successful_deployments") or 0)
    runs_matching_snapshot = int(workflow.get("runs_matching_snapshot_sha") or 0)

    if workflow_files:
        score += 6
    else:
        findings.append("No workflow configuration was retained at the assessed commit.")
    if workflow.get("explicit_permissions_present") is True:
        score += 6
    else:
        findings.append("Explicit workflow permission boundaries were not proven.")
    if control_count >= 9:
        score += 6
    elif control_count >= 5:
        score += 3
    if job_rate >= 0.98:
        score += 6
    elif job_rate >= 0.90:
        score += 3
    elif workflow.get("jobs_observed"):
        findings.append("Current bounded job success evidence is below 90%.")
    if deployments and successful_deployments / deployments >= 0.70:
        score += 4
    if runs_matching_snapshot:
        score += 4
    if successful == 0:
        score -= 10
        findings.append("No successful workflow run was retained in the bounded history window.")
    if non_success:
        findings.append(
            f"Historical evidence retains {non_success} non-success run(s); this remains a trend signal and is not treated as current-code failure."
        )
    evidence.extend(
        [
            f"Workflow files: {workflow_files}.",
            f"Successful runs: {successful}.",
            f"Historical non-success runs: {non_success}.",
            f"Jobs observed: {int(workflow.get('jobs_observed') or 0)}; success rate: {job_rate:.3f}.",
            f"Configuration controls: {control_count}.",
            f"Deployments: {successful_deployments}/{deployments} successful.",
            f"Runs matching assessed SHA: {runs_matching_snapshot}.",
        ]
    )
    return _bounded(score), evidence, findings


def _velocity_score(activity: dict[str, Any], workflow: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    commits = int(activity.get("commits_returned") or 0)
    pulls = int(activity.get("pull_requests_returned") or 0)
    merged = int(activity.get("merged_pull_requests") or 0)
    job_rate_raw = workflow.get("job_success_rate")
    job_rate = float(job_rate_raw) if isinstance(job_rate_raw, (int, float)) else 0.0
    score = 62
    findings: list[str] = []
    if commits >= 50:
        score += 10
    elif commits:
        score += 5
    else:
        findings.append("Commit history was unavailable for delivery-process analysis.")
    if pulls >= 50:
        score += 10
    elif pulls:
        score += 5
    else:
        findings.append("Pull-request history was unavailable for delivery-process analysis.")
    merge_ratio = merged / pulls if pulls else 0.0
    if merge_ratio >= 0.75:
        score += 7
    elif merge_ratio >= 0.50:
        score += 4
    if job_rate >= 0.98:
        score += 7
    elif job_rate >= 0.90:
        score += 4
    evidence = [
        f"Commits returned: {commits}.",
        f"Pull requests returned: {pulls}.",
        f"Merged pull requests: {merged}; merge ratio: {merge_ratio:.3f}.",
        f"Observed job success rate: {job_rate:.3f}.",
    ]
    return _bounded(score), evidence, findings


def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = legacy._repo(context)
    complexity = legacy._complexity(context)
    scan = legacy._scan(context)
    if not repo or scan.get("status") != "complete":
        return legacy._result(context, "blocked", reason="complete_repository_and_scanner_evidence_required")

    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    dependency = repo.get("dependency_evidence") if isinstance(repo.get("dependency_evidence"), dict) else {}
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), dict) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    signals = repo.get("code_signal_evidence") if isinstance(repo.get("code_signal_evidence"), dict) else {}

    code_hits = int(signals.get("risk_pattern_hits") or 0)
    code_score = _bounded(96 - min(48, code_hits * 8))
    code_findings = [
        f"{code_hits} executable first-party code-risk finding(s) require exact-source disposition."
    ] if code_hits else []
    code_evidence = [
        f"Executable code-risk findings: {code_hits}.",
        f"Excluded non-production observations: {int(signals.get('excluded_non_production_risk_count') or 0)}.",
        f"Example placeholder secrets retained separately: {int(signals.get('verified_example_placeholder_secret_count') or 0)}.",
        f"Source analysis: {signals.get('analysis_version') or 'legacy'}; comments/strings excluded={signals.get('comments_and_strings_excluded') is True}.",
        f"Test paths in tree: {int(architecture.get('test_path_count') or 0)}.",
    ]

    dependency_section = _scanner_section(
        "dependency_health",
        "Dependency / Library Ecosystem",
        scan,
        _DEPENDENCY_TOOLS,
        summary="Authoritative manifests and contextual dependency-analyzer evidence were reconciled by package, installed version, advisory, fixed version, path, scope, and reachability.",
        material_weight=18,
        review_weight=2,
        maximum_penalty=50,
    )
    if not dependency.get("lockfile_paths"):
        dependency_section["findings"].append("No lockfile evidence was retained in the captured snapshot.")
        dependency_section["score"] = dependency_section["presented_score"] = max(
            0, int(dependency_section["presented_score"]) - 10
        )

    secret_section = _scanner_section(
        "secrets_review",
        "Secrets Exposure Review",
        scan,
        _SECRET_TOOLS,
        summary="History-aware secret evidence was separated into verified material findings, review-required candidates, explicit example placeholders, and non-production observations.",
        material_weight=25,
        review_weight=2,
        maximum_penalty=55,
    )
    static_section = _scanner_section(
        "static_analysis",
        "Static Analysis",
        scan,
        _STATIC_TOOLS,
        summary="Bandit, Semgrep, ESLint, and TypeScript evidence were evaluated independently against the exact immutable commit.",
        material_weight=16,
        review_weight=3,
        maximum_penalty=48,
    )

    ci_score, ci_evidence, ci_findings = _ci_score(workflow)
    measured_complexity = complexity.get("complexity_score")
    architecture_score = int(measured_complexity) if isinstance(measured_complexity, (int, float)) else 78
    architecture_findings: list[str] = []
    if str(complexity.get("risk_level") or complexity.get("risk") or "").casefold() in {"high", "critical"}:
        architecture_findings.append("Complexity evidence reports concentrated high-risk hotspots.")
    velocity_score, velocity_evidence, velocity_findings = _velocity_score(activity, workflow)

    sections = [
        legacy._section(
            "code_audit",
            "Code Audit",
            code_score,
            "Exact-commit executable source signals were analyzed without promoting comments, strings, detector definitions, examples, or tests.",
            code_evidence,
            code_findings,
        ),
        dependency_section,
        secret_section,
        static_section,
        legacy._section(
            "ci_cd",
            "CI/CD Analysis",
            ci_score,
            "Current job, deployment, exact-SHA, workflow-control, and separately labeled historical evidence were evaluated.",
            ci_evidence,
            ci_findings,
        ),
        legacy._section(
            "architecture_debt",
            "Architecture & Technical Debt",
            architecture_score,
            "Snapshot-bound source footprint and measured complexity evidence were evaluated without score override.",
            [
                f"Source files: {int(architecture.get('source_file_count') or 0)}.",
                f"Files analyzed for complexity: {int(complexity.get('files_analyzed') or 0)}.",
                f"Complexity risk: {legacy._text(complexity.get('risk_level') or complexity.get('risk') or 'unknown')}.",
            ],
            architecture_findings,
        ),
        legacy._section(
            "velocity_complexity",
            "Velocity / Complexity",
            velocity_score,
            "Commit, pull-request, merge, and current job evidence inform delivery throughput without evaluating individual developer performance.",
            velocity_evidence,
            velocity_findings,
        ),
    ]

    scored = [int(item["presented_score"]) for item in sections if isinstance(item.get("presented_score"), int)]
    overall = round(sum(scored) / len(scored)) if scored else 0
    applicable_tools = (*_DEPENDENCY_TOOLS, *_STATIC_TOOLS, *_SECRET_TOOLS)
    incomplete = _incomplete_tools(scan, applicable_tools)
    analyzer_coverage = round(100 * (len(applicable_tools) - len(incomplete)) / len(applicable_tools))
    evidence_adjusted = min(overall, round(overall * 0.8 + analyzer_coverage * 0.2))
    level = "Senior" if overall >= 82 else "Mid" if overall >= 58 else "Junior"
    unavailable_notes = sorted(set((repo.get("unavailable_data_notes") or []) + (scan.get("unavailable_data_notes") or [])))

    assessment = {
        "status": "complete",
        "service_id": "comprehensive",
        "repository": context["repository"],
        "commit_sha": context["commit_sha"],
        "run_id": context["run_id"],
        "executive_summary": (
            f"Exact-SHA technical evidence for {context['repository']} produced an evidence-bound "
            f"{level} maturity signal ({overall}/100) and independently evidence-adjusted score "
            f"of {evidence_adjusted}/100. No score was raised without retained evidence."
        ),
        "technical_score": overall,
        "canonical_evidence_adjusted_score": evidence_adjusted,
        "evidence_adjusted_score": evidence_adjusted,
        "maturity_signal": {
            "level": level,
            "score": overall,
            "source_score": overall,
            "presented_score": overall,
            "technical_score": overall,
            "canonical_evidence_adjusted_score": evidence_adjusted,
            "evidence_adjusted_score": evidence_adjusted,
            "evidence_readiness_score": analyzer_coverage,
        },
        "evidence_coverage": {
            "calculated": True,
            "percent": analyzer_coverage,
            "label": "Applicable exact-SHA analyzer coverage",
            "applicable_analyzers": len(applicable_tools),
            "completed_verified_analyzers": len(applicable_tools) - len(incomplete),
            "incomplete_analyzers": incomplete,
        },
        "score_contract": {
            "version": VERSION,
            "target_score_not_used_as_input": True,
            "score_override_allowed": False,
            "category_specific_scanner_populations": True,
            "historical_failures_separate_from_current_health": True,
            "comments_strings_examples_and_tests_not_code_defects": True,
            "technical_score": overall,
            "evidence_adjusted_score": evidence_adjusted,
        },
        "sections": sections,
        "unavailable_data_notes": unavailable_notes,
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }
    return legacy._result(
        context,
        summary="Canonical technical and evidence-adjusted scoring completed from category-specific retained evidence without commercial score targeting.",
        assessment=assessment,
        evidence={
            "maturity_level": level,
            "technical_score": overall,
            "evidence_adjusted_score": evidence_adjusted,
            "scored_sections": len(scored),
            "applicable_analyzer_coverage": analyzer_coverage,
            "unavailable_note_count": len(unavailable_notes),
        },
    )


def native_comprehensive_providers() -> dict[str, legacy.Provider]:
    providers = legacy.native_comprehensive_providers()
    providers["canonical_scoring"] = canonical_scoring_provider
    return providers


def install_native_comprehensive_providers(app: FastAPI) -> dict[str, legacy.Provider]:
    existing = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(existing) if isinstance(existing, dict) else {}
    providers.update(native_comprehensive_providers())
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    app.state.nico_native_comprehensive_provider_status = {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "provider_count": len(providers),
        "providers": sorted(providers),
        "category_specific_scoring_bound": providers.get("canonical_scoring") is canonical_scoring_provider,
        "score_override_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return providers


__all__ = [
    "VERSION",
    "canonical_scoring_provider",
    "install_native_comprehensive_providers",
    "native_comprehensive_providers",
]
