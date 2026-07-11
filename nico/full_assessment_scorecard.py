from __future__ import annotations

from typing import Any

TECHNICAL_SECTION_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _status(score: int | None) -> str:
    if score is None:
        return "gray"
    if score >= 80:
        return "green"
    if score >= 55:
        return "yellow"
    return "red"


def _section(
    section_id: str,
    label: str,
    score: int | None,
    summary: str,
    evidence: list[str],
    *,
    findings: list[str] | None = None,
    unavailable: list[str] | None = None,
    confidence: str = "standard",
) -> dict[str, Any]:
    return {
        "id": section_id,
        "label": label,
        "score": 0 if score is None else max(0, min(100, int(score))),
        "status": _status(score),
        "summary": summary,
        "evidence": evidence,
        "verified_claims": evidence,
        "findings": findings or [],
        "unavailable": unavailable or [],
        "unverified_claims": unavailable or [],
        "confidence": "unavailable" if score is None else confidence,
    }


def _tool_names(scanner: dict[str, Any], key: str) -> set[str]:
    return {str(item).strip().lower() for item in _list(scanner.get(key)) if str(item).strip()}


def _tool_group(scanner: dict[str, Any], names: set[str]) -> dict[str, set[str]]:
    return {
        "run": _tool_names(scanner, "tools_run") & names,
        "requested": _tool_names(scanner, "tools_requested") & names,
        "unavailable": _tool_names(scanner, "unavailable_tools") & names,
        "failed": _tool_names(scanner, "failed_tools") & names,
        "timed_out": _tool_names(scanner, "timed_out_tools") & names,
    }


def _code_section(repo: dict[str, Any]) -> dict[str, Any]:
    files = _dict(repo.get("file_evidence"))
    architecture = _dict(repo.get("architecture_evidence"))
    activity = _dict(repo.get("activity_evidence"))
    signals = _dict(repo.get("code_signal_evidence"))
    files_profiled = _count(files.get("files_profiled"))
    source_count = _count(architecture.get("source_file_count"))
    test_count = _count(architecture.get("test_path_count"))
    docs = _count(architecture.get("documentation_path_count"))
    commits = _count(activity.get("commits_returned"))
    pulls = _count(activity.get("pull_requests_returned"))
    risks = _count(signals.get("risk_pattern_hits"))
    todos = _count(signals.get("todo_fixme_security_notes"))

    score = 45
    score += 10 if files_profiled >= 10 else 5 if files_profiled else 0
    score += 10 if source_count >= 5 else 5 if source_count else 0
    score += 10 if test_count >= 3 else 5 if test_count else 0
    score += 5 if docs else 0
    score += 5 if commits else 0
    score += 5 if pulls else 0
    score -= min(20, risks * 5)
    score -= min(10, todos)
    score = min(score, 88)

    evidence = [
        f"GitHub file profile inspected {files_profiled} sampled text files across {source_count} source-file paths.",
        f"Repository tree signals include {test_count} test paths and {docs} documentation paths.",
        f"Assessment-window activity returned {commits} commits and {pulls} pull requests.",
        f"Sampled-file pattern review returned {risks} code-risk hits and {todos} TODO/FIXME/security-note signals.",
    ]
    findings: list[str] = []
    if risks:
        findings.append(f"Review {risks} sampled-file code-risk pattern hit(s) before client delivery.")
    if not test_count:
        findings.append("No test-path signal was returned from the repository tree.")
    unavailable = ["This score does not replace line-by-line semantic code review, runtime testing, or complete coverage measurement."]
    return _section("code_audit", "Code Audit", score, "Code maturity is estimated from the attached repository profile, test/documentation structure, activity, and bounded risk-pattern signals.", evidence, findings=findings, unavailable=unavailable)


def _dependency_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    deps = _dict(repo.get("dependency_evidence"))
    manifests = [str(item) for item in _list(deps.get("manifest_paths"))]
    lockfiles = [str(item) for item in _list(deps.get("lockfile_paths"))]
    entries = _count(deps.get("dependency_entries"))
    tools = _tool_group(scanner, {"pip-audit", "npm-audit", "osv-scanner"})

    score = 35
    score += 15 if manifests else 0
    score += 15 if lockfiles else 0
    score += 10 if entries else 0
    score += min(20, len(tools["run"]) * 8)
    score -= len(tools["failed"]) * 12
    score -= len(tools["timed_out"]) * 8
    score -= len(tools["unavailable"]) * 5
    if not tools["run"]:
        score = min(score, 68)
    score = min(score, 88)

    evidence = [
        f"Dependency evidence includes {len(manifests)} manifest path(s), {len(lockfiles)} lockfile path(s), and {entries} parsed dependency entries.",
        f"Dependency scanners run: {', '.join(sorted(tools['run'])) or 'none'}.",
        f"Dependency scanners unavailable/failed/timed out: {len(tools['unavailable'])}/{len(tools['failed'])}/{len(tools['timed_out'])}.",
    ]
    findings: list[str] = []
    if manifests and not lockfiles:
        findings.append("Dependency manifests were found without a sampled lockfile signal.")
    if tools["failed"] or tools["timed_out"]:
        findings.append("One or more dependency scanners failed or timed out; vulnerability conclusions remain incomplete.")
    unavailable = ["Scanner execution coverage does not by itself prove that dependencies are vulnerability-free; parsed findings still require review."]
    return _section("dependency_health", "Dependency / Library Ecosystem", score, "Dependency health reflects manifest/lockfile controls and completed scanner coverage, not an unsupported clean-vulnerability claim.", evidence, findings=findings, unavailable=unavailable, confidence="scanner-and-repository-bound")


def _secrets_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = _dict(repo.get("code_signal_evidence"))
    hits = _count(signals.get("potential_secret_pattern_hits"))
    tools = _tool_group(scanner, {"gitleaks", "trufflehog", "detect-secrets"})

    score = 60 if hits == 0 else max(25, 55 - hits * 8)
    score += min(22, len(tools["run"]) * 12)
    score -= len(tools["failed"]) * 15
    score -= len(tools["timed_out"]) * 10
    score -= len(tools["unavailable"]) * 6
    if not tools["run"]:
        score = min(score, 68)
    score = min(score, 88)

    evidence = [
        f"Sampled repository text returned {hits} potential secret-pattern hit(s).",
        f"Dedicated secret scanners run: {', '.join(sorted(tools['run'])) or 'none'}.",
    ]
    findings = [f"Triage {hits} potential secret-pattern hit(s) and rotate any confirmed credential outside NICO."] if hits else []
    unavailable = ["A zero sampled-pattern count is not proof of no secrets; full-history and dedicated credential-scan evidence is required for a high-confidence clean claim."]
    return _section("secrets_review", "Secrets Exposure Review", score, "Secrets review combines bounded sampled-file pattern signals with any completed dedicated credential scanners.", evidence, findings=findings, unavailable=unavailable, confidence="limited" if not tools["run"] else "scanner-and-repository-bound")


def _static_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = _dict(repo.get("code_signal_evidence"))
    risks = _count(signals.get("risk_pattern_hits"))
    tools = _tool_group(scanner, {"bandit", "semgrep", "eslint"})

    score = 48
    score += 10 if risks == 0 else max(-15, 5 - risks * 5)
    score += min(28, len(tools["run"]) * 10)
    score -= len(tools["failed"]) * 12
    score -= len(tools["timed_out"]) * 8
    score -= len(tools["unavailable"]) * 5
    if not tools["run"]:
        score = min(score, 60)
    score = min(score, 88)

    evidence = [
        f"Sampled-file static risk-pattern hits: {risks}.",
        f"Static-analysis tools run: {', '.join(sorted(tools['run'])) or 'none'}.",
        f"Static tools unavailable/failed/timed out: {len(tools['unavailable'])}/{len(tools['failed'])}/{len(tools['timed_out'])}.",
    ]
    findings: list[str] = []
    if risks:
        findings.append(f"Review {risks} sampled static risk-pattern hit(s).")
    if tools["failed"] or tools["timed_out"]:
        findings.append("Static-analysis execution was incomplete because one or more tools failed or timed out.")
    unavailable = ["Tool execution coverage is scored separately from finding severity; human triage of parsed results remains required."]
    return _section("static_analysis", "Static Analysis", score, "Static-analysis maturity reflects sampled risk signals plus completed Bandit, Semgrep, and ESLint coverage where available.", evidence, findings=findings, unavailable=unavailable, confidence="scanner-and-repository-bound" if tools["run"] else "limited")


def _ci_section(repo: dict[str, Any]) -> dict[str, Any]:
    workflows = _dict(repo.get("workflow_evidence"))
    files = _count(workflows.get("workflow_file_count"))
    runs = _count(workflows.get("workflow_run_count"))
    success = _count(workflows.get("successful_runs"))
    non_success = _count(workflows.get("non_success_runs"))
    commands = [str(item) for item in _list(workflows.get("commands_detected"))]
    permissions = bool(workflows.get("explicit_permissions_present"))

    score = 35
    score += 12 if files else 0
    score += min(18, len(commands) * 4)
    score += 8 if permissions else 0
    if runs:
        rate = success / max(1, success + non_success)
        score += 17 if rate >= 0.8 else 10 if rate >= 0.6 else 0
        if non_success > success:
            score -= 10
    else:
        score = min(score, 72)
    score = min(score, 94)

    evidence = [
        f"GitHub workflow evidence includes {files} workflow file(s) and {runs} recent run(s).",
        f"Workflow history returned success={success} and non-success={non_success}.",
        f"Detected CI commands: {', '.join(commands) or 'none'}; explicit permissions block present={permissions}.",
    ]
    findings: list[str] = []
    if not files:
        findings.append("No readable GitHub Actions workflow file was attached.")
    if runs and non_success:
        findings.append(f"Review {non_success} non-success workflow run(s) in the assessment window.")
    unavailable = ["Workflow configuration and run conclusions do not replace inspection of failing job logs or deployment-provider evidence."]
    return _section("ci_cd", "CI/CD Analysis", score, "CI/CD maturity is based on attached workflow configuration, automation commands, permissions, and recent run conclusions.", evidence, findings=findings, unavailable=unavailable)


def _architecture_section(repo: dict[str, Any]) -> dict[str, Any]:
    architecture = _dict(repo.get("architecture_evidence"))
    source = _count(architecture.get("source_file_count"))
    tests = _count(architecture.get("test_path_count"))
    docs = _count(architecture.get("documentation_path_count"))
    deployment = [str(item) for item in _list(architecture.get("deployment_manifests"))]
    directories = [str(item) for item in _list(architecture.get("top_level_directories"))]

    score = 40
    score += 10 if source else 0
    score += 12 if tests >= 3 else 5 if tests else 0
    score += 8 if docs else 0
    score += 8 if deployment else 0
    score += 7 if len(directories) >= 3 else 3 if directories else 0
    score = min(score, 90)

    evidence = [
        f"Repository tree includes {source} source paths, {tests} test paths, and {docs} documentation paths.",
        f"Deployment manifest signals: {', '.join(deployment) or 'none'}.",
        f"Top-level directory signals: {', '.join(directories[:12]) or 'none'}.",
    ]
    findings: list[str] = []
    if not tests:
        findings.append("No test-path signal was attached for architecture readiness.")
    if not docs:
        findings.append("No documentation-path signal was attached for onboarding and maintenance review.")
    unavailable = ["Call-graph, coupling, duplication, and cyclomatic-complexity conclusions require language-specific analyzer output."]
    return _section("architecture_debt", "Architecture & Technical Debt", score, "Architecture maturity uses repository layout, source/test/documentation structure, and deployment-manifest evidence.", evidence, findings=findings, unavailable=unavailable)


def _velocity_section(repo: dict[str, Any]) -> dict[str, Any]:
    activity = _dict(repo.get("activity_evidence"))
    architecture = _dict(repo.get("architecture_evidence"))
    commits = _count(activity.get("commits_returned"))
    pulls = _count(activity.get("pull_requests_returned"))
    merged = _count(activity.get("merged_pull_requests"))
    open_count = _count(activity.get("open_pull_requests"))
    source = _count(architecture.get("source_file_count"))

    score = 35
    score += 10 if commits else 0
    score += 10 if commits >= 10 else 0
    score += 10 if pulls else 0
    score += 10 if merged else 0
    score += 5 if open_count else 0
    score += 5 if source else 0
    score = min(score, 88)

    evidence = [
        f"Assessment-window activity returned {commits} commits and {pulls} pull requests.",
        f"Pull-request traceability returned merged={merged} and open={open_count}.",
        f"Velocity context includes a source footprint of {source} source-file paths.",
    ]
    findings = ["Commit activity exists without pull-request traceability in the assessment window."] if commits and not pulls else []
    unavailable = ["Story-point expectations, developer seniority, review quality, and business-value delivery require stakeholder context and human review."]
    return _section("velocity_complexity", "Velocity / Complexity", score, "Velocity maturity is estimated from bounded commit/PR activity and source-footprint traceability, not individual performance attribution.", evidence, findings=findings, unavailable=unavailable)


def _evidence_integrity_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    requested = _tool_names(scanner, "tools_requested")
    run = _tool_names(scanner, "tools_run")
    unavailable_tools = _tool_names(scanner, "unavailable_tools")
    failed = _tool_names(scanner, "failed_tools")
    timed_out = _tool_names(scanner, "timed_out_tools")

    score = 30
    score += 25 if repo.get("status") == "attached" else 0
    score += 25 if scanner.get("status") == "attached" else 0
    if requested:
        coverage = len(run) / max(1, len(requested))
        score += round(15 * min(1.0, coverage))
    score += 5 if not unavailable_tools and not failed and not timed_out else 0
    score -= len(failed) * 8
    score -= len(timed_out) * 5
    score = min(score, 95)

    evidence = [
        f"Repository evidence id={repo.get('evidence_id') or 'unavailable'} is bound to run_id={repo.get('run_id') or 'unavailable'}.",
        f"Scanner evidence id={scanner.get('scan_id') or 'unavailable'} is bound to run_id={scanner.get('run_id') or 'unavailable'}.",
        f"Scanner coverage completed {len(run)} of {len(requested)} requested tool(s).",
    ]
    findings: list[str] = []
    if unavailable_tools or failed or timed_out:
        findings.append("Evidence coverage is degraded by unavailable, failed, or timed-out scanner tools.")
    unavailable = list(repo.get("unavailable_data_notes") or []) + list(scanner.get("unavailable_data_notes") or [])
    return _section("evidence_integrity", "Evidence Integrity & Scanner Coverage", score, "Evidence integrity measures same-run binding, repository attachment, scanner attachment, and requested-tool execution coverage.", evidence, findings=findings, unavailable=unavailable, confidence="run-bound")


def _technical_score(sections: list[dict[str, Any]]) -> int:
    by_id = {str(item.get("id") or ""): item for item in sections}
    weighted = 0
    weight_total = 0
    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        item = by_id.get(section_id)
        if not item or item.get("status") == "gray":
            continue
        weighted += _count(item.get("score")) * weight
        weight_total += weight
    return round(weighted / weight_total) if weight_total else 0


def _maturity_level(score: int) -> str:
    if score >= 82:
        return "Senior"
    if score >= 58:
        return "Mid"
    return "Junior"


def build_full_assessment_scorecard(
    context: dict[str, Any],
    repository_evidence: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Build a multi-section draft scorecard from completed same-run evidence."""

    sections = [
        _code_section(repository_evidence),
        _dependency_section(repository_evidence, scanner_evidence),
        _secrets_section(repository_evidence, scanner_evidence),
        _static_section(repository_evidence, scanner_evidence),
        _ci_section(repository_evidence),
        _architecture_section(repository_evidence),
        _velocity_section(repository_evidence),
        _evidence_integrity_section(repository_evidence, scanner_evidence),
    ]
    score = _technical_score(sections)
    evidence_score = next((int(item["score"]) for item in sections if item.get("id") == "evidence_integrity"), 0)
    available = sum(1 for item in sections if item.get("status") != "gray")
    gray = len(sections) - available
    findings = [str(finding) for item in sections for finding in _list(item.get("findings"))]
    unavailable = sorted({str(note) for item in sections for note in _list(item.get("unavailable")) if str(note).strip()})
    level = _maturity_level(score)
    confidence = "standard" if evidence_score >= 80 and gray == 0 else "limited"

    assessment = {
        "status": "draft",
        "run_id": context.get("run_id") or "",
        "repository": context.get("repository") or "",
        "customer_id": context.get("customer_id") or "default_customer",
        "project_id": context.get("project_id") or "default_project",
        "client_name": context.get("client_name") or "",
        "project_name": context.get("project_name") or "",
        "source_scope": context.get("repository") or "",
        "authorization_statement": "Full-run assessment output is valid only for the explicitly authorized repository, customer, project, run_id, and evidence scope.",
        "executive_summary": (
            f"NICO generated an evidence-bound Full Assessment draft for {context.get('repository') or 'the authorized repository'}. "
            f"The technical maturity signal is {level} ({score}/100) across seven weighted technical sections, with evidence readiness {evidence_score}/100. "
            "Repository and scanner records are bound to the same run. Scores describe the attached evidence and do not replace human validation of findings or client context."
        ),
        "maturity_signal": {
            "level": level,
            "score": score,
            "summary": "Weighted technical score derived from attached repository and completed same-run scanner evidence.",
            "evidence_readiness_score": evidence_score,
            "available_sections": available,
            "total_sections": len(sections),
        },
        "scorecard": {
            "technical_score": score,
            "evidence_readiness_score": evidence_score,
            "weights": TECHNICAL_SECTION_WEIGHTS,
            "available_sections": available,
            "unavailable_sections": gray,
            "scoring_basis": "Completed same-run GitHub repository evidence plus completed same-run scanner evidence.",
        },
        "client_delivery_verdict": {
            "status": "human_review_required",
            "confidence": confidence,
            "blockers": [
                "Final client delivery requires human review and approval.",
                "Scanner coverage and sampled repository evidence do not establish exhaustive absence of defects, vulnerabilities, or secrets.",
            ],
            "unavailable_items": len(unavailable),
        },
        "sections": sections,
        "findings": findings or ["No scored section returned a specific repair finding; human review of attached evidence remains required."],
        "unavailable_data_notes": unavailable,
        "next_steps": [
            "Review red and yellow sections with the attached evidence before making client-facing claims.",
            "Triage any scanner failures, timeouts, unavailable tools, risk-pattern hits, and CI non-success runs.",
            "Validate architecture, dependency, secrets, and static-analysis conclusions with human review.",
            "Approve or reject the final report through the same-run review workflow before client delivery.",
        ],
        "truthfulness_rules": [
            "Only completed same-run evidence can affect the scorecard.",
            "Missing evidence is disclosed and does not count as passing evidence.",
            "Scanner execution coverage is not the same as a clean finding result.",
            "Client delivery requires human approval.",
        ],
        "repository_evidence_id": repository_evidence.get("evidence_id") or "",
        "scanner_evidence_id": scanner_evidence.get("scan_id") or "",
        "human_review_required": True,
        "client_ready": False,
    }
    return assessment


def full_assessment_scoring_handler(context: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    repo_output = _dict(outputs.get("repo_evidence"))
    repository_evidence = _dict(repo_output.get("repository_evidence"))
    attachment = _dict(outputs.get("evidence_attachment"))
    scanner_evidence = _dict(attachment.get("scanner_evidence"))

    repo_status = repository_evidence.get("status") or "not_attached"
    scanner_status = scanner_evidence.get("status") or "not_attached"
    if repo_status != "attached" or scanner_status != "attached":
        return {
            "status": "planned",
            "message": "Full Assessment scorecard waits for attached GitHub repository evidence and completed same-run scanner evidence.",
            "evidence": {
                "run_id": context.get("run_id") or "",
                "repository_evidence_status": repo_status,
                "scanner_evidence_status": scanner_status,
            },
        }

    if str(repository_evidence.get("run_id") or "") != str(context.get("run_id") or ""):
        return {
            "status": "blocked",
            "message": "Repository evidence run_id does not match this full-run; scoring is blocked.",
            "evidence": {
                "run_id": context.get("run_id") or "",
                "repository_evidence_run_id": repository_evidence.get("run_id") or "",
            },
        }
    if str(scanner_evidence.get("run_id") or "") != str(context.get("run_id") or ""):
        return {
            "status": "blocked",
            "message": "Scanner evidence run_id does not match this full-run; scoring is blocked.",
            "evidence": {
                "run_id": context.get("run_id") or "",
                "scanner_evidence_run_id": scanner_evidence.get("run_id") or "",
            },
        }

    assessment = build_full_assessment_scorecard(context, repository_evidence, scanner_evidence)
    scorecard = _dict(assessment.get("scorecard"))
    return {
        "status": "complete",
        "message": "Full Assessment multi-section scorecard was generated from attached same-run repository and scanner evidence.",
        "assessment": assessment,
        "evidence": {
            "run_id": context.get("run_id") or "",
            "repository_evidence_id": repository_evidence.get("evidence_id") or "",
            "scanner_evidence_id": scanner_evidence.get("scan_id") or "",
            "technical_score": scorecard.get("technical_score", 0),
            "evidence_readiness_score": scorecard.get("evidence_readiness_score", 0),
            "sections": len(assessment.get("sections") or []),
        },
    }
