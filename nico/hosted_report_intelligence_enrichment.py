from __future__ import annotations

import re
import sys
from typing import Any, Callable

import requests

from nico.report_repair_intelligence import (
    build_report_repair_intelligence,
    render_repair_intelligence_markdown,
)
from nico.repository_quality_signals import build_repository_quality_signals

PATCH_VERSION = "nico.hosted_report_intelligence_enrichment.v1"
_MARKER = "_nico_hosted_report_intelligence_enrichment_v1"
_MAX_BRANCH_PAGES = 10
_MAX_BRANCHES = 1000
_CRITICAL_QUALITY_FILES = (
    "README.md",
    "ARCHITECTURE.md",
    "docs/PROJECT_STATUS.md",
    "nico/__init__.py",
)


def _severity_for_risk(kind: str) -> str:
    return {
        "python_eval_exec": "critical",
        "python_shell_true": "high",
        "python_os_system": "high",
        "unsafe_yaml_load": "high",
        "pickle_loads": "high",
        "js_inner_html": "high",
        "react_dangerous_html": "high",
        "tls_verify_disabled": "critical",
    }.get(kind, "medium")


def _exploitability_for_risk(kind: str) -> str:
    return {
        "python_eval_exec": "high",
        "python_shell_true": "high",
        "python_os_system": "high",
        "unsafe_yaml_load": "medium",
        "pickle_loads": "high",
        "js_inner_html": "medium",
        "react_dangerous_html": "medium",
        "tls_verify_disabled": "medium",
    }.get(kind, "unknown")


def _risk_business_impact(kind: str) -> str:
    return {
        "python_eval_exec": "Dynamic execution can expose systems, data, and service availability.",
        "python_shell_true": "Shell injection can create unauthorized command execution and incident-response cost.",
        "python_os_system": "Unbounded command construction can create command-injection and reliability risk.",
        "unsafe_yaml_load": "Unsafe deserialization can execute attacker-controlled object construction.",
        "pickle_loads": "Loading untrusted pickle data can execute arbitrary code.",
        "js_inner_html": "Unsafe HTML rendering can expose users to cross-site scripting.",
        "react_dangerous_html": "Unsanitized HTML can expose users to cross-site scripting.",
        "tls_verify_disabled": "Disabled certificate verification can expose credentials and data to interception.",
    }.get(kind, "The pattern may increase security, reliability, or maintenance cost.")


def _risk_recommendation(kind: str) -> str:
    return {
        "python_eval_exec": "Replace dynamic execution with an explicit parser or operation allowlist.",
        "python_shell_true": "Pass a validated argument vector with shell execution disabled.",
        "python_os_system": "Use bounded subprocess execution with an argument list and timeout.",
        "unsafe_yaml_load": "Use safe YAML deserialization and validate the parsed schema.",
        "pickle_loads": "Replace untrusted pickle input with a safe serialization format and schema validation.",
        "js_inner_html": "Render untrusted data as text or through an approved sanitizer policy.",
        "react_dangerous_html": "Prefer normal React text rendering or sanitize required HTML with an approved library.",
        "tls_verify_disabled": "Restore certificate verification and configure an approved CA bundle where required.",
    }.get(kind, "Apply the smallest evidence-supported defensive repair.")


def structured_source_findings(hosted: Any, files: dict[str, str]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path, text in files.items():
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            for kind, pattern, message in hosted.RISK_PATTERNS:
                if not pattern.search(line):
                    continue
                findings.append(
                    {
                        "code": kind,
                        "title": f"{kind.replace('_', ' ').title()} in {path}:{line_number}",
                        "severity": _severity_for_risk(kind),
                        "confidence": 0.9,
                        "category": kind,
                        "evidence": [
                            f"{path}:{line_number}: {kind} — {message}",
                            f"Bounded source excerpt: {stripped[:220]}",
                        ],
                        "affected_files": [path],
                        "business_impact": _risk_business_impact(kind),
                        "technical_impact": message,
                        "recommendation": _risk_recommendation(kind),
                        "verification_method": (
                            "Add the smallest regression test, run the affected test and full suite, then rerun the "
                            "relevant static analyzer against the exact commit."
                        ),
                        "exploitability": _exploitability_for_risk(kind),
                    }
                )
            for secret_kind, pattern in hosted.SECRET_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue
                findings.append(
                    {
                        "code": secret_kind,
                        "title": f"Potential secret exposure in {path}:{line_number}",
                        "severity": "critical",
                        "confidence": 0.92,
                        "category": "secret_exposure",
                        "evidence": [
                            f"{path}:{line_number}: potential {secret_kind} evidence {hosted.mask_secret(match.group(0))}"
                        ],
                        "affected_files": [path],
                        "business_impact": "A confirmed credential leak can expose systems, billing, users, or customer data.",
                        "technical_impact": "Credential-like source evidence was detected; the raw value is not retained.",
                        "recommendation": "Confirm whether the value is real, rotate it outside the code change, and move configuration to a managed secret store.",
                        "verification_method": "Rescan the current tree and full history, confirm the old credential is revoked, and test configuration loading.",
                        "exploitability": "high",
                    }
                )
    return findings


def _response_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:240]
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("documentation_url") or payload)[:240]
    return str(payload)[:240]


def get_paginated_branches(client: Any, repo: str) -> tuple[list[dict[str, Any]], str | None, bool]:
    branches: list[dict[str, Any]] = []
    for page in range(1, _MAX_BRANCH_PAGES + 1):
        try:
            response = requests.get(
                client.repo_url(repo, "/branches"),
                headers=client.headers,
                params={"per_page": 100, "page": page},
                timeout=25,
            )
        except requests.RequestException as exc:
            return branches, f"GitHub branch request failed: {exc}", False
        if response.status_code >= 400:
            return branches, f"GitHub branch API returned {response.status_code}: {_response_message(response)}", False
        try:
            page_items = response.json()
        except ValueError:
            return branches, "GitHub branch API returned a non-JSON response.", False
        if not isinstance(page_items, list):
            return branches, "GitHub branch API did not return a list.", False
        branches.extend(item for item in page_items if isinstance(item, dict))
        if len(page_items) < 100:
            return branches, None, False
    return branches[:_MAX_BRANCHES], None, True


def get_default_branch_head(client: Any, repo: str, branch: str) -> tuple[str, str | None]:
    data, error = client.get_json(client.repo_url(repo, f"/branches/{branch}"))
    if error:
        return "", error
    commit = data.get("commit") if isinstance(data, dict) and isinstance(data.get("commit"), dict) else {}
    sha = str(commit.get("sha") or "")
    return sha, None if sha else "Default-branch response did not include a commit SHA."


def _alert_inventory(client: Any, repo: str, endpoint: str) -> dict[str, Any]:
    try:
        response = requests.get(
            client.repo_url(repo, endpoint),
            headers=client.headers,
            params={"state": "open", "per_page": 100},
            timeout=25,
        )
    except requests.RequestException as exc:
        return {"status": "unavailable", "message": f"GitHub request failed: {exc}"}
    message = _response_message(response)
    if response.status_code in {403, 404}:
        lowered = message.lower()
        status = "disabled" if "disabled" in lowered or "not enabled" in lowered else "unavailable"
        return {"status": status, "http_status": response.status_code, "message": message}
    if response.status_code >= 400:
        return {"status": "unavailable", "http_status": response.status_code, "message": message}
    try:
        alerts = response.json()
    except ValueError:
        return {"status": "unavailable", "message": "GitHub alert API returned non-JSON data."}
    if not isinstance(alerts, list):
        return {"status": "unavailable", "message": "GitHub alert API did not return a list."}
    severities: dict[str, int] = {}
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        rule = alert.get("rule") if isinstance(alert.get("rule"), dict) else {}
        security = alert.get("security_advisory") if isinstance(alert.get("security_advisory"), dict) else {}
        severity = str(rule.get("security_severity_level") or security.get("severity") or "unknown").lower()
        severities[severity] = severities.get(severity, 0) + 1
    return {
        "status": "available",
        "open_alert_count": len(alerts),
        "severity_counts": severities,
        "result_limit": 100,
        "truncated": len(alerts) == 100,
    }


def get_security_posture(client: Any, repo: str) -> dict[str, Any]:
    return {
        "code_scanning": _alert_inventory(client, repo, "/code-scanning/alerts"),
        "secret_scanning": _alert_inventory(client, repo, "/secret-scanning/alerts"),
        "dependabot": _alert_inventory(client, repo, "/dependabot/alerts"),
    }


def _ensure_quality_files(client: Any, repo: str, profile: dict[str, Any]) -> dict[str, str]:
    files = dict(profile.get("files") or {})
    tree_paths = [str(path) for path in profile.get("tree_paths") or []]
    requested = list(_CRITICAL_QUALITY_FILES)
    requested.extend(
        path
        for path in tree_paths
        if path.startswith("apps/web/app/") and path.endswith("/page.tsx")
    )
    for path in requested:
        if path in files or path not in tree_paths:
            continue
        text, _error = client.get_text_file(repo, path)
        if text is not None:
            files[path] = text
    return files


def _quality_markdown(quality: dict[str, Any] | None) -> list[str]:
    quality = quality if isinstance(quality, dict) else {}
    findings = [item for item in quality.get("findings", []) or [] if isinstance(item, dict)]
    lines = ["## Repository Quality and Governance Signals", ""]
    lines.append(
        "These signals are advisory and evidence-bound. NICO does not delete branches, enable repository settings, "
        "rewrite route files, or refactor the assessed repository."
    )
    lines.append("")
    for evidence in quality.get("evidence", []) or []:
        lines.append(f"- {evidence}")
    if findings:
        lines.append("")
        lines.append("Prioritized quality findings:")
        for finding in findings[:15]:
            lines.append(
                f"- **{str(finding.get('severity') or 'unknown').upper()} — {finding.get('title')}**: "
                f"{finding.get('recommendation')}"
            )
    if quality.get("unavailable"):
        lines.append("")
        lines.append("Unavailable or permission-limited evidence:")
        for note in quality.get("unavailable", [])[:15]:
            lines.append(f"- {note}")
    lines.append("")
    return lines


def _append_sections(markdown: str, result: dict[str, Any]) -> str:
    extra = [
        *_quality_markdown(result.get("repository_quality_signals")),
        *render_repair_intelligence_markdown(result.get("repair_intelligence")),
    ]
    return markdown.rstrip() + "\n\n" + "\n".join(extra).strip() + "\n"


def enrich_hosted_result(hosted: Any, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete" or not result.get("repository"):
        return result
    repo = str(result.get("repository"))
    client = hosted.GitHubAssessmentClient()
    repo_meta, repo_error = client.get_repo(repo)
    if repo_error or not repo_meta:
        enriched = dict(result)
        enriched["repository_quality_signals"] = {
            "status": "unavailable",
            "findings": [],
            "evidence": [],
            "unavailable": [f"Repository quality enrichment unavailable: {repo_error}"],
        }
        enriched["repair_intelligence"] = build_report_repair_intelligence(enriched)
        return enriched

    profile = hosted.fetch_repository_profile(client, repo, repo_meta)
    profile["files"] = _ensure_quality_files(client, repo, profile)
    branch = str(repo_meta.get("default_branch") or "main")
    head_sha, head_error = get_default_branch_head(client, repo, branch)
    branches, branch_error, branches_truncated = get_paginated_branches(client, repo)
    security_posture = get_security_posture(client, repo)
    quality = build_repository_quality_signals(
        tree_paths=[str(path) for path in profile.get("tree_paths") or []],
        files=profile.get("files") or {},
        branches=branches,
        branches_truncated=branches_truncated,
        branches_error=branch_error,
        current_default_branch_sha=head_sha,
        security_posture=security_posture,
    )
    if head_error:
        quality.setdefault("unavailable", []).append(f"Default-branch head unavailable: {head_error}")

    source_findings = structured_source_findings(hosted, profile.get("files") or {})
    structured = [*quality.get("findings", []), *source_findings]
    enriched = dict(result)
    enriched["repository_quality_signals"] = quality
    enriched["security_configuration_evidence"] = security_posture
    enriched["repair_intelligence"] = build_report_repair_intelligence(
        enriched,
        structured_findings=structured,
    )
    metadata = dict(enriched.get("repository_metadata") or {})
    metadata.update(
        {
            "default_branch_head_sha": head_sha or None,
            "branch_count": len(branches) if not branch_error else None,
            "branch_inventory_truncated": branches_truncated,
            "quality_files_profiled": len(profile.get("files") or {}),
        }
    )
    enriched["repository_metadata"] = metadata
    quality_titles = [str(item.get("title")) for item in quality.get("findings", []) if item.get("title")]
    existing_findings = [str(item) for item in enriched.get("findings", []) or []]
    enriched["findings"] = list(dict.fromkeys([*existing_findings, *quality_titles]))
    enriched["repairs"] = [
        str(item.get("recommended_action"))
        for item in enriched["repair_intelligence"].get("candidates", [])[:10]
        if item.get("recommended_action")
    ] or list(enriched.get("repairs") or [])
    return enriched


def install_hosted_report_intelligence_enrichment() -> dict[str, Any]:
    from nico import hosted_assessment as hosted
    from nico import reports

    current_run: Callable[[dict[str, Any]], dict[str, Any]] = hosted.run_github_assessment
    already_installed = bool(getattr(current_run, _MARKER, False))
    if not already_installed:
        original_run = current_run

        def run_with_report_intelligence(payload: dict[str, Any]) -> dict[str, Any]:
            return enrich_hosted_result(hosted, original_run(payload))

        setattr(run_with_report_intelligence, _MARKER, True)
        setattr(run_with_report_intelligence, "_nico_previous", original_run)
        hosted.run_github_assessment = run_with_report_intelligence

        for module in list(sys.modules.values()):
            if module is None:
                continue
            try:
                if getattr(module, "run_github_assessment", None) is original_run:
                    setattr(module, "run_github_assessment", run_with_report_intelligence)
            except Exception:
                continue

    current_hosted_markdown = hosted.build_markdown
    if not getattr(current_hosted_markdown, "_nico_report_intelligence_markdown_v1", False):
        original_hosted_markdown = current_hosted_markdown

        def hosted_markdown_with_intelligence(result: dict[str, Any]) -> str:
            return _append_sections(original_hosted_markdown(result), result)

        setattr(hosted_markdown_with_intelligence, "_nico_report_intelligence_markdown_v1", True)
        setattr(hosted_markdown_with_intelligence, "_nico_previous", original_hosted_markdown)
        hosted.build_markdown = hosted_markdown_with_intelligence

    current_package_markdown = reports.markdown_report
    if not getattr(current_package_markdown, "_nico_report_intelligence_markdown_v1", False):
        original_package_markdown = current_package_markdown

        def package_markdown_with_intelligence(payload: dict[str, Any]) -> str:
            base = original_package_markdown(payload)
            if not payload.get("repair_intelligence") and not payload.get("repository_quality_signals"):
                return base
            return _append_sections(base, payload)

        setattr(package_markdown_with_intelligence, "_nico_report_intelligence_markdown_v1", True)
        setattr(package_markdown_with_intelligence, "_nico_previous", original_package_markdown)
        reports.markdown_report = package_markdown_with_intelligence

    return {
        "status": "already_installed" if already_installed else "installed",
        "version": PATCH_VERSION,
        "repository_quality_signals": True,
        "branch_inventory": True,
        "frontend_alias_false_positive_guard": True,
        "documentation_alignment": True,
        "security_configuration_evidence": True,
        "report_only_code_suggestions": True,
        "automatic_application_allowed": False,
        "human_review_required": True,
    }


__all__ = [
    "PATCH_VERSION",
    "enrich_hosted_result",
    "get_default_branch_head",
    "get_paginated_branches",
    "get_security_posture",
    "install_hosted_report_intelligence_enrichment",
    "structured_source_findings",
]
