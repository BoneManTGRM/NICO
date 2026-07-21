from __future__ import annotations

import base64
import hashlib
from typing import Any, Callable

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.comprehensive_report_package import build_comprehensive_report_package
from nico.repository_snapshot import capture_repository_snapshot
from nico.scanner_worker import get_scan
from nico.snapshot_repository_evidence import collect_snapshot_repository_evidence
from nico.snapshot_scanner_worker import start_snapshot_scan

VERSION = "nico.comprehensive_native_providers.v1"
Provider = Callable[[dict[str, Any]], dict[str, Any]]


def _text(value: Any, limit: int = 900) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _prior(context: dict[str, Any], stage_id: str) -> dict[str, Any]:
    stages = context.get("prior_stage_results")
    if not isinstance(stages, dict):
        return {}
    value = stages.get(stage_id)
    return value if isinstance(value, dict) else {}


def _identity(context: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id", "customer_id", "project_id"):
        value = _text(context.get(field), 180)
        if not value:
            raise ValueError(f"{field}_required")
        output[field] = value
    return output


def _result(context: dict[str, Any], status: str = "complete", **payload: Any) -> dict[str, Any]:
    identity = _identity(context)
    return {
        "status": status,
        **payload,
        "run_id": identity["run_id"],
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "evidence_ledger_id": identity["evidence_ledger_id"],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _snapshot(context: dict[str, Any]) -> dict[str, Any]:
    value = _prior(context, "immutable_repository_snapshot").get("snapshot")
    return value if isinstance(value, dict) else {}


def _repo(context: dict[str, Any]) -> dict[str, Any]:
    value = _prior(context, "repository_and_delivery_evidence").get("repository_evidence")
    return value if isinstance(value, dict) else {}


def _complexity(context: dict[str, Any]) -> dict[str, Any]:
    value = _prior(context, "repository_and_delivery_evidence").get("complexity_evidence")
    return value if isinstance(value, dict) else {}


def _scan_id(context: dict[str, Any]) -> str:
    for stage_id in ("dependency_security_static_analysis", "deep_scanner_triage"):
        previous = _prior(context, stage_id)
        direct = _text(previous.get("scan_id"), 120)
        if direct:
            return direct
        scanner = previous.get("scanner")
        if isinstance(scanner, dict):
            nested = _text(scanner.get("scan_id"), 120)
            if nested:
                return nested
    return ""


def _scan(context: dict[str, Any]) -> dict[str, Any]:
    scan_id = _scan_id(context)
    return get_scan(scan_id) if scan_id else {}


def _counts(scan: dict[str, Any]) -> dict[str, int]:
    summary = scan.get("finding_summary") if isinstance(scan.get("finding_summary"), dict) else {}
    return {
        "raw": int(scan.get("finding_count") or summary.get("raw_total") or 0),
        "material": int(scan.get("material_finding_count") or summary.get("material_total") or 0),
        "review": int(scan.get("review_required_finding_count") or summary.get("review_required_total") or 0),
        "excluded": int(scan.get("excluded_test_only_finding_count") or summary.get("excluded_test_only_total") or 0),
    }


def _section(section_id: str, label: str, score: int | None, summary: str, evidence: list[str], findings: list[str] | None = None, unavailable: list[str] | None = None) -> dict[str, Any]:
    findings = findings or []
    unavailable = unavailable or []
    if score is None:
        return {"id": section_id, "label": label, "score": None, "presented_score": None, "status": "gray", "presented_status": "gray", "exclude_from_maturity": True, "summary": summary, "evidence": evidence, "findings": findings, "unavailable": unavailable}
    bounded = max(0, min(100, int(score)))
    status = "red" if bounded < 45 else "yellow" if bounded < 75 or findings or unavailable else "green"
    return {"id": section_id, "label": label, "score": bounded, "source_score": bounded, "presented_score": bounded, "status": status, "presented_status": status, "summary": summary, "evidence": evidence, "findings": findings, "unavailable": unavailable}


def snapshot_provider(context: dict[str, Any]) -> dict[str, Any]:
    snapshot = capture_repository_snapshot(context)
    expected = _text(context.get("commit_sha"), 80).lower()
    actual = _text(snapshot.get("commit_sha"), 80).lower()
    if snapshot.get("status") != "attached" or not actual:
        return _result(context, "blocked", reason="immutable_snapshot_unavailable", snapshot=snapshot, unavailable_data_notes=snapshot.get("unavailable_data_notes") or ["The immutable repository snapshot was unavailable."])
    if actual != expected:
        return _result(context, "blocked", reason="immutable_snapshot_identity_drift", expected_commit_sha=expected, observed_commit_sha=actual, snapshot=snapshot)
    return _result(context, summary="The authorized repository was bound to one immutable commit before evidence collection.", snapshot=snapshot, evidence={"snapshot_id": snapshot.get("snapshot_id"), "commit_sha": actual, "tree_sha": snapshot.get("tree_sha"), "default_branch": snapshot.get("default_branch"), "captured_at": snapshot.get("captured_at")})


def repository_evidence_provider(context: dict[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot(context)
    if snapshot.get("status") != "attached":
        return _result(context, "blocked", reason="attached_snapshot_required")
    repository_evidence, complexity_evidence = collect_snapshot_repository_evidence({**context, "authorized_by": "comprehensive_native_provider", "authorization_scope": "authorized defensive repository assessment", "timeframe_days": 180}, snapshot)
    if repository_evidence.get("status") != "attached":
        return _result(context, "blocked", reason="snapshot_repository_evidence_unavailable", repository_evidence=repository_evidence, complexity_evidence=complexity_evidence, unavailable_data_notes=repository_evidence.get("unavailable_data_notes") or [])
    files = repository_evidence.get("file_evidence") if isinstance(repository_evidence.get("file_evidence"), dict) else {}
    architecture = repository_evidence.get("architecture_evidence") if isinstance(repository_evidence.get("architecture_evidence"), dict) else {}
    workflows = repository_evidence.get("workflow_evidence") if isinstance(repository_evidence.get("workflow_evidence"), dict) else {}
    return _result(context, summary="Exact-commit repository, dependency, architecture, workflow, activity, and complexity evidence were attached.", repository_evidence=repository_evidence, complexity_evidence=complexity_evidence, evidence={"repository_evidence_id": repository_evidence.get("evidence_id"), "complexity_evidence_id": complexity_evidence.get("evidence_id"), "snapshot_commit_sha": repository_evidence.get("snapshot_commit_sha"), "files_profiled": files.get("files_profiled", 0), "tree_paths_seen": files.get("tree_paths_seen", 0), "source_file_count": architecture.get("source_file_count", 0), "test_path_count": architecture.get("test_path_count", 0), "workflow_file_count": workflows.get("workflow_file_count", 0)}, unavailable_data_notes=repository_evidence.get("unavailable_data_notes") or [])


def scanner_suite_provider(context: dict[str, Any]) -> dict[str, Any]:
    snapshot = _snapshot(context)
    if snapshot.get("status") != "attached":
        return _result(context, "blocked", reason="attached_snapshot_required")
    scan_id = _scan_id(context)
    scan = get_scan(scan_id) if scan_id else start_snapshot_scan({"repository": context["repository"], "authorized": True, "customer_id": context["customer_id"], "project_id": context["project_id"], "run_id": context["run_id"], "authorized_by": "comprehensive_native_provider", "authorization_scope": "authorized defensive repository assessment", "snapshot_id": snapshot.get("snapshot_id"), "snapshot_commit_sha": snapshot.get("commit_sha"), "tools": []})
    status = _text(scan.get("status"), 40).lower()
    if status in {"queued", "running"}:
        return _result(context, "running", summary="The modern scanner suite is executing against the exact immutable commit.", scan_id=scan.get("scan_id"), scanner={"scan_id": scan.get("scan_id"), "status": status, "current_stage": scan.get("current_stage"), "active_tool": scan.get("active_tool"), "progress_percent": scan.get("progress_percent"), "snapshot_commit_sha": scan.get("snapshot_commit_sha")}, evidence={"scan_id": scan.get("scan_id"), "active_tool": scan.get("active_tool"), "progress_percent": scan.get("progress_percent"), "snapshot_commit_sha": scan.get("snapshot_commit_sha")})
    if status != "complete" or scan.get("snapshot_match") is not True:
        return _result(context, "blocked", reason="snapshot_scanner_not_verified", scan_id=scan.get("scan_id"), scanner_status=status or "unavailable", unavailable_data_notes=scan.get("unavailable_data_notes") or ["Scanner output did not verify the immutable snapshot."])
    counts = _counts(scan)
    return _result(context, summary="Dependency, static-analysis, secret, TypeScript, and history-aware scanner output was verified against the immutable commit.", scan_id=scan.get("scan_id"), scanner={"scan_id": scan.get("scan_id"), "status": "complete", "snapshot_match": True, "actual_commit_sha": scan.get("actual_commit_sha"), "tools_requested": scan.get("tools_requested") or [], "tools_run": scan.get("tools_run") or [], "unavailable_tools": scan.get("unavailable_tools") or [], "failed_tools": scan.get("failed_tools") or [], "timed_out_tools": scan.get("timed_out_tools") or [], "finding_summary": scan.get("finding_summary") or {}}, evidence={"scan_id": scan.get("scan_id"), "snapshot_match": True, "actual_commit_sha": scan.get("actual_commit_sha"), "tools_run": scan.get("tools_run") or [], **counts}, unavailable_data_notes=scan.get("unavailable_data_notes") or [])


def technical_analysis_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    complexity = _complexity(context)
    if not repo:
        return _result(context, "blocked", reason="repository_evidence_required")
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), dict) else {}
    workflows = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    return _result(context, summary="CI/CD, architecture, source footprint, complexity, ownership, churn, and delivery velocity were analyzed from snapshot-bound and separately labeled historical evidence.", technical_analysis={"architecture": architecture, "activity": activity, "workflow": workflows, "complexity": complexity}, evidence={"source_file_count": architecture.get("source_file_count", 0), "test_path_count": architecture.get("test_path_count", 0), "deployment_manifests": architecture.get("deployment_manifests") or [], "workflow_file_count": workflows.get("workflow_file_count", 0), "workflow_run_count": workflows.get("workflow_run_count", 0), "successful_runs": workflows.get("successful_runs", 0), "non_success_runs": workflows.get("non_success_runs", 0), "commits_returned": activity.get("commits_returned", 0), "pull_requests_returned": activity.get("pull_requests_returned", 0), "files_analyzed": complexity.get("files_analyzed", 0), "source_loc": complexity.get("source_loc", complexity.get("loc", 0)), "complexity_score": complexity.get("complexity_score"), "risk_level": complexity.get("risk_level", complexity.get("risk"))}, unavailable_data_notes=sorted(set((repo.get("unavailable_data_notes") or []) + (complexity.get("unavailable_data_notes") or []))))


def canonical_scoring_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    complexity = _complexity(context)
    scan = _scan(context)
    if not repo or scan.get("status") != "complete":
        return _result(context, "blocked", reason="complete_repository_and_scanner_evidence_required")
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    dependency = repo.get("dependency_evidence") if isinstance(repo.get("dependency_evidence"), dict) else {}
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), dict) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    signals = repo.get("code_signal_evidence") if isinstance(repo.get("code_signal_evidence"), dict) else {}
    counts = _counts(scan)
    unavailable_tools = list(scan.get("unavailable_tools") or [])
    failed_tools = list(scan.get("failed_tools") or [])
    timed_out_tools = list(scan.get("timed_out_tools") or [])
    code_hits = int(signals.get("risk_pattern_hits") or 0)
    code_findings = [f"{code_hits} sampled code-risk pattern hit(s) require review."] if code_hits else []
    dependency_findings: list[str] = []
    dependency_score = 94
    if not dependency.get("lockfile_paths"):
        dependency_findings.append("No lockfile evidence was found in the captured snapshot.")
        dependency_score -= 10
    if any(tool in unavailable_tools for tool in ("pip-audit", "npm-audit", "osv-scanner")):
        dependency_findings.append("One or more dependency analyzers were unavailable.")
        dependency_score -= 8
    scanner_findings: list[str] = []
    scanner_score = 96
    if counts["material"]:
        scanner_findings.append(f"{counts['material']} material scanner finding(s) require immediate human disposition.")
        scanner_score -= min(45, counts["material"] * 15)
    if counts["review"]:
        scanner_findings.append(f"{counts['review']} scanner candidate(s) require human triage.")
        scanner_score -= min(18, counts["review"])
    static_findings: list[str] = []
    static_score = 94
    if failed_tools:
        static_findings.append(f"Failed analyzers: {', '.join(failed_tools)}.")
        static_score -= min(24, len(failed_tools) * 8)
    if timed_out_tools:
        static_findings.append(f"Timed-out analyzers: {', '.join(timed_out_tools)}.")
        static_score -= min(20, len(timed_out_tools) * 7)
    successful = int(workflow.get("successful_runs") or 0)
    non_success = int(workflow.get("non_success_runs") or 0)
    ci_findings: list[str] = []
    ci_score = 92
    if non_success:
        ci_findings.append(f"Historical workflow evidence includes {non_success} non-success run(s).")
        ci_score -= min(18, non_success)
    if not workflow.get("explicit_permissions_present"):
        ci_findings.append("Workflow configuration did not prove explicit permissions blocks.")
        ci_score -= 7
    if successful == 0:
        ci_findings.append("No successful workflow run was available in the bounded history window.")
        ci_score -= 12
    measured_complexity = complexity.get("complexity_score")
    architecture_score = int(measured_complexity) if isinstance(measured_complexity, (int, float)) else 78
    architecture_findings: list[str] = []
    if str(complexity.get("risk_level") or complexity.get("risk") or "").lower() in {"high", "critical"}:
        architecture_findings.append("Complexity evidence reports concentrated high-risk hotspots.")
    commits = int(activity.get("commits_returned") or 0)
    pulls = int(activity.get("pull_requests_returned") or 0)
    velocity_score = 84 if commits and pulls else 65
    velocity_findings = [] if commits and pulls else ["Commit or pull-request history was incomplete for delivery-process analysis."]
    sections = [
        _section("code_audit", "Code Audit", 94 - min(18, code_hits * 2), "Exact-commit sampled code signals and repository structure were reviewed.", [f"Risk pattern hits: {code_hits}.", f"Test paths in tree: {int(architecture.get('test_path_count') or 0)}."], code_findings),
        _section("dependency_health", "Dependency / Library Ecosystem", dependency_score, "Manifest, lockfile, and scanner evidence were reconciled.", [f"Dependency entries: {int(dependency.get('dependency_entries') or 0)}.", f"Lockfiles: {', '.join(dependency.get('lockfile_paths') or []) or 'none'}."], dependency_findings),
        _section("secrets_review", "Secrets Exposure Review", scanner_score, "Secret-scanner candidates are separated from verified material findings.", [f"Raw scanner candidates: {counts['raw']}.", f"Material findings: {counts['material']}.", f"Review-required candidates: {counts['review']}."], scanner_findings),
        _section("static_analysis", "Static Analysis", static_score, "Static analyzers were executed against the immutable snapshot and reconciled by disposition.", [f"Tools run: {', '.join(scan.get('tools_run') or [])}.", f"Failed tools: {', '.join(failed_tools) or 'none'}.", f"Timed-out tools: {', '.join(timed_out_tools) or 'none'}."], static_findings, [f"Unavailable tools: {', '.join(unavailable_tools)}."] if unavailable_tools else []),
        _section("ci_cd", "CI/CD Analysis", ci_score, "Workflow configuration and bounded operational history were reviewed separately.", [f"Workflow files: {int(workflow.get('workflow_file_count') or 0)}.", f"Successful runs: {successful}.", f"Non-success runs: {non_success}."], ci_findings),
        _section("architecture_debt", "Architecture & Technical Debt", architecture_score, "Snapshot-bound source footprint and measured complexity evidence were evaluated.", [f"Source files: {int(architecture.get('source_file_count') or 0)}.", f"Files analyzed for complexity: {int(complexity.get('files_analyzed') or 0)}.", f"Complexity risk: {_text(complexity.get('risk_level') or complexity.get('risk') or 'unknown')}."], architecture_findings),
        _section("velocity_complexity", "Velocity / Complexity", velocity_score, "Commit, PR, workflow, source-footprint, and complexity evidence inform work-vs-expected review.", [f"Commits returned: {commits}.", f"Pull requests returned: {pulls}."], velocity_findings),
    ]
    scored = [int(item["presented_score"]) for item in sections if isinstance(item.get("presented_score"), int)]
    overall = round(sum(scored) / len(scored)) if scored else 0
    level = "Senior" if overall >= 82 else "Mid" if overall >= 58 else "Junior"
    unavailable_notes = sorted(set((repo.get("unavailable_data_notes") or []) + (scan.get("unavailable_data_notes") or [])))
    assessment = {"status": "complete", "service_id": "comprehensive", "repository": context["repository"], "commit_sha": context["commit_sha"], "run_id": context["run_id"], "executive_summary": f"Core technical evidence for {context['repository']} at {context['commit_sha']} produced an evidence-bound {level} maturity signal ({overall}/100). Comprehensive-only modules continue after this score and remain subject to human review.", "maturity_signal": {"level": level, "score": overall, "source_score": overall, "presented_score": overall, "evidence_readiness_score": max(0, 100 - min(50, len(unavailable_notes) * 5 + len(unavailable_tools) * 5))}, "evidence_coverage": {"calculated": True, "percent": max(0, 100 - min(60, len(unavailable_notes) * 5 + len(unavailable_tools) * 7)), "label": "Automated evidence coverage"}, "sections": sections, "unavailable_data_notes": unavailable_notes, "human_review_required": True, "client_ready": False, "client_delivery_allowed": False}
    return _result(context, summary="Canonical evidence-bound technical scoring completed without forced score inflation.", assessment=assessment, evidence={"maturity_level": level, "technical_score": overall, "scored_sections": len(scored), "unavailable_note_count": len(unavailable_notes)})


def _build_report(context: dict[str, Any], final: bool) -> dict[str, Any]:
    prior = context.get("prior_stage_results") if isinstance(context.get("prior_stage_results"), dict) else {}
    package = build_comprehensive_report_package(identity=_identity(context), stage_results=prior)
    if str(package.get("status") or "blocked") != "complete":
        report = package.get("report_package") if isinstance(package.get("report_package"), dict) else {}
        return _result(context, "blocked", reason=package.get("reason") or report.get("pdf_error") or "report_generation_failed", report_package=report)
    return _result(context, summary="The final native Comprehensive Markdown, HTML, JSON, and PDF draft package was generated." if final else "The core decision report was generated from reconciled technical evidence.", report_package=package["report_package"], assessment=package["assessment"], evidence={"report_id": package.get("report_id"), "pdf_page_count": package["report_package"].get("pdf_page_count"), "canonical_truth_sha256": package.get("canonical_truth_sha256"), "final_package": final})


def report_generation_provider(context: dict[str, Any]) -> dict[str, Any]: return _build_report(context, False)


def scanner_triage_provider(context: dict[str, Any]) -> dict[str, Any]:
    scan = _scan(context)
    if scan.get("status") != "complete":
        return _result(context, "blocked", reason="complete_scanner_evidence_required")
    counts = _counts(scan)
    return _result(context, summary="Scanner findings were separated into material, review-required, approved/nonblocking, and test-only dispositions.", scanner_triage={"finding_summary": scan.get("finding_summary") or {}, "tools_run": scan.get("tools_run") or [], "failed_tools": scan.get("failed_tools") or [], "timed_out_tools": scan.get("timed_out_tools") or [], "unavailable_tools": scan.get("unavailable_tools") or []}, evidence={**counts, "tools_run": scan.get("tools_run") or [], "full_history_verified_tools": scan.get("full_history_verified_tools") or []}, unavailable_data_notes=scan.get("unavailable_data_notes") or [])


def functional_qa_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    workflows = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    commands = list(workflows.get("commands_detected") or [])
    return _result(context, summary="Functional QA evidence was assessed from test footprint and CI command configuration; runtime acceptance remains human-supplied evidence.", evidence={"test_path_count": int(architecture.get("test_path_count") or 0), "test_commands_detected": [item for item in commands if "test" in str(item).lower()]}, unavailable_data_notes=["Runtime user-journey execution and stakeholder acceptance testing were not available from repository evidence alone."])


def platform_parity_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    files = repo.get("file_evidence") if isinstance(repo.get("file_evidence"), dict) else {}
    sampled = [str(item) for item in files.get("sampled_paths") or []]
    ios = [path for path in sampled if any(token in path.lower() for token in ("ios", ".swift", "xcode"))]
    android = [path for path in sampled if any(token in path.lower() for token in ("android", ".kt", ".gradle"))]
    unavailable = [] if ios or android else ["No native iOS or Android project evidence was observed in the bounded repository sample; cross-platform parity cannot be scored."]
    return _result(context, summary="Platform evidence was inventoried without claiming parity where runnable builds or native project evidence were unavailable.", evidence={"ios_paths": ios[:20], "android_paths": android[:20], "parity_directly_scored": bool(ios and android)}, unavailable_data_notes=unavailable)


def deployment_review_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    return _result(context, summary="Deployment manifests, workflow deployment evidence, and runtime configuration controls were reviewed.", evidence={"deployment_manifests": architecture.get("deployment_manifests") or [], "deployments_observed": workflow.get("deployments_observed", 0), "successful_deployments": workflow.get("successful_deployments", 0), "non_success_deployments": workflow.get("non_success_deployments", 0), "configuration_controls": workflow.get("configuration_controls") or {}})


def architecture_data_flow_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    complexity = _complexity(context)
    architecture = repo.get("architecture_evidence") if isinstance(repo.get("architecture_evidence"), dict) else {}
    return _result(context, summary="Architecture, top-level modules, deployment boundaries, source footprint, and measured complexity were synthesized into a data-flow review boundary.", evidence={"top_level_directories": architecture.get("top_level_directories") or [], "source_file_count": architecture.get("source_file_count", 0), "deployment_manifests": architecture.get("deployment_manifests") or [], "complexity_files_analyzed": complexity.get("files_analyzed", 0), "complexity_risk": complexity.get("risk_level", complexity.get("risk"))}, unavailable_data_notes=complexity.get("unavailable_data_notes") or [])


def delivery_process_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), dict) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    return _result(context, summary="Commit, pull-request, workflow, job, and deployment evidence were reviewed as bounded delivery-process history.", evidence={"commits_returned": activity.get("commits_returned", 0), "pull_requests_returned": activity.get("pull_requests_returned", 0), "merged_pull_requests": activity.get("merged_pull_requests", 0), "open_pull_requests": activity.get("open_pull_requests", 0), "jobs_observed": workflow.get("jobs_observed", 0), "job_success_rate": workflow.get("job_success_rate")})


def stakeholder_alignment_provider(context: dict[str, Any]) -> dict[str, Any]:
    return _result(context, summary="Stakeholder and business alignment remains an explicit human-context boundary; NICO did not infer unprovided objectives or approvals.", evidence={"repository_identity": context["repository"], "stakeholder_interviews_attached": False, "business_objectives_attached": False}, unavailable_data_notes=["Stakeholder interviews, business priorities, budget authority, and acceptance criteria were not supplied in the repository evidence package."])


def requirements_traceability_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    files = repo.get("file_evidence") if isinstance(repo.get("file_evidence"), dict) else {}
    sampled = [str(item) for item in files.get("sampled_paths") or []]
    candidates = [path for path in sampled if any(token in path.lower() for token in ("requirement", "spec", "roadmap", "issue", "adr"))]
    unavailable = [] if candidates else ["No authoritative requirements register or stakeholder-approved acceptance matrix was present in the bounded repository sample."]
    return _result(context, summary="Repository documentation was searched for requirements, specifications, ADRs, roadmaps, and acceptance evidence.", evidence={"candidate_traceability_paths": candidates[:30], "directly_verified_requirement_count": 0}, unavailable_data_notes=unavailable)


def historical_trends_provider(context: dict[str, Any]) -> dict[str, Any]:
    repo = _repo(context)
    activity = repo.get("activity_evidence") if isinstance(repo.get("activity_evidence"), dict) else {}
    workflow = repo.get("workflow_evidence") if isinstance(repo.get("workflow_evidence"), dict) else {}
    return _result(context, summary="Historical change and failure signals were calculated only from bounded GitHub operational evidence observed through capture time.", evidence={"captured_through": activity.get("captured_through"), "commits_returned": activity.get("commits_returned", 0), "pull_requests_returned": activity.get("pull_requests_returned", 0), "successful_runs": workflow.get("successful_runs", 0), "non_success_runs": workflow.get("non_success_runs", 0), "successful_deployments": workflow.get("successful_deployments", 0), "non_success_deployments": workflow.get("non_success_deployments", 0)}, unavailable_data_notes=["Change-failure rate and recovery time remain estimates unless incidents and production telemetry are supplied."])


def roadmap_provider(context: dict[str, Any]) -> dict[str, Any]:
    scoring = _prior(context, "evidence_reconciliation_and_scoring")
    assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), dict) else {}
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    ranked = sorted([item for item in sections if isinstance(item, dict) and isinstance(item.get("presented_score"), (int, float))], key=lambda item: int(item.get("presented_score") or 0))
    priorities = [_text(item.get("label") or item.get("id"), 120) for item in ranked[:5]]
    roadmap = [{"window": "0-30 days", "objective": "Stabilize material security, dependency, CI, and evidence-integrity findings.", "priority_controls": priorities[:3]}, {"window": "31-90 days", "objective": "Strengthen tests, architecture boundaries, deployment controls, and operational observability.", "priority_controls": priorities[2:5]}, {"window": "91-180 days", "objective": "Execute platform, stakeholder, requirements, and delivery-maturity improvements with measurable acceptance criteria.", "priority_controls": priorities}]
    return _result(context, summary="A six-month roadmap was sequenced from the lowest evidence-bound controls and explicit unavailable-evidence boundaries.", roadmap=roadmap, evidence={"priority_controls": priorities, "roadmap_window_count": len(roadmap)}, unavailable_data_notes=["Dates, owners, and budget require stakeholder approval before becoming commitments."])


def resourcing_provider(context: dict[str, Any]) -> dict[str, Any]:
    roadmap = _prior(context, "six_month_roadmap").get("roadmap") or []
    plan = [{"role": "Product Engineering Architect", "sequence": 1, "focus": "Architecture, scoring validation, risk disposition, and roadmap governance."}, {"role": "Senior Product Engineer", "sequence": 2, "focus": "Dependency, CI/CD, backend, frontend, and deployment remediation."}, {"role": "Product Quality Engineer", "sequence": 3, "focus": "Functional QA, platform parity, report truth, and release acceptance."}]
    return _result(context, summary="A role-based staffing and sequencing plan was generated without presenting unverified market rates as committed cost.", staffing_plan=plan, evidence={"roadmap_items_available": len(roadmap), "recommended_role_count": len(plan)}, unavailable_data_notes=["Labor rates, contract structure, geographic mix, and budget ceilings require client input before cost finalization."])


def executive_briefing_provider(context: dict[str, Any]) -> dict[str, Any]:
    scoring = _prior(context, "evidence_reconciliation_and_scoring")
    assessment = scoring.get("assessment") if isinstance(scoring.get("assessment"), dict) else {}
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    roadmap = _prior(context, "six_month_roadmap").get("roadmap") or []
    staffing = _prior(context, "staffing_sequencing_and_cost").get("staffing_plan") or []
    briefing = {"maturity_level": maturity.get("level") or "Pending", "technical_score": maturity.get("presented_score", maturity.get("score")), "roadmap_windows": len(roadmap), "recommended_roles": len(staffing), "decision": "Proceed to human review; do not authorize client delivery until evidence limitations and recommendations are approved."}
    return _result(context, summary="Technical score, evidence limitations, roadmap, staffing, and decision boundaries were condensed into an executive briefing.", executive_briefing=briefing, evidence=briefing)


def final_report_generation_provider(context: dict[str, Any]) -> dict[str, Any]: return _build_report(context, True)


def cross_format_verification_provider(context: dict[str, Any]) -> dict[str, Any]:
    final_stage = _prior(context, "final_comprehensive_report_generation")
    package = final_stage.get("report_package") if isinstance(final_stage.get("report_package"), dict) else {}
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    encoded_pdf = str(package.get("pdf_base64") or "")
    try:
        pdf = base64.b64decode(encoded_pdf, validate=True) if encoded_pdf else b""
    except Exception:
        pdf = b""
    identity = _identity(context)
    checks = {"markdown_available": bool(markdown), "html_available": bool(rendered_html), "pdf_available": pdf.startswith(b"%PDF"), "identity_present_in_markdown": all(value in markdown for value in (identity["run_id"], identity["repository"], identity["commit_sha"])), "delivery_blocked_in_markdown": "CLIENT DELIVERY NOT AUTHORIZED" in markdown, "service_id": package.get("service_id")}
    if not all(value is True for key, value in checks.items() if key != "service_id") or checks["service_id"] != "comprehensive":
        return _result(context, "blocked", reason="cross_format_truth_verification_failed", checks=checks)
    return _result(context, summary="Markdown, HTML, and PDF artifacts passed identity, validity, service-name, and delivery-boundary verification.", checks=checks, evidence={**checks, "pdf_sha256": hashlib.sha256(pdf).hexdigest(), "canonical_truth_sha256": package.get("canonical_truth_sha256")})


def human_review_provider(context: dict[str, Any]) -> dict[str, Any]:
    final_stage = _prior(context, "final_comprehensive_report_generation")
    package = final_stage.get("report_package") if isinstance(final_stage.get("report_package"), dict) else {}
    report_id = _text(package.get("report_id"), 180)
    if not report_id:
        return _result(context, "blocked", reason="final_report_package_required")
    approval_id = f"comprehensive_review_{hashlib.sha256((context['run_id'] + '|' + report_id).encode()).hexdigest()[:20]}"
    return _result(context, summary="A human-review request was created for the exact immutable Comprehensive report package.", approval_request={"approval_id": approval_id, "status": "pending_review", "report_id": report_id, "commit_sha": context["commit_sha"], "evidence_ledger_id": context["evidence_ledger_id"]}, evidence={"approval_id": approval_id, "report_id": report_id, "status": "pending_review"})


def acceptance_gate_provider(context: dict[str, Any]) -> dict[str, Any]:
    review = _prior(context, "human_review_request")
    request = review.get("approval_request") if isinstance(review.get("approval_request"), dict) else {}
    if not request.get("approval_id"):
        return _result(context, "blocked", reason="human_review_request_required")
    return _result(context, "review_required", summary="Automated Comprehensive work is complete. Client acceptance and delivery remain pending human approval.", acceptance={"status": "pending_human_review", "approval_id": request.get("approval_id"), "client_delivery_allowed": False}, evidence={"approval_id": request.get("approval_id"), "human_review_required": True, "client_delivery_allowed": False})


def native_comprehensive_providers() -> dict[str, Provider]:
    return {"snapshot": snapshot_provider, "repository_evidence": repository_evidence_provider, "scanner_suite": scanner_suite_provider, "technical_analysis": technical_analysis_provider, "canonical_scoring": canonical_scoring_provider, "report_generation": report_generation_provider, "scanner_triage": scanner_triage_provider, "functional_qa": functional_qa_provider, "platform_parity": platform_parity_provider, "deployment_review": deployment_review_provider, "architecture_data_flow": architecture_data_flow_provider, "delivery_process": delivery_process_provider, "stakeholder_alignment": stakeholder_alignment_provider, "requirements_traceability": requirements_traceability_provider, "historical_trends": historical_trends_provider, "roadmap": roadmap_provider, "resourcing": resourcing_provider, "executive_briefing": executive_briefing_provider, "final_report_generation": final_report_generation_provider, "cross_format_verification": cross_format_verification_provider, "human_review": human_review_provider, "acceptance_gate": acceptance_gate_provider}


def install_native_comprehensive_providers(app: FastAPI) -> dict[str, Provider]:
    existing = getattr(app.state, PROVIDER_STATE_KEY, None)
    providers = dict(existing) if isinstance(existing, dict) else {}
    providers.update(native_comprehensive_providers())
    setattr(app.state, PROVIDER_STATE_KEY, providers)
    app.state.nico_native_comprehensive_provider_status = {"artifact_schema": VERSION, "service_id": "comprehensive", "provider_count": len(providers), "providers": sorted(providers), "human_review_required": True, "client_delivery_allowed": False}
    return providers


__all__ = ["VERSION", "install_native_comprehensive_providers", "native_comprehensive_providers"]
