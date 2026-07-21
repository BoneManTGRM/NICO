from __future__ import annotations

from typing import Any

from nico import comprehensive_native_providers as providers
from nico.comprehensive_decision_grade_model_v5 import (
    VERSION, _assurance, _bounded_int, _category_counts, _complexity_register,
    _dedupe_records, _record, _scanner_register, _score_band, _section,
    _text, _tools_for_category,
)

def build_decision_grade_assessment(
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
    repo: dict[str, Any],
    complexity: dict[str, Any],
    scan: dict[str, Any],
) -> dict[str, Any]:
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    dependency = repo.get("dependency_evidence") if isinstance(repo.get("dependency_evidence"), dict) else {}
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), dict) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    signals = repo.get("code_signal_evidence") if isinstance(repo.get("code_signal_evidence"), dict) else {}

    unavailable_tools = [_text(item, 80).casefold() for item in scan.get("unavailable_tools") or []]
    failed_tools = [_text(item, 80).casefold() for item in scan.get("failed_tools") or []]
    timed_out_tools = [_text(item, 80).casefold() for item in scan.get("timed_out_tools") or []]
    dependency_counts = _category_counts(scan, "dependency")
    secret_counts = _category_counts(scan, "secret")
    static_counts = _category_counts(scan, "static")

    records: list[dict[str, str]] = []
    records.extend(_scanner_register(scan))
    records.extend(_complexity_register(complexity))

    code_hits = _bounded_int(signals.get("risk_pattern_hits"))
    risk_samples = [str(item) for item in signals.get("risk_pattern_samples") or [] if str(item).strip()]
    if code_hits:
        for index, sample in enumerate(risk_samples[:12], start=1):
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
        if not risk_samples:
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

    successful = _bounded_int(workflow.get("successful_runs"))
    non_success = _bounded_int(workflow.get("non_success_runs"))
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

    records = _dedupe_records(records)

    dependency_findings: list[str] = []
    dependency_unavailable: list[str] = []
    dependency_score = 94
    if not dependency.get("lockfile_paths"):
        dependency_findings.append("No lockfile evidence was found in the captured snapshot.")
        dependency_score -= 10
    if dependency_counts["material"]:
        dependency_findings.append(f"{dependency_counts['material']} material dependency finding(s) require immediate disposition.")
        dependency_score -= min(45, dependency_counts["material"] * 15)
    if dependency_counts["review_required"]:
        dependency_findings.append(f"{dependency_counts['review_required']} dependency candidate(s) require human triage.")
        dependency_score -= min(18, dependency_counts["review_required"] * 2)
    unavailable_dependency = _tools_for_category(unavailable_tools, "dependency")
    failed_dependency = _tools_for_category(failed_tools, "dependency")
    timed_out_dependency = _tools_for_category(timed_out_tools, "dependency")
    if unavailable_dependency or failed_dependency or timed_out_dependency:
        dependency_unavailable.append(
            "Dependency analyzer coverage incomplete: "
            + ", ".join(unavailable_dependency + failed_dependency + timed_out_dependency)
            + "."
        )
        dependency_score -= min(18, 5 * len(set(unavailable_dependency + failed_dependency + timed_out_dependency)))

    secret_findings: list[str] = []
    secret_unavailable: list[str] = []
    secret_score = 96
    potential_secret_patterns = _bounded_int(signals.get("potential_secret_pattern_hits"))
    if secret_counts["material"]:
        secret_findings.append(f"{secret_counts['material']} verified material secret finding(s) require immediate response.")
        secret_score -= min(60, secret_counts["material"] * 20)
    if secret_counts["review_required"]:
        secret_findings.append(f"{secret_counts['review_required']} secret candidate(s) require human triage.")
        secret_score -= min(24, secret_counts["review_required"] * 3)
    if potential_secret_patterns:
        secret_findings.append(f"{potential_secret_patterns} bounded source-pattern candidate(s) require exact-location verification.")
        secret_score -= min(18, potential_secret_patterns * 3)
    unavailable_secret = _tools_for_category(unavailable_tools, "secret")
    failed_secret = _tools_for_category(failed_tools, "secret")
    timed_out_secret = _tools_for_category(timed_out_tools, "secret")
    if unavailable_secret or failed_secret or timed_out_secret:
        secret_unavailable.append(
            "Dedicated secret-history coverage incomplete: "
            + ", ".join(unavailable_secret + failed_secret + timed_out_secret)
            + ". No verified exposure is claimed from unavailable tools."
        )
        secret_score -= min(20, 5 * len(set(unavailable_secret + failed_secret + timed_out_secret)))

    static_findings: list[str] = []
    static_unavailable: list[str] = []
    static_score = 94
    if static_counts["material"]:
        static_findings.append(f"{static_counts['material']} material static-analysis finding(s) require immediate disposition.")
        static_score -= min(45, static_counts["material"] * 15)
    if static_counts["review_required"]:
        static_findings.append(f"{static_counts['review_required']} static-analysis candidate(s) require human triage.")
        static_score -= min(20, static_counts["review_required"] * 2)
    unavailable_static = _tools_for_category(unavailable_tools, "static")
    failed_static = _tools_for_category(failed_tools, "static")
    timed_out_static = _tools_for_category(timed_out_tools, "static")
    if failed_static:
        static_findings.append(f"Failed static analyzers: {', '.join(failed_static)}.")
        static_score -= min(24, len(failed_static) * 8)
    if timed_out_static:
        static_findings.append(f"Timed-out static analyzers: {', '.join(timed_out_static)}.")
        static_score -= min(20, len(timed_out_static) * 7)
    if unavailable_static:
        static_unavailable.append(f"Unavailable static analyzers: {', '.join(unavailable_static)}.")
        static_score -= min(18, len(unavailable_static) * 5)

    ci_findings: list[str] = []
    ci_score = 92
    if non_success:
        ci_findings.append(f"Historical workflow evidence includes {non_success} non-success run(s) requiring cause classification.")
        ci_score -= min(18, non_success)
    if not workflow.get("explicit_permissions_present"):
        ci_findings.append("Workflow configuration did not prove explicit permissions blocks.")
        ci_score -= 7
    if successful == 0:
        ci_findings.append("No successful workflow run was available in the bounded history window.")
        ci_score -= 12

    measured_complexity = complexity.get("complexity_score")
    architecture_score = int(measured_complexity) if isinstance(measured_complexity, (int, float)) else 78
    functions_measured = _bounded_int(complexity.get("functions_measured"))
    high_complexity = _bounded_int(complexity.get("high_complexity_functions"))
    high_ratio = complexity.get("high_complexity_ratio")
    deep_nesting = _bounded_int(complexity.get("deep_nesting_functions"))
    duplicate = complexity.get("duplicate_evidence") if isinstance(complexity.get("duplicate_evidence"), dict) else {}
    duplicate_ratio = duplicate.get("duplicate_line_ratio")
    architecture_findings: list[str] = []
    if high_complexity:
        architecture_findings.append(f"{high_complexity} high-complexity function or module region(s) require prioritization.")
    if isinstance(high_ratio, (int, float)) and high_ratio >= 0.15:
        architecture_findings.append(f"High-complexity ratio is {high_ratio:.1%} across the measured sample.")
    hotspots = complexity.get("hotspots") if isinstance(complexity.get("hotspots"), list) else []
    for hotspot in hotspots[:3]:
        if isinstance(hotspot, dict):
            architecture_findings.append(
                f"Hotspot {_text(hotspot.get('path'), 220)}:{_bounded_int(hotspot.get('line')) or 1} measured complexity {_bounded_int(hotspot.get('cyclomatic_complexity'))}."
            )

    commits = _bounded_int(activity.get("commits_returned"))
    pulls = _bounded_int(activity.get("pull_requests_returned"))
    merged_pulls = _bounded_int(activity.get("merged_pull_requests"))
    velocity_score = 84 if commits and pulls else 65
    velocity_findings = [] if commits and pulls else ["Commit or pull-request history was incomplete for delivery-process analysis."]

    code_records = [item["title"] for item in records if item["category"] == "code"]
    sections = [
        _section(
            "code_audit",
            "Code Audit",
            94 - min(18, code_hits * 2),
            "Exact-commit sampled code signals and repository structure were reviewed.",
            [
                f"Risk pattern hits: {code_hits}.",
                f"Test paths in tree: {_bounded_int(architecture.get('test_path_count'))}.",
                "Exact file/line locations are retained for new code-risk samples." if risk_samples else "No new exact-location code-risk sample was retained in the legacy evidence.",
            ],
            code_records or ([f"{code_hits} sampled code-risk pattern hit(s) require review."] if code_hits else []),
        ),
        _section(
            "dependency_health",
            "Dependency / Library Ecosystem",
            dependency_score,
            "Manifest, lockfile, and dependency-analyzer evidence were reconciled by category.",
            [
                f"Dependency entries: {_bounded_int(dependency.get('dependency_entries'))}.",
                f"Lockfiles: {', '.join(dependency.get('lockfile_paths') or []) or 'none'}.",
                f"Dependency candidates: raw={dependency_counts['raw']}; material={dependency_counts['material']}; review_required={dependency_counts['review_required']}.",
            ],
            dependency_findings,
            dependency_unavailable,
            material_count=dependency_counts["material"],
        ),
        _section(
            "secrets_review",
            "Secrets Exposure Review",
            secret_score,
            "Secret evidence is classified independently from dependency and static-analysis candidates; unavailable history scanners do not create false secret findings.",
            [
                f"Secret candidates: raw={secret_counts['raw']}; material={secret_counts['material']}; review_required={secret_counts['review_required']}.",
                f"Bounded source-pattern candidates: {potential_secret_patterns}.",
                f"Dedicated secret tools completed: {', '.join(_tools_for_category(scan.get('tools_run') or [], 'secret')) or 'none'}.",
            ],
            secret_findings,
            secret_unavailable,
            material_count=secret_counts["material"],
        ),
        _section(
            "static_analysis",
            "Static Analysis",
            static_score,
            "Static-analysis results are classified independently from dependency and secret evidence, with failed and unavailable analyzers disclosed separately.",
            [
                f"Static candidates: raw={static_counts['raw']}; material={static_counts['material']}; review_required={static_counts['review_required']}.",
                f"Completed static tools: {', '.join(_tools_for_category(scan.get('tools_run') or [], 'static')) or 'none'}.",
                f"Failed static tools: {', '.join(failed_static) or 'none'}.",
            ],
            static_findings,
            static_unavailable,
            material_count=static_counts["material"],
        ),
        _section(
            "ci_cd",
            "CI/CD Analysis",
            ci_score,
            "Workflow configuration and bounded operational history were reviewed separately; non-success runs require cause classification rather than automatic defect claims.",
            [
                f"Workflow files: {_bounded_int(workflow.get('workflow_file_count'))}.",
                f"Successful runs: {successful}.",
                f"Non-success runs: {non_success}.",
                f"Jobs observed: {_bounded_int(workflow.get('jobs_observed'))}; job success rate: {workflow.get('job_success_rate') if workflow.get('job_success_rate') is not None else 'not available'}.",
            ],
            ci_findings,
        ),
        _section(
            "architecture_debt",
            "Architecture & Technical Debt",
            architecture_score,
            "Snapshot-bound source footprint, measured complexity, duplication, nesting, and named hotspots were evaluated.",
            [
                f"Source files: {_bounded_int(architecture.get('source_file_count'))}.",
                f"Files analyzed for complexity: {_bounded_int(complexity.get('files_analyzed'))}.",
                f"Functions or module regions measured: {functions_measured}.",
                f"High-complexity regions: {high_complexity}; ratio: {high_ratio:.1%}." if isinstance(high_ratio, (int, float)) else f"High-complexity regions: {high_complexity}; ratio: not available.",
                f"Deep nesting regions: {deep_nesting}.",
                f"Duplicate-line ratio: {duplicate_ratio:.1%}." if isinstance(duplicate_ratio, (int, float)) else "Duplicate-line ratio: not available.",
            ],
            architecture_findings,
            list(complexity.get("unavailable_data_notes") or []),
        ),
        _section(
            "velocity_complexity",
            "Velocity / Complexity",
            velocity_score,
            "Commit, pull-request, workflow, source-footprint, and complexity evidence inform work-vs-expected review without claiming individual developer performance.",
            [
                f"Commits returned: {commits}.",
                f"Pull requests returned: {pulls}.",
                f"Merged pull requests: {merged_pulls}.",
            ],
            velocity_findings,
        ),
    ]

    scored = [int(item["presented_score"]) for item in sections if isinstance(item.get("presented_score"), int)]
    overall = round(sum(scored) / len(scored)) if scored else 0
    level = "Senior" if overall >= 82 else "Mid" if overall >= 58 else "Junior"
    unavailable_notes = sorted(set((repo.get("unavailable_data_notes") or []) + (scan.get("unavailable_data_notes") or [])))
    score_affecting = sum(len(item.get("findings") or []) + len(item.get("unavailable") or []) for item in sections)
    limitation_metrics = {
        "assessment_wide_records": len(unavailable_notes),
        "score_affecting_records": score_affecting,
        "material_findings": sum(_category_counts(scan, category)["material"] for category in ("dependency", "secret", "static")),
        "review_required_findings": sum(_category_counts(scan, category)["review_required"] for category in ("dependency", "secret", "static")),
    }
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
            "score_band": _score_band(overall)["score_band"],
            "score_band_label": _score_band(overall)["score_band_label"],
            "evidence_readiness_score": max(0, 100 - min(50, len(unavailable_notes) * 5 + len(unavailable_tools) * 5 + len(failed_tools) * 6)),
        },
        "evidence_coverage": {
            "calculated": True,
            "percent": max(0, 100 - min(60, len(unavailable_notes) * 5 + len(unavailable_tools) * 7 + len(failed_tools) * 7)),
            "label": "Automated evidence coverage",
        },
        "sections": sections,
        "findings_register": records,
        "limitation_metrics": limitation_metrics,
        "unavailable_data_notes": unavailable_notes,
        "decision_grade_schema": VERSION,
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }


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



__all__ = ["build_decision_grade_assessment", "canonical_scoring_provider"]
