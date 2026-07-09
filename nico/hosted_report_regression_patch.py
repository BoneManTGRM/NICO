from __future__ import annotations

from typing import Any

from nico.scanner_worker_artifacts import DEPENDENCY_TOOLS, SECRET_TOOLS, STATIC_TOOLS, normalize_scanner_worker_artifact

REQUIRED_CURRENT_RUN_TOOLS = DEPENDENCY_TOOLS + STATIC_TOOLS + SECRET_TOOLS
CURRENT_RELEASE_WORKFLOWS = (
    "NICO CI",
    "Node.js CI",
    "CodeQL Advanced",
    "Audit Evidence",
    "Security Audit Evidence",
)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _marker_requests_refresh(payload: dict[str, Any]) -> bool:
    if payload.get("refresh_full_evidence_requested") is True:
        return True
    marker = str(payload.get("authorized_by") or "").lower()
    if "frontend-refresh-full-evidence" in marker or "refresh-full-evidence" in marker:
        return True
    # The hosted Express button is a read-only authorized assessment request. In
    # hosted mode it should attempt evidence collection rather than silently
    # returning manifest-only yellow sections.
    return bool(payload.get("authorized")) and marker in {"", "unspecified", "frontend", "user"}


def _prepare_refresh_payload(payload: dict[str, Any]) -> dict[str, Any]:
    prepared = dict(payload or {})
    if _marker_requests_refresh(prepared):
        prepared["refresh_full_evidence_requested"] = True
        if str(prepared.get("authorized_by") or "").lower() in {"", "unspecified", "frontend", "user"}:
            prepared["authorized_by"] = "frontend-refresh-full-evidence"
        prepared.setdefault("run_scanner_worker", True)
        prepared.setdefault("scanner_worker_autorun", True)
        prepared.setdefault("full_history_secret_scan", True)
    return prepared


def _tool_category(tool: str) -> str:
    if tool in DEPENDENCY_TOOLS:
        return "dependency"
    if tool in STATIC_TOOLS:
        return "static"
    if tool in SECRET_TOOLS:
        return "secret"
    return "unknown"


def _tool_findings_count(payload: dict[str, Any]) -> int:
    findings = payload.get("findings")
    if isinstance(findings, list):
        return len(findings)
    for key in ("findings_count", "finding_count", "issue_count"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return 0


def _tool_records(artifact: dict[str, Any] | None) -> list[dict[str, Any]]:
    tools = artifact.get("tools") if isinstance(artifact, dict) else {}
    tools = tools if isinstance(tools, dict) else {}
    generated_at = str((artifact or {}).get("generated_at") or "")
    records: list[dict[str, Any]] = []
    for tool in REQUIRED_CURRENT_RUN_TOOLS:
        raw = tools.get(tool)
        if not isinstance(raw, dict):
            records.append(
                {
                    "tool": tool,
                    "category": _tool_category(tool),
                    "status": "missing",
                    "returncode": None,
                    "findings_count": 0,
                    "verified_for_this_report": False,
                    "current_run": False,
                    "reason": "No current-run tool record was attached by the hosted scanner worker.",
                }
            )
            continue
        status = str(raw.get("status") or "missing")
        reason = str(raw.get("reason") or raw.get("failure_reason") or raw.get("stderr") or "").strip()
        findings_count = _tool_findings_count(raw)
        verified = bool(raw.get("verified_for_this_report")) or (status == "completed" and bool(generated_at))
        records.append(
            {
                "tool": tool,
                "category": str(raw.get("category") or _tool_category(tool)),
                "status": status,
                "returncode": raw.get("returncode"),
                "findings_count": findings_count,
                "verified_for_this_report": verified,
                "current_run": bool(generated_at),
                "reason": reason,
                "execution_source": raw.get("execution_source") or "hosted_scanner_worker",
            }
        )
    return records


def _runtime_validation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    guards = result.get("report_quality_guards") if isinstance(result.get("report_quality_guards"), dict) else {}
    guard = guards.get("hosted_full_evidence_runtime") if isinstance(guards.get("hosted_full_evidence_runtime"), dict) else {}
    artifact = result.get("scanner_worker_artifact") if isinstance(result.get("scanner_worker_artifact"), dict) else None
    normalized = result.get("scanner_worker_artifact_normalized") if isinstance(result.get("scanner_worker_artifact_normalized"), dict) else None
    if normalized is None and artifact is not None:
        normalized = normalize_scanner_worker_artifact(artifact)
    records = _tool_records(artifact)
    missing = [item["tool"] for item in records if item["status"] in {"missing", "unavailable", "failed", "timeout"}]
    findings = [item["tool"] for item in records if int(item.get("findings_count") or 0) > 0]
    validation = {
        "status": str(guard.get("status") or "unknown"),
        "requested": bool(guard.get("refresh_full_evidence_requested") or result.get("refresh_full_evidence_requested")),
        "repository": result.get("repository"),
        "worker_execution_state": (artifact or {}).get("worker_execution_state"),
        "generated_at": (artifact or {}).get("generated_at"),
        "tool_records": records,
        "missing_or_unavailable_tools": missing,
        "tools_with_findings": findings,
        "normalized": normalized or {},
        "unavailable_data_notes": list((artifact or {}).get("unavailable_data_notes") or []),
    }
    return validation


def _append_runtime_notes_to_sections(result: dict[str, Any]) -> None:
    validation = _runtime_validation_from_result(result)
    result["hosted_full_evidence_runtime_validation"] = validation
    guards = result.setdefault("report_quality_guards", {})
    guard = guards.setdefault("hosted_full_evidence_runtime", {})
    if isinstance(guard, dict):
        guard["tool_records"] = validation["tool_records"]
        guard["missing_or_unavailable_tools"] = validation["missing_or_unavailable_tools"]
        guard["tools_with_findings"] = validation["tools_with_findings"]
        guard["unavailable_data_notes"] = validation["unavailable_data_notes"]

    sections = {section.get("id"): section for section in result.get("sections", []) or [] if isinstance(section, dict)}
    grouped: dict[str, list[dict[str, Any]]] = {"dependency": [], "static": [], "secret": []}
    for record in validation["tool_records"]:
        category = record.get("category")
        if category in grouped:
            grouped[category].append(record)
    category_to_section = {"dependency": "dependency_health", "static": "static_analysis", "secret": "secrets_review"}
    for category, records in grouped.items():
        section = sections.get(category_to_section[category])
        if not section:
            continue
        section.setdefault("evidence", [])
        section.setdefault("unavailable", [])
        status_line = ", ".join(f"{item['tool']}={item['status']}" for item in records)
        if status_line:
            section["evidence"] = _unique(list(section.get("evidence", []) or []) + [f"Refresh Full Evidence current-run {category} tool status: {status_line}."])
        unavailable_lines = []
        for item in records:
            if item["status"] in {"missing", "unavailable", "failed", "timeout"}:
                reason = item.get("reason") or "no reason returned"
                unavailable_lines.append(f"{item['tool']} current-run status={item['status']}; reason={reason}")
        if unavailable_lines:
            section["unavailable"] = _unique(list(section.get("unavailable", []) or []) + unavailable_lines)


def _patch_hosted_refresh_contract() -> None:
    from nico import hosted_assessment

    original = getattr(hosted_assessment, "_nico_original_run_github_assessment_refresh", None)
    if original is None:
        original = hosted_assessment.run_github_assessment
        hosted_assessment._nico_original_run_github_assessment_refresh = original

    def run_github_assessment_with_refresh_contract(payload: dict[str, Any]) -> dict[str, Any]:
        prepared = _prepare_refresh_payload(payload)
        result = original(prepared)
        if isinstance(result, dict) and result.get("status") == "complete":
            result["authorized_by"] = prepared.get("authorized_by") or "unspecified"
            result["refresh_full_evidence_requested"] = bool(prepared.get("refresh_full_evidence_requested"))
            result["run_scanner_worker"] = bool(prepared.get("run_scanner_worker", True))
            result["scanner_worker_autorun"] = bool(prepared.get("scanner_worker_autorun", True))
            result["full_history_secret_scan"] = bool(prepared.get("full_history_secret_scan", True))
        return result

    hosted_assessment.run_github_assessment = run_github_assessment_with_refresh_contract


def _latest_runs_by_name(workflow_runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in workflow_runs:
        if not isinstance(run, dict):
            continue
        name = str(run.get("name") or run.get("workflow_name") or "").strip()
        if name and name not in latest:
            latest[name] = run
    return latest


def _patch_ci_release_readiness_scoring() -> None:
    from nico import hosted_assessment

    def analyze_ci_release_readiness(workflows: dict[str, str], workflow_unavailable: list[str], workflow_runs: list[dict[str, Any]], runs_error: str | None) -> dict[str, Any]:
        evidence: list[str] = []
        findings: list[str] = []
        unavailable = list(workflow_unavailable)
        score = 20
        combined = "\n".join(workflows.values()).lower()
        if workflows:
            evidence.append(f"GitHub Actions workflows found: {', '.join(workflows.keys())}.")
            score = 55
            if any(term in combined for term in ["pytest", "npm run lint", "next build", "npm test", "ruff", "mypy", "eslint", "tsc --noemit", "tsc --noemit"]):
                score += 18
                evidence.append("Workflow text includes test, lint, or build commands.")
            else:
                findings.append("Workflow files exist but no obvious test/lint/build command was detected.")
            if "permissions:" in combined:
                score += 7
                evidence.append("Workflow text includes explicit permissions blocks.")
            else:
                findings.append("Workflow files do not show explicit permissions blocks in inspected text.")
            if any(term in combined for term in ["deploy", "vercel", "render", "railway", "flyctl", "docker"]):
                score += 8
                evidence.append("Workflow text includes deployment-related commands or providers.")
            if "secrets." in combined:
                evidence.append("Workflow text references GitHub secrets, which is expected for controlled deploy credentials but should be reviewed.")
        else:
            evidence.append("No GitHub Actions workflow files were available for analysis.")
            findings.append("No CI/CD workflow files were found through GitHub contents access.")

        if runs_error:
            unavailable.append(f"Workflow run history unavailable: {runs_error}")
        else:
            recent = workflow_runs[:100]
            success = sum(1 for run in recent if run.get("conclusion") == "success")
            failed = sum(1 for run in recent if run.get("conclusion") in {"failure", "timed_out", "cancelled"})
            evidence.append(f"GitHub Actions workflow runs returned in assessment window: {len(recent)}; success={success}; non-success={failed}.")
            latest = _latest_runs_by_name(recent)
            current = {name: latest[name] for name in CURRENT_RELEASE_WORKFLOWS if name in latest}
            if current:
                current_line = ", ".join(f"{name}={run.get('conclusion') or run.get('status') or 'unknown'}" for name, run in current.items())
                evidence.append(f"Current release-readiness latest checks: {current_line}.")
                current_failures = [name for name, run in current.items() if run.get("conclusion") not in {"success", "skipped"}]
                if not current_failures and len(current) >= 3:
                    score += 8
                    evidence.append("Current release readiness is green based on the latest required checks; historical failures are disclosed separately.")
                elif current_failures:
                    findings.append("Current release-readiness latest checks contain non-success results: " + ", ".join(current_failures) + ".")
                    score -= 8
            if recent:
                conclusive = success + failed
                rate = success / max(1, conclusive)
                if failed:
                    findings.append(f"Historical workflow reliability includes {failed} non-success run(s); review reliability history separately from current release readiness.")
                if rate < 0.6 and not current:
                    score -= 8
                elif rate >= 0.8 and not current:
                    score += 8
        return {
            "score": max(20, min(score, 95)),
            "summary": "CI/CD maturity separates current release-readiness checks from historical workflow reliability.",
            "evidence": evidence + findings,
            "findings": findings,
            "unavailable": unavailable,
        }

    hosted_assessment.analyze_ci = analyze_ci_release_readiness


def _patch_runtime_evidence_diagnostics() -> None:
    from nico import hosted_full_evidence_runtime_v2

    original = getattr(hosted_full_evidence_runtime_v2, "_nico_original_ensure_hosted_runtime_evidence_diagnostics", None)
    if original is None:
        original = hosted_full_evidence_runtime_v2.ensure_hosted_runtime_evidence
        hosted_full_evidence_runtime_v2._nico_original_ensure_hosted_runtime_evidence_diagnostics = original

    def ensure_hosted_runtime_evidence_with_diagnostics(result: dict[str, Any]) -> dict[str, Any]:
        updated = original(result)
        if isinstance(updated, dict) and updated.get("status") == "complete":
            _append_runtime_notes_to_sections(updated)
        return updated

    hosted_full_evidence_runtime_v2.ensure_hosted_runtime_evidence = ensure_hosted_runtime_evidence_with_diagnostics


def _patch_trust_display_runtime_evidence() -> None:
    from nico import trust_report_display

    original = getattr(trust_report_display, "_nico_original_attach_trust_report_display_runtime", None)
    if original is None:
        original = trust_report_display.attach_trust_report_display
        trust_report_display._nico_original_attach_trust_report_display_runtime = original

    def attach_trust_report_display_with_runtime(result: dict[str, Any]) -> dict[str, Any]:
        updated = original(result)
        validation = updated.get("hosted_full_evidence_runtime_validation") if isinstance(updated.get("hosted_full_evidence_runtime_validation"), dict) else {}
        if not validation:
            return updated
        for section in updated.get("sections", []) or []:
            if not isinstance(section, dict) or section.get("id") not in {"trust_readiness", "trust_client_readiness"}:
                continue
            records = validation.get("tool_records") or []
            status = validation.get("status") or "unknown"
            missing = validation.get("missing_or_unavailable_tools") or []
            tool_status = ", ".join(f"{item.get('tool')}={item.get('status')}" for item in records[:9] if isinstance(item, dict))
            section["evidence"] = _unique(
                list(section.get("evidence", []) or [])
                + [
                    f"Refresh Full Evidence runtime validation: status={status}; requested={validation.get('requested')}; missing_or_unavailable={', '.join(missing) if missing else 'none'}.",
                    f"Refresh Full Evidence required tool records: {tool_status or 'none'}.",
                ]
            )
            if missing:
                section["findings"] = _unique(list(section.get("findings", []) or []) + ["Refresh Full Evidence still lacks current-run proof for: " + ", ".join(missing) + "."])
            break
        return updated

    trust_report_display.attach_trust_report_display = attach_trust_report_display_with_runtime


def install_hosted_report_regression_patch() -> None:
    _patch_ci_release_readiness_scoring()
    _patch_hosted_refresh_contract()
    _patch_runtime_evidence_diagnostics()
    _patch_trust_display_runtime_evidence()
