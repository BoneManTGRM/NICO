from __future__ import annotations

import os
from typing import Any

from nico.hosted_dependency_normalization import exact_osv_dependencies, parse_requirements_normalized
from nico.report_truth_runtime_patch import apply_dependency_score_consistency, normalize_report_dependency_evidence


BUILD_GUARD_VERSION = "truth-guards-2026-07-08.1"


def build_truth_guard_status() -> dict[str, Any]:
    deps = parse_requirements_normalized("PyJWT[crypto]==2.13.0\n")
    exact = exact_osv_dependencies(deps)
    sample = {
        "maturity_signal": {"level": "Senior", "score": 89, "summary": "sample"},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is green from available evidence.",
                "evidence": ["OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0: GHSA-example."],
                "findings": [],
                "unavailable": [],
            },
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86},
            {"id": "secrets_review", "label": "Secrets", "status": "green", "score": 90},
            {"id": "static_analysis", "label": "Static", "status": "green", "score": 86},
            {"id": "ci_cd", "label": "CI/CD", "status": "green", "score": 95},
            {"id": "architecture_debt", "label": "Architecture", "status": "green", "score": 94},
            {"id": "velocity_complexity", "label": "Velocity", "status": "green", "score": 82},
        ],
    }
    sample = normalize_report_dependency_evidence(sample)
    sample = apply_dependency_score_consistency(sample)
    dependency = sample["sections"][0]
    return {
        "status": "ok",
        "truth_guard_version": BUILD_GUARD_VERSION,
        "git_sha": os.getenv("GIT_COMMIT_SHA") or os.getenv("RENDER_GIT_COMMIT") or os.getenv("VERCEL_GIT_COMMIT_SHA") or os.getenv("RAILWAY_GIT_COMMIT_SHA") or "unknown",
        "normalized_pyjwt_extra": exact == [{"name": "PyJWT", "version": "2.13.0", "ecosystem": "PyPI"}],
        "sample_exact_osv_dependencies": exact,
        "sample_dependency_score_after_guard": dependency.get("score"),
        "sample_dependency_status_after_guard": dependency.get("status"),
        "sample_contains_malformed_pyjwt_extra": "@[crypto]" in str(sample),
        "scanner_clean_claim_policy": "No scanner-clean, release-ready, or client-ready claim without current-run artifacts.",
    }
