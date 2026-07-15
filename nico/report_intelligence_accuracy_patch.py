from __future__ import annotations

import posixpath
import re
from typing import Any, Callable

PATCH_VERSION = "nico.report_intelligence_accuracy.v1"
_MARKER = "_nico_report_intelligence_accuracy_v1"
_NONPRODUCTION_PARTS = {
    "test",
    "tests",
    "testing",
    "fixture",
    "fixtures",
    "example",
    "examples",
    "sample",
    "samples",
    "docs",
    "documentation",
    "test_lab",
}
_SYNTHETIC_SECRET_MARKERS = (
    "fake",
    "example",
    "sample",
    "test_only",
    "test-only",
    "dummy",
    "placeholder",
)
_DEPLOYED_SHA_RE = re.compile(
    r"latest verified deployed main commit\s+is\s+`([0-9a-f]{40})`",
    re.IGNORECASE,
)
_MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _path_parts(path: str) -> set[str]:
    return {part.lower() for part in str(path).replace("\\", "/").split("/") if part}


def _is_nonproduction_path(path: str) -> bool:
    return bool(_path_parts(path) & _NONPRODUCTION_PARTS)


def _looks_synthetic(text: str) -> bool:
    lower = str(text or "").lower()
    return any(marker in lower for marker in _SYNTHETIC_SECRET_MARKERS)


def _relative_links(doc_path: str, text: str) -> list[str]:
    base_dir = posixpath.dirname(doc_path)
    resolved: list[str] = []
    for raw in _MARKDOWN_LINK_RE.findall(text):
        value = raw.strip().split("#", 1)[0].split("?", 1)[0]
        if not value or "://" in value or value.startswith(("mailto:", "#", "/")):
            continue
        if any(char in value for char in (" ", "{", "}")):
            continue
        resolved.append(posixpath.normpath(posixpath.join(base_dir, value)))
    return resolved


def accurate_documentation_alignment(
    tree_paths: list[str],
    files: dict[str, str],
    *,
    current_default_branch_sha: str = "",
) -> dict[str, Any]:
    from nico.repository_quality_signals import _finding

    docs = {
        path: text
        for path, text in files.items()
        if path.lower().endswith(".md")
        and (path in {"README.md", "ARCHITECTURE.md"} or path.startswith("docs/"))
    }
    tree = set(tree_paths)
    missing_links: list[str] = []
    release_claim_differences: list[dict[str, str]] = []
    for path, text in docs.items():
        for resolved in _relative_links(path, text):
            if resolved not in tree and not any(item.startswith(resolved.rstrip("/") + "/") for item in tree):
                missing_links.append(f"{path} -> {resolved}")
        for documented_sha in _DEPLOYED_SHA_RE.findall(text):
            if current_default_branch_sha and documented_sha != current_default_branch_sha:
                release_claim_differences.append(
                    {
                        "path": path,
                        "documented_sha": documented_sha,
                        "current_default_branch_sha": current_default_branch_sha,
                    }
                )

    evidence = [
        f"Documentation alignment checked {len(docs)} Markdown file(s) against {len(tree_paths)} repository path(s)."
    ]
    if current_default_branch_sha:
        evidence.append(f"Current default-branch head observed: {current_default_branch_sha}.")
    findings: list[dict[str, Any]] = []
    if release_claim_differences:
        findings.append(
            _finding(
                code="documentation_release_claim_verification_needed",
                title="Documented deployed commit differs from the current default-branch head",
                severity="medium",
                confidence=0.82,
                category="documentation_drift",
                evidence=[
                    (
                        f"{item['path']} documents deployed commit {item['documented_sha']}; "
                        f"the current default-branch head is {item['current_default_branch_sha']}."
                    )
                    for item in release_claim_differences
                ],
                affected_files=sorted({item["path"] for item in release_claim_differences}),
                business_impact=(
                    "An unverified release-status mismatch can cause operators to rely on the wrong version during "
                    "support, audit, or incident response."
                ),
                technical_impact=(
                    "Default-branch head and deployed commit are different concepts. The documentation claim requires "
                    "provider deployment evidence before it can be called stale or correct."
                ),
                recommendation=(
                    "Compare the documented SHA with exact Railway/Vercel deployment identity and retained production "
                    "proof. Update the status document only when provider evidence confirms a different deployed SHA."
                ),
                verification=(
                    "Require exact frontend/backend deployed commit identity and successful production proof; do not "
                    "infer deployment state from the repository head alone."
                ),
            )
        )
    if missing_links:
        findings.append(
            _finding(
                code="documentation_missing_paths",
                title="Documentation contains repository-relative paths that were not found",
                severity="medium",
                confidence=0.92,
                category="documentation_drift",
                evidence=missing_links[:20],
                affected_files=sorted({item.split(" -> ", 1)[0] for item in missing_links[:20]}),
                business_impact="Broken documentation paths increase onboarding and operator-resolution time.",
                technical_impact="Instructions or architecture references may point to moved or removed files.",
                recommendation="Correct the links or restore the referenced file, then add a documentation-link check to CI.",
                verification="Run the documentation-link check and manually open the corrected high-value references.",
            )
        )
    return {
        "status": "available" if docs else "unavailable",
        "documents_checked": len(docs),
        "missing_link_count": len(missing_links),
        "release_claim_verification_count": len(release_claim_differences),
        "evidence": evidence,
        "findings": findings,
        "unavailable": [] if docs else ["No Markdown documentation was available in the bounded text sample."],
        "truth_rule": (
            "A documented deployed SHA is never declared stale merely because main has advanced. Provider deployment "
            "identity is required."
        ),
    }


def context_aware_source_findings(hosted: Any, files: dict[str, str]) -> list[dict[str, Any]]:
    from nico import hosted_report_intelligence_enrichment as enrichment

    original = getattr(context_aware_source_findings, "_nico_previous")
    production_files = {
        path: text
        for path, text in files.items()
        if not _is_nonproduction_path(path)
    }
    findings = original(hosted, production_files)
    retained: list[dict[str, Any]] = []
    for finding in findings:
        evidence_text = " ".join(str(item) for item in finding.get("evidence", []) or [])
        if finding.get("category") == "secret_exposure" and _looks_synthetic(evidence_text):
            continue
        finding = dict(finding)
        finding["source_context"] = "production_or_configuration"
        finding["false_positive_reduction"] = (
            "Test, fixture, example, sample, and documentation paths were excluded from prioritized source-pattern "
            "repair candidates."
        )
        retained.append(finding)
    return retained


def rebuild_enriched_reports(hosted: Any, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    enriched = dict(result)
    markdown = hosted.build_markdown(enriched)
    reports: dict[str, Any] = {
        "markdown": markdown,
        "html": hosted.build_html(markdown),
    }
    pdf_base64, pdf_error = hosted.build_pdf_base64(markdown)
    if pdf_base64:
        reports["pdf_base64"] = pdf_base64
        repo = str(enriched.get("repository") or "repository").replace("/", "-")
        reports["pdf_filename"] = f"nico-express-assessment-{repo}.pdf"
    elif pdf_error:
        notes = list(enriched.get("unavailable_data_notes") or [])
        if pdf_error not in notes:
            notes.append(pdf_error)
        enriched["unavailable_data_notes"] = notes
    enriched["reports"] = reports
    return enriched


def install_report_intelligence_accuracy_patch() -> dict[str, Any]:
    from nico import hosted_report_intelligence_enrichment as enrichment
    from nico import repository_quality_signals as quality

    current_docs = quality.analyze_documentation_alignment
    if not getattr(current_docs, _MARKER, False):
        setattr(accurate_documentation_alignment, _MARKER, True)
        setattr(accurate_documentation_alignment, "_nico_previous", current_docs)
        quality.analyze_documentation_alignment = accurate_documentation_alignment

    current_source = enrichment.structured_source_findings
    if not getattr(current_source, _MARKER, False):
        setattr(context_aware_source_findings, _MARKER, True)
        setattr(context_aware_source_findings, "_nico_previous", current_source)
        enrichment.structured_source_findings = context_aware_source_findings

    current_enrich: Callable[[Any, dict[str, Any]], dict[str, Any]] = enrichment.enrich_hosted_result
    if not getattr(current_enrich, _MARKER, False):
        original_enrich = current_enrich

        def enrich_and_rebuild(hosted: Any, result: dict[str, Any]) -> dict[str, Any]:
            enriched = original_enrich(hosted, result)
            return rebuild_enriched_reports(hosted, enriched)

        setattr(enrich_and_rebuild, _MARKER, True)
        setattr(enrich_and_rebuild, "_nico_previous", original_enrich)
        enrichment.enrich_hosted_result = enrich_and_rebuild

    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "report_formats_rebuilt_after_enrichment": True,
        "nonproduction_pattern_candidates_excluded": True,
        "synthetic_secret_candidates_excluded": True,
        "documentation_deployment_claim_requires_provider_proof": True,
        "automatic_application_allowed": False,
        "human_review_required": True,
    }


__all__ = [
    "PATCH_VERSION",
    "accurate_documentation_alignment",
    "context_aware_source_findings",
    "install_report_intelligence_accuracy_patch",
    "rebuild_enriched_reports",
]
