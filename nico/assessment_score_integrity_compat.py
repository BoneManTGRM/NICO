from __future__ import annotations

from pathlib import Path
from typing import Any

import nico.assessment_score_integrity as integrity
import nico.full_assessment_scorecard as scorecard
from nico.hosted_api_complexity_fallback import install_hosted_api_complexity_fallback
from nico.hosted_api_complexity_fallback_compat import (
    install_hosted_api_complexity_fallback as _install_hosted_api_complexity_fallback_compat,
)


# Preserve the public installer name while using the scoped v2 implementation.
install_hosted_api_complexity_fallback = _install_hosted_api_complexity_fallback_compat

_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
_ORIGINAL_CLASSIFIER = integrity.classify_secret_candidates
_ORIGINAL_ELIGIBLE_FILE = integrity._eligible_file


def deduplicated_secret_candidates(path: str, text: str) -> list[dict[str, Any]]:
    """Prefer the strongest classification when two rules match the same value."""

    selected: dict[tuple[str, int, str], dict[str, Any]] = {}
    for candidate in _ORIGINAL_CLASSIFIER(path, text):
        key = (
            str(candidate.get("path") or path),
            int(candidate.get("line") or 0),
            str(candidate.get("fingerprint") or ""),
        )
        current = selected.get(key)
        if current is None or _CONFIDENCE_RANK.get(str(candidate.get("confidence")), 0) > _CONFIDENCE_RANK.get(str(current.get("confidence")), 0):
            selected[key] = candidate
    return sorted(selected.values(), key=lambda item: (str(item.get("path")), int(item.get("line") or 0), str(item.get("kind"))))


def production_source_file(path: Path, root: Path, *, source_only: bool = False) -> bool:
    if not _ORIGINAL_ELIGIBLE_FILE(path, root, source_only=source_only):
        return False
    if not source_only:
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    parts = {part.lower() for part in relative.parts}
    name = path.name.lower()
    if parts & {"test", "tests", "fixture", "fixtures"}:
        return False
    if name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.ts", ".test.tsx", ".spec.js", ".spec.ts", ".spec.tsx")):
        return False
    return True


def _tool_sets(scanner: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    run = {str(item).lower() for item in scanner.get("tools_run") or []}
    failed = {str(item).lower() for item in scanner.get("failed_tools") or []}
    timed_out = {str(item).lower() for item in scanner.get("timed_out_tools") or []}
    return run, failed, timed_out


def calibrated_secrets_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = integrity._dict(repo.get("code_signal_evidence"))
    sampled_material = integrity._int(signals.get("potential_secret_pattern_hits"))
    built_in = integrity._scanner_result(scanner, "nico-secrets")
    counts = integrity._dict(built_in.get("finding_counts"))
    high = integrity._int(counts.get("high"))
    medium = integrity._int(counts.get("medium"))
    low = integrity._int(counts.get("low"))
    built_in_ran = str(built_in.get("status") or "") in {"passed", "failed"}

    run, failed, timed_out = _tool_sets(scanner)
    history_names = {"gitleaks", "trufflehog", "detect-secrets"}
    clean_history = sorted((run & history_names) - failed - timed_out)

    score = 68 if sampled_material == 0 else max(25, 60 - sampled_material * 8)
    if built_in_ran:
        score += 12
    if clean_history:
        score += min(16, len(clean_history) * 12)
    score -= min(55, high * 35)
    score -= min(18, medium * 8)
    score -= min(4, low)
    if not built_in_ran and not clean_history:
        score = min(score, 68)
    if high:
        score = min(score, 44)
    score = max(20, min(88, score))

    evidence = [
        f"Sampled repository text returned {sampled_material} material potential secret-pattern hit(s) after confidence classification.",
        f"NICO current-tree credential scanner status={built_in.get('status') or 'not run'}; high={high}, medium={medium}, low={low}; files={integrity._int(built_in.get('files_scanned'))}.",
        f"Clean dedicated history scanner evidence attached: {', '.join(clean_history) or 'none'}.",
        "Candidate output is masked and fingerprinted; raw credential values are not retained in assessment evidence.",
    ]
    findings: list[str] = []
    if high:
        findings.append(f"Immediately triage {high} high-confidence credential candidate(s) and rotate confirmed credentials outside NICO.")
    if medium:
        findings.append(f"Human-validate {medium} medium-confidence credential candidate(s) before report approval.")

    unavailable = ["A clean current-tree result is not proof that repository history contains no credentials."]
    if not clean_history:
        unavailable.extend(
            [
                "Full git-history secret coverage is not verified; current-tree classification cannot prove that repository history contains no credentials.",
                "Live gitleaks/trufflehog history evidence was not attached to this score.",
            ]
        )
    confidence = "scanner-and-repository-bound" if clean_history else "current-tree-scanner-bound" if built_in_ran else "limited"
    return scorecard._section(
        "secrets_review",
        "Secrets Exposure Review",
        score,
        "Secrets maturity reflects confidence-classified sampled evidence, masked current-tree scanning, and any clean dedicated history evidence attached to the same run.",
        evidence,
        findings=findings,
        unavailable=unavailable,
        confidence=confidence,
    )


def calibrated_static_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    signals = integrity._dict(repo.get("code_signal_evidence"))
    sampled = integrity._int(signals.get("risk_pattern_hits"))
    built_in = integrity._scanner_result(scanner, "nico-static")
    built_hits = integrity._int(built_in.get("finding_count"))
    built_in_ran = str(built_in.get("status") or "") in {"passed", "failed"}

    run, failed, timed_out = _tool_sets(scanner)
    external_names = {"bandit", "semgrep", "eslint"}
    clean_external = sorted((run & external_names) - failed - timed_out)

    score = 58 if sampled == 0 else max(30, 55 - sampled * 5)
    if built_in_ran:
        score += 16
    score += min(24, len(clean_external) * 8)
    score -= min(30, max(sampled, built_hits) * 5)
    score -= len(failed & external_names) * 8
    score -= len(timed_out & external_names) * 6
    if not built_in_ran and not clean_external:
        score = min(score, 60)
    score = max(25, min(90, score))

    evidence = [
        f"Sampled-file static risk-pattern hits: {sampled}.",
        f"NICO current-tree static scanner status={built_in.get('status') or 'not run'}; material hits={built_hits}; files={integrity._int(built_in.get('files_scanned'))}.",
        f"Clean language-specific analyzers attached: {', '.join(clean_external) or 'none'}; failed={len(failed & external_names)}; timed out={len(timed_out & external_names)}.",
    ]
    findings: list[str] = []
    material = max(sampled, built_hits)
    if material:
        findings.append(f"Review {material} current-tree static risk-pattern hit(s) before report approval.")
    if failed & external_names or timed_out & external_names:
        findings.append("One or more language-specific analyzers failed or timed out; semantic static-analysis evidence is incomplete.")
    unavailable = ["Tool execution and a clean bounded pattern result are not proof that no vulnerability exists."]
    if not clean_external:
        unavailable.append("Bandit, Semgrep, and ESLint semantic artifacts were not attached; the current-tree built-in result remains review-limited.")
    confidence = "scanner-and-repository-bound" if clean_external else "current-tree-scanner-bound" if built_in_ran else "limited"
    return scorecard._section(
        "static_analysis",
        "Static Analysis",
        score,
        "Static-analysis maturity combines bounded full-checkout current-tree scanning with clean language-specific analyzer execution where available.",
        evidence,
        findings=findings,
        unavailable=unavailable,
        confidence=confidence,
    )


def install_score_integrity_compatibility() -> dict[str, Any]:
    installed = bool(getattr(integrity, "_compatibility_installed", False))
    integrity.classify_secret_candidates = deduplicated_secret_candidates
    integrity._eligible_file = production_source_file
    integrity.calibrated_secrets_section = calibrated_secrets_section
    integrity.calibrated_static_section = calibrated_static_section
    scorecard._secrets_section = calibrated_secrets_section
    scorecard._static_section = calibrated_static_section
    complexity_fallback = install_hosted_api_complexity_fallback()
    integrity._compatibility_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": integrity.INTEGRITY_VERSION,
        "deduplicated_secret_candidates": True,
        "test_only_static_sources_excluded": True,
        "legacy_clean_scanner_evidence_supported": True,
        "hosted_api_complexity_fallback": complexity_fallback.get("status"),
        "hosted_api_complexity_fallback_version": complexity_fallback.get("version"),
        "hosted_api_complexity_shared_profile_override": complexity_fallback.get("shared_profile_override"),
    }


__all__ = [
    "calibrated_secrets_section",
    "calibrated_static_section",
    "deduplicated_secret_candidates",
    "install_score_integrity_compatibility",
    "production_source_file",
]
