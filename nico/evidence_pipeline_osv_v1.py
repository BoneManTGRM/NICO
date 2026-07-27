from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from nico.evidence_pipeline_common_v1 import _not_applicable, _skip_generated


def _all_exact_dependencies(runners: Any, repo_dir: Path) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for requirement_file in repo_dir.rglob("requirements*.txt"):
        if _skip_generated(requirement_file, repo_dir):
            continue
        try:
            lines = requirement_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            item = runners._normalize_requirement(line)
            if item:
                item = dict(item)
                item["source"] = str(requirement_file.relative_to(repo_dir))
                dependencies.append(item)
    for lockfile in repo_dir.rglob("package-lock.json"):
        if _skip_generated(lockfile, repo_dir):
            continue
        dependencies.extend(runners._package_lock_dependencies(lockfile))
    deduped: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in dependencies:
        key = (str(item.get("ecosystem") or ""), str(item.get("name") or ""), str(item.get("version") or ""))
        if all(key):
            deduped[key] = item
    return list(deduped.values())


def _full_osv_api_fallback(runners: Any, spec: Any, repo_dir: Path) -> dict[str, Any]:
    dependencies = _all_exact_dependencies(runners, repo_dir)
    if not dependencies:
        return _not_applicable(spec, "No exact dependency versions were available for OSV analysis in this snapshot.")
    findings: list[dict[str, Any]] = []
    batch_size = max(1, int(os.getenv("NICO_OSV_QUERY_BATCH_SIZE", "250")))
    batch_count = 0
    for start in range(0, len(dependencies), batch_size):
        batch = dependencies[start : start + batch_size]
        queries = [
            {"package": {"name": item["name"], "ecosystem": item["ecosystem"]}, "version": item["version"]}
            for item in batch
        ]
        batch_count += 1
        try:
            response = runners.requests.post(runners.OSV_API, json={"queries": queries}, timeout=45)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {
                "tool": spec.name,
                "status": "failed",
                "category": spec.category,
                "returncode": 2,
                "returncode_valid": False,
                "timed_out": False,
                "output_truncated": False,
                "output_capture_complete": False,
                "execution_source": "osv_api_fallback",
                "findings": findings,
                "findings_count": len(findings),
                "reason": f"OSV API fallback failed after {start} of {len(dependencies)} exact dependencies: {type(exc).__name__}",
                "verified_for_this_report": False,
                "execution_observed_for_this_report": True,
                "current_run": True,
                "dependency_count": len(dependencies),
                "queried_dependency_count": start,
                "batch_count": batch_count,
                "coverage_complete": False,
                "scans_git_history": False,
            }
        results = payload.get("results") if isinstance(payload, dict) else []
        if not isinstance(results, list) or len(results) != len(batch):
            return {
                "tool": spec.name,
                "status": "failed",
                "category": spec.category,
                "returncode": 2,
                "returncode_valid": False,
                "timed_out": False,
                "output_truncated": False,
                "output_capture_complete": False,
                "execution_source": "osv_api_fallback",
                "findings": findings,
                "findings_count": len(findings),
                "reason": "OSV API fallback returned an incomplete querybatch response.",
                "verified_for_this_report": False,
                "execution_observed_for_this_report": True,
                "current_run": True,
                "dependency_count": len(dependencies),
                "queried_dependency_count": start,
                "batch_count": batch_count,
                "coverage_complete": False,
                "scans_git_history": False,
            }
        for dependency, result in zip(batch, results):
            vulns = result.get("vulns", []) if isinstance(result, dict) else []
            for vuln in vulns:
                if isinstance(vuln, dict):
                    item = dict(vuln)
                    item.setdefault("package", dependency["name"])
                    item.setdefault("version", dependency["version"])
                    item.setdefault("ecosystem", dependency["ecosystem"])
                    findings.append(item)
    return runners.redact_payload(
        {
            "tool": spec.name,
            "status": "completed",
            "category": spec.category,
            "returncode": 1 if findings else 0,
            "returncode_valid": True,
            "timed_out": False,
            "output_truncated": False,
            "output_capture_complete": True,
            "execution_source": "osv_api_fallback",
            "evidence_summary": f"OSV API fallback queried all {len(dependencies)} exact dependency versions in {batch_count} batch(es).",
            "findings": findings,
            "findings_count": len(findings),
            "stderr": "",
            "reason": "",
            "scans_git_history": False,
            "verified_for_this_report": True,
            "execution_observed_for_this_report": True,
            "current_run": True,
            "dependency_count": len(dependencies),
            "queried_dependency_count": len(dependencies),
            "batch_count": batch_count,
            "coverage_complete": True,
        }
    )


__all__ = ["_all_exact_dependencies", "_full_osv_api_fallback"]
