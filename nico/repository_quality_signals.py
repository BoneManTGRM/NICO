from __future__ import annotations

import re
from typing import Any

_ROUTE_ALIAS_RE = re.compile(
    r"^\s*export\s*\{\s*default\s*\}\s*from\s*['\"][^'\"]+['\"]\s*;?\s*$",
    re.DOTALL,
)
_PLACEHOLDER_MARKERS = (
    "coming soon",
    "not implemented",
    "placeholder page",
    "todo: implement",
    "under construction",
)
_PATCH_SUFFIXES = ("_patch.py", "_compat.py", "_fallback.py")
_LATEST_DEPLOYED_SHA_RE = re.compile(
    r"latest verified deployed main commit\s+is\s+`([0-9a-f]{40})`",
    re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _finding(
    *,
    code: str,
    title: str,
    severity: str,
    confidence: float,
    category: str,
    evidence: list[str],
    affected_files: list[str],
    business_impact: str,
    technical_impact: str,
    recommendation: str,
    verification: str,
    exploitability: str = "low",
) -> dict[str, Any]:
    return {
        "code": code,
        "title": title,
        "severity": severity,
        "confidence": confidence,
        "category": category,
        "evidence": evidence,
        "affected_files": affected_files,
        "business_impact": business_impact,
        "technical_impact": technical_impact,
        "recommendation": recommendation,
        "verification_method": verification,
        "exploitability": exploitability,
        "report_only": True,
        "automatic_change_allowed": False,
    }


def analyze_branch_hygiene(
    branches: list[dict[str, Any]] | None,
    *,
    truncated: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    branches = [item for item in (branches or []) if isinstance(item, dict)]
    count = len(branches)
    evidence: list[str] = []
    unavailable: list[str] = []
    findings: list[dict[str, Any]] = []
    if error:
        unavailable.append(f"Branch inventory unavailable: {error}")
    else:
        suffix = " or more" if truncated else ""
        evidence.append(f"GitHub branch inventory returned {count}{suffix} branch(es).")
        if count >= 250:
            findings.append(
                _finding(
                    code="branch_inventory_large",
                    title="Very large branch inventory increases repository maintenance cost",
                    severity="high",
                    confidence=0.98,
                    category="repository_hygiene",
                    evidence=[evidence[-1]],
                    affected_files=[],
                    business_impact=(
                        "A very large branch inventory increases review noise, cleanup time, merge confusion, and the "
                        "chance that engineers work from obsolete code."
                    ),
                    technical_impact=(
                        "Branch enumeration, policy review, release triage, and stale-reference analysis become slower "
                        "and more error-prone."
                    ),
                    recommendation=(
                        "Create a read-only branch inventory, identify protected and active branches, then use a "
                        "human-approved retention policy to archive or delete merged and obsolete branches in batches."
                    ),
                    verification=(
                        "Recount branches after each approved cleanup batch and confirm protected, release, incident, "
                        "and active feature branches remain."
                    ),
                )
            )
        elif count >= 100:
            findings.append(
                _finding(
                    code="branch_inventory_elevated",
                    title="Elevated branch inventory should be governed",
                    severity="medium",
                    confidence=0.95,
                    category="repository_hygiene",
                    evidence=[evidence[-1]],
                    affected_files=[],
                    business_impact="Unmanaged branches create avoidable review and maintenance overhead.",
                    technical_impact="Obsolete refs make release and ownership analysis harder.",
                    recommendation="Define retention rules and review merged or inactive branches before deletion.",
                    verification="Confirm branch count and protected-branch inventory after human-approved cleanup.",
                )
            )
    return {
        "status": "available" if not error else "unavailable",
        "branch_count": count if not error else None,
        "truncated": bool(truncated),
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
    }


def analyze_frontend_routes(
    tree_paths: list[str],
    files: dict[str, str],
) -> dict[str, Any]:
    route_paths = sorted(
        path
        for path in tree_paths
        if path.startswith("apps/web/app/") and path.endswith("/page.tsx")
    )
    aliases: list[str] = []
    placeholders: list[str] = []
    substantive: list[str] = []
    unread: list[str] = []
    for path in route_paths:
        text = files.get(path)
        if text is None:
            unread.append(path)
            continue
        stripped = text.strip()
        if _ROUTE_ALIAS_RE.fullmatch(stripped):
            aliases.append(path)
            continue
        lower = stripped.lower()
        if any(marker in lower for marker in _PLACEHOLDER_MARKERS):
            placeholders.append(path)
            continue
        substantive.append(path)

    evidence = [
        (
            "Frontend route review: "
            f"routes={len(route_paths)}, route_aliases={len(aliases)}, "
            f"explicit_placeholders={len(placeholders)}, substantive_or_composed={len(substantive)}, "
            f"unread={len(unread)}."
        )
    ]
    if aliases:
        evidence.append(
            "Small page.tsx route aliases were recognized as intentional re-exports rather than incomplete pages: "
            + ", ".join(aliases[:12])
            + ("." if len(aliases) <= 12 else ", ...")
        )
    findings: list[dict[str, Any]] = []
    if placeholders:
        findings.append(
            _finding(
                code="frontend_explicit_placeholders",
                title="Explicit frontend placeholder routes reduce product readiness",
                severity="medium",
                confidence=0.94,
                category="frontend_completeness",
                evidence=[f"Explicit placeholder markers were found in: {', '.join(placeholders[:20])}."],
                affected_files=placeholders[:20],
                business_impact="Customers may encounter incomplete workflows or unclear product boundaries.",
                technical_impact="Placeholder routes can conceal missing data, state, authorization, or error handling.",
                recommendation=(
                    "Define the route contract, required API evidence, loading/error/empty states, and acceptance tests; "
                    "keep the route disabled or clearly labeled until those conditions are met."
                ),
                verification="Run the frontend build and route-level tests, then verify the workflow on mobile and desktop.",
            )
        )
    return {
        "status": "available" if route_paths else "not_detected",
        "route_count": len(route_paths),
        "route_aliases": aliases,
        "explicit_placeholders": placeholders,
        "substantive_or_composed": substantive,
        "unread_routes": unread,
        "evidence": evidence,
        "findings": findings,
        "unavailable": (
            [f"{len(unread)} route file(s) were not available in the bounded text sample."] if unread else []
        ),
    }


def analyze_runtime_patch_surface(
    tree_paths: list[str],
    files: dict[str, str],
) -> dict[str, Any]:
    patch_files = sorted(
        path
        for path in tree_paths
        if path.startswith("nico/") and path.endswith(_PATCH_SUFFIXES)
    )
    init_text = files.get("nico/__init__.py", "")
    installer_calls = [
        line.strip()
        for line in init_text.splitlines()
        if re.match(r"^(?:install|patch|apply)_[A-Za-z0-9_]+\(\)\s*$", line.strip())
    ]
    evidence = [
        f"Runtime compatibility surface: patch/compat/fallback modules={len(patch_files)}; package import-time installer calls={len(installer_calls)}."
    ]
    findings: list[dict[str, Any]] = []
    if len(patch_files) >= 20 or len(installer_calls) >= 12:
        severity = "high" if len(patch_files) >= 40 or len(installer_calls) >= 25 else "medium"
        findings.append(
            _finding(
                code="runtime_patch_surface",
                title="Large runtime patch and compatibility surface creates import-order fragility",
                severity=severity,
                confidence=0.99,
                category="runtime_patch_surface",
                evidence=[evidence[0], *patch_files[:12]],
                affected_files=["nico/__init__.py", *patch_files[:19]],
                business_impact=(
                    "Import-order regressions and duplicated compatibility behavior increase debugging time, release risk, "
                    "and the cost of onboarding engineers."
                ),
                technical_impact=(
                    "Many import-time installers can replace references in different orders, obscure the canonical "
                    "implementation, and make idempotency difficult to reason about."
                ),
                recommendation=(
                    "Consolidate installers behind an explicit bootstrap registry, migrate one capability family per "
                    "release, preserve idempotency tests, and retire compatibility modules only after import-path proof."
                ),
                verification=(
                    "Snapshot installer order; run import-order, double-bootstrap, API startup, full assessment, CI, "
                    "and production smoke tests for each migration slice."
                ),
            )
        )
    return {
        "status": "available",
        "patch_compat_fallback_count": len(patch_files),
        "package_installer_call_count": len(installer_calls),
        "sample_files": patch_files[:25],
        "evidence": evidence,
        "findings": findings,
        "unavailable": [] if init_text else ["nico/__init__.py was not available in the bounded text sample."],
    }


def _relative_markdown_links(text: str) -> list[str]:
    links: list[str] = []
    for raw in _MARKDOWN_LINK_RE.findall(text):
        value = raw.strip().split("#", 1)[0]
        if not value or "://" in value or value.startswith(("mailto:", "#", "/")):
            continue
        if any(char in value for char in (" ", "{", "}")):
            continue
        links.append(value.lstrip("./"))
    return links


def analyze_documentation_alignment(
    tree_paths: list[str],
    files: dict[str, str],
    *,
    current_default_branch_sha: str = "",
) -> dict[str, Any]:
    docs = {
        path: text
        for path, text in files.items()
        if path.lower().endswith(".md")
        and (path in {"README.md", "ARCHITECTURE.md"} or path.startswith("docs/"))
    }
    tree = set(tree_paths)
    missing_links: list[str] = []
    stale_release_claims: list[dict[str, str]] = []
    for path, text in docs.items():
        for link in _relative_markdown_links(text):
            if link not in tree and not any(item.startswith(link.rstrip("/") + "/") for item in tree):
                missing_links.append(f"{path} -> {link}")
        for sha in _LATEST_DEPLOYED_SHA_RE.findall(text):
            if current_default_branch_sha and sha != current_default_branch_sha:
                stale_release_claims.append(
                    {
                        "path": path,
                        "documented_sha": sha,
                        "current_default_branch_sha": current_default_branch_sha,
                    }
                )

    evidence = [
        f"Documentation alignment checked {len(docs)} Markdown file(s) against {len(tree_paths)} repository path(s)."
    ]
    if current_default_branch_sha:
        evidence.append(f"Current default-branch head used for release-claim comparison: {current_default_branch_sha}.")
    findings: list[dict[str, Any]] = []
    if stale_release_claims:
        affected = sorted({item["path"] for item in stale_release_claims})
        findings.append(
            _finding(
                code="documentation_deployment_sha_drift",
                title="Documentation claims an outdated latest deployed main commit",
                severity="high",
                confidence=0.99,
                category="documentation_drift",
                evidence=[
                    (
                        f"{item['path']} documents {item['documented_sha']} as the latest verified deployed main commit, "
                        f"while the assessed default-branch head is {item['current_default_branch_sha']}."
                    )
                    for item in stale_release_claims
                ],
                affected_files=affected,
                business_impact=(
                    "Customers and operators can make release decisions from obsolete deployment evidence, increasing "
                    "incident response and audit costs."
                ),
                technical_impact="The canonical status document no longer matches the repository version being assessed.",
                recommendation=(
                    "Update the status block only from exact-SHA deployment and production-smoke evidence, and retain "
                    "the prior proof in append-only history."
                ),
                verification=(
                    "Confirm the documented SHA matches the deployed frontend/backend identities and the retained "
                    "authorized production proof."
                ),
            )
        )
    if missing_links:
        findings.append(
            _finding(
                code="documentation_missing_paths",
                title="Documentation contains repository-relative paths that were not found",
                severity="medium",
                confidence=0.9,
                category="documentation_drift",
                evidence=missing_links[:20],
                affected_files=sorted({item.split(" -> ", 1)[0] for item in missing_links[:20]}),
                business_impact="Broken documentation paths increase onboarding and operator-resolution time.",
                technical_impact="Instructions or architecture references may point to moved or removed files.",
                recommendation="Update links or restore the documented file, then add a documentation-link check to CI.",
                verification="Run the documentation-link check and manually open the corrected high-value references.",
            )
        )
    return {
        "status": "available" if docs else "unavailable",
        "documents_checked": len(docs),
        "missing_link_count": len(missing_links),
        "stale_release_claim_count": len(stale_release_claims),
        "evidence": evidence,
        "findings": findings,
        "unavailable": [] if docs else ["No Markdown documentation was available in the bounded text sample."],
    }


def analyze_security_configuration(posture: dict[str, Any] | None) -> dict[str, Any]:
    posture = posture if isinstance(posture, dict) else {}
    evidence: list[str] = []
    unavailable: list[str] = []
    findings: list[dict[str, Any]] = []
    for key, label in (
        ("code_scanning", "Code scanning"),
        ("secret_scanning", "Secret scanning"),
        ("dependabot", "Dependabot alerts"),
    ):
        item = posture.get(key) if isinstance(posture.get(key), dict) else {}
        status = str(item.get("status") or "unavailable")
        count = item.get("open_alert_count")
        if status == "available":
            evidence.append(f"{label} API returned open_alert_count={int(count or 0)}.")
            continue
        message = str(item.get("message") or "API evidence was unavailable.")
        unavailable.append(f"{label}: {message}")
        if status == "disabled":
            findings.append(
                _finding(
                    code=f"{key}_disabled",
                    title=f"{label} are disabled",
                    severity="medium",
                    confidence=0.98,
                    category="security_configuration",
                    evidence=[f"{label} API reported that the feature is disabled."],
                    affected_files=[],
                    business_impact="Disabled repository alerts can delay detection and increase remediation cost.",
                    technical_impact="The repository lacks the provider's continuous alert signal for this category.",
                    recommendation=(
                        f"Review licensing, permissions, and repository policy, then enable {label.lower()} if appropriate. "
                        "Enabling remains an owner-approved configuration change."
                    ),
                    verification=f"Re-query the {label.lower()} API and confirm it returns an available alert inventory.",
                )
            )
    return {
        "status": "available" if posture else "unavailable",
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
        "posture": posture,
    }


def build_repository_quality_signals(
    *,
    tree_paths: list[str],
    files: dict[str, str],
    branches: list[dict[str, Any]] | None = None,
    branches_truncated: bool = False,
    branches_error: str | None = None,
    current_default_branch_sha: str = "",
    security_posture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    groups = {
        "branch_hygiene": analyze_branch_hygiene(
            branches,
            truncated=branches_truncated,
            error=branches_error,
        ),
        "frontend_routes": analyze_frontend_routes(tree_paths, files),
        "runtime_patch_surface": analyze_runtime_patch_surface(tree_paths, files),
        "documentation_alignment": analyze_documentation_alignment(
            tree_paths,
            files,
            current_default_branch_sha=current_default_branch_sha,
        ),
        "security_configuration": analyze_security_configuration(security_posture),
    }
    findings = [
        finding
        for group in groups.values()
        for finding in group.get("findings", [])
        if isinstance(finding, dict)
    ]
    evidence = [
        evidence
        for group in groups.values()
        for evidence in group.get("evidence", [])
        if str(evidence).strip()
    ]
    unavailable = [
        note
        for group in groups.values()
        for note in group.get("unavailable", [])
        if str(note).strip()
    ]
    return {
        "status": "complete",
        "scoring_effect": "advisory_only_until_calibrated",
        "groups": groups,
        "finding_count": len(findings),
        "findings": findings,
        "evidence": evidence,
        "unavailable": unavailable,
        "truth_rule": (
            "Route aliases are not classified as placeholders. Branch staleness is not claimed from count alone. "
            "Security features are not called enabled, disabled, or clean unless the provider API returns that evidence."
        ),
    }


__all__ = [
    "analyze_branch_hygiene",
    "analyze_documentation_alignment",
    "analyze_frontend_routes",
    "analyze_runtime_patch_surface",
    "analyze_security_configuration",
    "build_repository_quality_signals",
]
