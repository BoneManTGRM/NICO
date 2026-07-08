from __future__ import annotations

import importlib.util
import re
from typing import Any

VALID_STATUSES = {
    "not_built",
    "built_but_not_wired",
    "built_but_runtime_artifact_missing",
    "unavailable_in_this_run",
    "completed_clean",
    "completed_with_findings",
    "failed_or_blocked",
    "needs_human_review",
}


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return str(value or "")


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in result.get("sections", []) or []
            if isinstance(item, dict) and item.get("id") == section_id
        ),
        None,
    )


def _section_text(item: dict[str, Any] | None) -> str:
    if not item:
        return ""
    return "\n".join(_text(item.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _replace_unavailable(section: dict[str, Any], old_fragments: tuple[str, ...], replacement: str) -> None:
    unavailable = [str(item) for item in section.get("unavailable", []) or []]
    kept = [
        item
        for item in unavailable
        if not any(fragment.lower() in item.lower() for fragment in old_fragments)
    ]
    if len(kept) != len(unavailable):
        _append_unique(kept, replacement)
    section["unavailable"] = kept


def _tool_completed_marker(text: str, tool: str) -> bool:
    lower = text.lower()
    tool_lower = tool.lower()
    return (
        f"{tool_lower} artifact" in lower
        or f"{tool_lower} artifacts" in lower
        or f"{tool_lower} completed" in lower
        or f"{tool_lower} status=passed" in lower
        or f"{tool_lower} status=completed" in lower
        or f"{tool_lower} status=ok" in lower
        or (f"scanner-worker {tool_lower}" in lower and "completed" in lower)
    )


def _tool_unavailable_marker(text: str, tool: str) -> bool:
    lower = text.lower()
    return tool.lower() in lower and any(
        marker in lower for marker in ("unavailable", "not attached", "not verified", "not executed", "not yet run")
    )


def _tool_findings_marker(text: str, tool: str) -> bool:
    lower = text.lower()
    return tool.lower() in lower and (
        "finding(s)" in lower
        or "vulnerability record(s)" in lower
        or "with findings" in lower
        or ("reported" in lower and "finding" in lower)
    )


def _classify_tool(
    *,
    built: bool,
    wired: bool = True,
    text: str = "",
    tool: str,
    complete_without_findings: bool = False,
) -> dict[str, Any]:
    if not built:
        status = "not_built"
    elif not wired:
        status = "built_but_not_wired"
    else:
        completed = complete_without_findings or _tool_completed_marker(text, tool)
        unavailable = _tool_unavailable_marker(text, tool)
        findings = _tool_findings_marker(text, tool)
        if completed and findings:
            status = "completed_with_findings"
        elif completed and unavailable:
            status = "needs_human_review"
        elif completed:
            status = "completed_clean"
        elif unavailable:
            status = "built_but_runtime_artifact_missing"
        else:
            status = "unavailable_in_this_run"
    return {
        "tool": tool,
        "status": status,
        "built": built,
        "wired": wired,
        "human_review_required": status in {"needs_human_review", "completed_with_findings", "failed_or_blocked"},
    }


def _has_osv_vulnerability(text: str) -> bool:
    lower = text.lower()
    return "osv returned" in lower and "vulnerability record" in lower and "no vulnerability records" not in lower


def _has_exact_pinned_osv_vulnerability(text: str) -> bool:
    return bool(
        re.search(
            r"osv returned\s+[0-9]+\s+vulnerability record\(s\)\s+for\s+[^:\n]+:[^\n]+==[^\s:]+",
            text,
            re.IGNORECASE,
        )
    )


def _bandit_count(text: str) -> int | None:
    for pattern in (
        r"Parsed Bandit artifact reported\s+([0-9]+)\s+finding",
        r"Bandit triage classified\s+([0-9]+)\s+finding",
        r"bandit.*?([0-9]+)\s+finding",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def build_report_evidence_status(result: dict[str, Any]) -> dict[str, Any]:
    dependency = _section_text(_section(result, "dependency_health"))
    secrets = _section_text(_section(result, "secrets_review"))
    static = _section_text(_section(result, "static_analysis"))
    architecture = _section_text(_section(result, "architecture_debt"))
    velocity = _section_text(_section(result, "velocity_complexity"))

    scanner_worker_built = _module_exists("nico.hosted_scanner_worker")
    github_app_built = _module_exists("nico.github_app_auth") or _module_exists("nico.github_app")
    mid_built = _module_exists("nico.qa_parity_intake") or _module_exists("nico.roadmap_generator")
    retainer_built = _module_exists("nico.retainer_modules")
    readiness_built = _module_exists("nico.report_readiness_gate")
    readiness_attach_built = _module_exists("nico.report_readiness_attachment")
    clean_secret_artifacts = "credential-scan" in secrets.lower() and (
        "zero high-confidence" in secrets.lower() or "clean credential-scan" in secrets.lower()
    )
    full_history_missing = "full git-history" in secrets.lower() and any(
        marker in secrets.lower() for marker in ("not verified", "requires", "unavailable", "missing")
    )

    return {
        "artifact_schema": "nico.report_evidence_status.v1",
        "status_vocabulary": sorted(VALID_STATUSES),
        "capabilities": {
            "scanner_worker": {"status": "built_but_runtime_artifact_missing" if scanner_worker_built else "not_built", "built": scanner_worker_built},
            "github_app_private_repo_flow": {"status": "built_but_runtime_artifact_missing" if github_app_built else "not_built", "built": github_app_built},
            "mid_modules": {"status": "built_but_runtime_artifact_missing" if mid_built else "not_built", "built": mid_built},
            "retainer_modules": {"status": "built_but_runtime_artifact_missing" if retainer_built else "not_built", "built": retainer_built},
            "report_readiness_gate": {"status": "built_but_runtime_artifact_missing" if readiness_built else "not_built", "built": readiness_built},
            "report_readiness_attachment": {"status": "built_but_runtime_artifact_missing" if readiness_attach_built else "not_built", "built": readiness_attach_built},
        },
        "dependency_tools": {
            "pip-audit": _classify_tool(built=scanner_worker_built, text=dependency, tool="pip-audit"),
            "npm audit": _classify_tool(built=scanner_worker_built, text=dependency, tool="npm-audit"),
            "OSV Scanner": _classify_tool(built=scanner_worker_built, text=dependency, tool="osv-scanner"),
            "OSV API": {
                "tool": "OSV API",
                "status": "completed_with_findings" if _has_osv_vulnerability(dependency) else ("completed_clean" if "osv returned no vulnerability records" in dependency.lower() else "unavailable_in_this_run"),
                "built": True,
                "wired": True,
                "human_review_required": _has_osv_vulnerability(dependency),
            },
        },
        "secret_tools": {
            "credential-scan": {"tool": "credential-scan", "status": "completed_clean" if clean_secret_artifacts else "unavailable_in_this_run", "built": True, "wired": True, "human_review_required": False},
            "gitleaks": _classify_tool(built=scanner_worker_built, text=secrets, tool="gitleaks", complete_without_findings="gitleaks" in secrets.lower() and clean_secret_artifacts),
            "trufflehog": _classify_tool(built=scanner_worker_built, text=secrets, tool="trufflehog"),
            "full_git_history_coverage": {"tool": "full_git_history_coverage", "status": "built_but_runtime_artifact_missing" if full_history_missing else "completed_clean", "built": scanner_worker_built, "wired": True, "human_review_required": full_history_missing},
        },
        "static_tools": {
            "Bandit": _classify_tool(built=scanner_worker_built, text=static, tool="bandit"),
            "Semgrep": _classify_tool(built=scanner_worker_built, text=static, tool="semgrep"),
            "ESLint": _classify_tool(built=scanner_worker_built, text=static, tool="eslint"),
            "TypeScript": _classify_tool(built=scanner_worker_built, text=static, tool="typescript"),
        },
        "complexity_tools": {
            "call_graph": _classify_tool(built=scanner_worker_built, text=architecture + "\n" + velocity, tool="call-graph"),
            "cyclomatic_complexity": _classify_tool(built=scanner_worker_built, text=architecture + "\n" + velocity, tool="cyclomatic"),
            "hotspot_churn": _classify_tool(built=scanner_worker_built, text=architecture + "\n" + velocity, tool="hotspot"),
        },
        "readiness_gates": {
            "deployment_verification": {"status": "completed_clean" if result.get("deployment_verification") else "built_but_runtime_artifact_missing", "built": _module_exists("nico.deployment_verification")},
            "hosted_smoke_test": {"status": "completed_clean" if result.get("hosted_smoke_test") else "built_but_runtime_artifact_missing", "built": _module_exists("nico.hosted_smoke_test")},
            "report_readiness_gate": {"status": "completed_clean" if result.get("report_readiness_gate") else "built_but_runtime_artifact_missing", "built": readiness_built},
            "client_human_acceptance": {"status": "completed_clean" if result.get("client_acceptance", {}).get("status") in {"accepted", "approved"} else "needs_human_review", "built": _module_exists("nico.client_acceptance")},
        },
    }


def _apply_dependency_language(result: dict[str, Any]) -> None:
    section = _section(result, "dependency_health")
    if not section:
        return
    raw_text = _section_text(section)
    text = raw_text.lower()
    section.setdefault("evidence", [])
    section.setdefault("findings", [])
    section.setdefault("unavailable", [])
    _replace_unavailable(
        section,
        ("not yet run inside a sandboxed worker", "hosted review uses manifest parsing plus osv api"),
        "Dependency scanner artifacts were not attached or verified for this report run; manifest, lockfile, and OSV API evidence remain separate from final scanner-clean proof.",
    )
    if _has_osv_vulnerability(text):
        section["summary"] = (
            "Dependency review is green from available manifest, lockfile, and OSV API evidence, "
            "but OSV returned vulnerability records and final scanner-clean dependency status is not claimed "
            "until pip-audit, npm audit, and OSV Scanner artifacts are attached for this run."
        )
        status_line = (
            "Dependency evidence status: OSV API completed_with_findings; final scanner-clean status is not claimed "
            "without pip-audit/npm audit/OSV Scanner artifacts for this run."
        )
        if _has_exact_pinned_osv_vulnerability(raw_text):
            _append_unique(section["findings"], status_line)
        else:
            _append_unique(section["evidence"], status_line)
    elif "zero dependency vulnerabilities" in text:
        section["summary"] = "Dependency review uses attached audit artifacts and available manifest evidence; missing tools remain disclosed separately."


def _apply_secret_language(result: dict[str, Any]) -> None:
    section = _section(result, "secrets_review")
    if not section:
        return
    text = _section_text(section).lower()
    section.setdefault("evidence", [])
    section.setdefault("unavailable", [])
    _replace_unavailable(
        section,
        ("full git-history secret scanning requires a sandboxed worker", "hosted mode currently scans fetched file contents only"),
        "Full git-history secret coverage was not verified for this report run; attached credential artifacts and live full-history scanner proof are separate evidence sources.",
    )
    clean_artifacts = "credential-scan" in text and ("zero high-confidence" in text or "clean credential-scan" in text)
    history_gap = "full git-history" in text and any(marker in text for marker in ("not verified", "requires", "unavailable"))
    if clean_artifacts and history_gap:
        section["summary"] = (
            "Secrets review found no high-confidence credential findings in attached credential-scan/gitleaks artifacts, "
            "but full git-history secret coverage is not verified for this report run."
        )
        _append_unique(section["evidence"], "Secrets evidence status: no high-confidence credential findings in attached artifacts, but full git-history secret coverage is not verified for this run.")
        if "scanner-worker secret tools unavailable" in text and "gitleaks" in text:
            _append_unique(section["unavailable"], "Secret scanner source distinction: attached clean credential/gitleaks artifact evidence is separate from live scanner-worker gitleaks/trufflehog execution and full-history coverage for this run.")


def _apply_static_language(result: dict[str, Any]) -> None:
    section = _section(result, "static_analysis")
    if not section:
        return
    raw_text = _section_text(section)
    lower = raw_text.lower()
    section.setdefault("evidence", [])
    section.setdefault("findings", [])
    section.setdefault("unavailable", [])
    _replace_unavailable(
        section,
        ("not yet executed by a sandboxed worker", "this section uses built-in pattern checks only"),
        "Live scanner-worker artifacts for Semgrep, Bandit, ESLint, and TypeScript were not attached or verified for this report run; built-in pattern checks and CI-backed evidence remain separate from full scanner-worker proof.",
    )
    _replace_unavailable(
        section,
        ("external semgrep/bandit scanner-worker execution remains unavailable",),
        "External Semgrep/Bandit scanner-worker execution was not verified for this report run; CI-backed evidence is counted separately from full scanner-worker proof.",
    )
    bandit_total = _bandit_count(raw_text)
    if bandit_total:
        triage = result.get("bandit_triage") if isinstance(result.get("bandit_triage"), dict) else {}
        blocker_count = int(triage.get("blocking_count") or 0)
        review_count = int(triage.get("review_required_count") or 0) or bandit_total
        false_positive_count = int(triage.get("candidate_false_positive_count") or 0)
        section["summary"] = (
            "Static analysis uses clean built-in pattern checks plus CI-backed evidence, but Bandit artifact findings require explicit triage; "
            "the green score is not a final scanner-clean claim."
        )
        _append_unique(section["evidence"], "Bandit evidence source distinction: parsed prior/sample or attached artifact findings are separate from live scanner-worker Bandit execution for this report run.")
        _append_unique(section["findings"], f"Bandit triage summary: total={bandit_total}, blocker_count={blocker_count}, review_required_count={review_count}, candidate_false_positive_count={false_positive_count}; score impact=needs_human_review until rule-level triage is attached and approved.")
        if "scanner-worker static tools unavailable" in lower or ("bandit" in lower and "unavailable" in lower):
            _append_unique(section["unavailable"], "Bandit source distinction: Bandit findings were parsed from available artifact text, but live scanner-worker Bandit execution is not verified for this report run.")


def _dynamic_medium_term_plan(status: dict[str, Any]) -> list[str]:
    capabilities = status.get("capabilities", {}) if isinstance(status, dict) else {}
    scanner_built = bool(capabilities.get("scanner_worker", {}).get("built"))
    github_built = bool(capabilities.get("github_app_private_repo_flow", {}).get("built"))
    mid_built = bool(capabilities.get("mid_modules", {}).get("built"))
    retainer_built = bool(capabilities.get("retainer_modules", {}).get("built"))
    readiness_built = bool(capabilities.get("report_readiness_gate", {}).get("built"))
    plan: list[str] = []
    plan.append("Run and attach verified scanner-worker artifacts for dependency, secret, static-analysis, coverage, and complexity evidence in each client-facing report." if scanner_built else "Build scanner-worker execution for dependency, secret, static-analysis, coverage, and complexity evidence.")
    plan.append("Maintain and verify GitHub App/private-repository authorization evidence in hosted report runs without exposing credentials." if github_built else "Build authenticated GitHub App/private-repository authorization before private-repo client delivery.")
    plan.append("Maintain Mid assessment modules and attach verified QA/parity/stakeholder/roadmap evidence when the selected workflow requires them." if mid_built else "Build Mid assessment modules for QA/parity/stakeholder/roadmap evidence.")
    plan.append("Maintain Retainer Ops modules and attach verified weekly/monthly/release evidence when a retainer workflow is selected." if retainer_built else "Build Retainer Ops modules for weekly/monthly/release evidence.")
    plan.append("Run and attach deployment, smoke-test, report-readiness, delivery-manifest, final-review, and client-acceptance artifacts before client-facing delivery." if readiness_built else "Build report readiness and delivery-manifest gates before client-facing delivery.")
    return plan


def _dynamic_resourcing_recommendation() -> list[str]:
    return [
        "Product Engineering Architect: validate maturity scoring, architecture/debt conclusions, evidence-state classification, and client-facing recommendations.",
        "Product Engineer: repair high-priority findings, run and attach verified scanner-worker artifacts, and maintain frontend/backend integrations.",
        "Product Quality Engineer: verify QA/parity evidence, report quality, safety boundaries, delivery-manifest status, and final client readiness.",
    ]


def _dynamic_repairs() -> list[str]:
    return [
        "Triage and repair confirmed findings in risk order, starting with secrets, dependency findings, static-analysis findings, and CI gaps.",
        "Run and attach scanner-worker execution artifacts for pip-audit, npm audit, OSV Scanner, Semgrep, Bandit, ESLint, TypeScript, and gitleaks/trufflehog before scanner-clean claims.",
        "Complete report-readiness, final-review, delivery-manifest, and client-acceptance checks before client-facing delivery.",
    ]


def _dynamic_risk_register(result: dict[str, Any]) -> list[str]:
    current = [str(item) for item in result.get("risk_register", []) or []]
    kept = [
        item
        for item in current
        if not (
            "cli scanners are marked unavailable until a sandboxed worker executes" in item.lower()
            or "add scanner worker" in item.lower()
            or "add scanner workers" in item.lower()
        )
    ]
    _append_unique(kept, "Private repositories require backend GitHub credentials; the browser must never receive a GitHub token.")
    _append_unique(kept, "Hosted servers cannot scan a user's local filesystem; hosted mode must use authorized repository APIs only.")
    _append_unique(kept, "CLI scanner results remain unavailable for a report run until scanner-worker artifacts are executed against an authorized checkout and attached to that run.")
    _append_unique(kept, "Production-impacting remediation must remain human-approved.")
    return kept


def apply_report_evidence_status(result: dict[str, Any]) -> dict[str, Any]:
    """Attach evidence-state classification without hiding unavailable evidence."""
    status = build_report_evidence_status(result)
    result["report_evidence_status"] = status
    _apply_dependency_language(result)
    _apply_secret_language(result)
    _apply_static_language(result)
    result["medium_term_plan"] = _dynamic_medium_term_plan(status)
    result["resourcing_recommendation"] = _dynamic_resourcing_recommendation()
    result["repairs"] = _dynamic_repairs()
    result["risk_register"] = _dynamic_risk_register(result)
    return result
