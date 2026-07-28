#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}
_EXCLUDED_PARTS = {
    ".git",
    ".next",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
_TOOL_CATEGORY = {
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "osv-scanner": "dependency",
    "bandit": "static",
    "semgrep": "static",
    "eslint": "static",
    "typescript": "static",
    "gitleaks": "secret",
    "trufflehog": "secret",
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _git(source: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_head(source: Path) -> str:
    return _git(source, "rev-parse", "HEAD").lower()


def _source_files(source: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in _CODE_SUFFIXES:
            continue
        relative = path.relative_to(source)
        if any(part in _EXCLUDED_PARTS for part in relative.parts):
            continue
        try:
            if path.stat().st_size > 2_000_000:
                continue
            files[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return files


def _workflow_runs(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    payload = _read_json(path)
    values = payload.get("workflow_runs") or payload.get("runs") or []
    return [dict(item) for item in values if isinstance(item, dict)]


def _pulls(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        values = value.get("pull_requests") or value.get("items") or []
        return [dict(item) for item in values if isinstance(item, dict)]
    return []


def _repository_path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/")
    lowered = raw.casefold()
    candidates: list[tuple[int, str]] = []
    for root in (".github/", "apps/", "config/", "docs/", "nico/", "scripts/", "tests/"):
        index = lowered.rfind(root.casefold())
        if index >= 0:
            candidates.append((index, raw[index:]))
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return raw.lstrip("./")


def _finding_path(item: dict[str, Any]) -> str:
    return _repository_path(
        item.get("file_path")
        or item.get("filename")
        or item.get("path")
        or item.get("filePath")
        or ""
    )


def _finding_line(item: dict[str, Any]) -> int | None:
    for key in ("line", "line_number", "start_line", "lineNumber"):
        try:
            value = int(item.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _is_test_only(item: dict[str, Any]) -> bool:
    path = _finding_path(item).casefold()
    return path.startswith("tests/") or "/tests/" in f"/{path}" or path.endswith("_test.py") or ".test." in path


def _ordered_unique(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = " ".join(str(value or "").split())
        key = token.casefold()
        if not token or key in seen:
            continue
        seen.add(key)
        output.append(token)
    return output


def _scanner_tools_complete(artifact: dict[str, Any], target_sha: str) -> None:
    if artifact.get("target_commit_sha") != target_sha:
        raise ValueError("Scanner artifact target SHA does not match the exact source SHA.")
    if artifact.get("scanner_evidence_ready") is not True:
        raise ValueError("Scanner artifact is not evidence-ready.")
    tools = artifact.get("tools") if isinstance(artifact.get("tools"), dict) else {}
    required = tuple(sorted((artifact.get("required_scanner_statuses") or {}).keys()))
    if not required:
        raise ValueError("Scanner artifact does not identify required tools.")
    incomplete = {
        tool: (tools.get(tool) or {}).get("status", "missing")
        for tool in required
        if not isinstance(tools.get(tool), dict)
        or (tools.get(tool) or {}).get("status") != "completed"
        or (tools.get(tool) or {}).get("verified_for_this_report") is not True
        or (tools.get(tool) or {}).get("output_capture_complete") is not True
        or (tools.get(tool) or {}).get("raw_artifact_capture_complete") is not True
        or (tools.get(tool) or {}).get("raw_artifact_retention_complete") is not True
        or not ((tools.get(tool) or {}).get("artifact_hash") or (tools.get(tool) or {}).get("raw_artifact_sha256"))
    }
    if incomplete:
        raise ValueError(f"Required scanner proof is incomplete: {incomplete}")


def _proof_complete(proof: dict[str, Any], target_sha: str) -> None:
    if proof.get("target_commit_sha") != target_sha:
        raise ValueError("Two-pass scanner proof target SHA does not match the source SHA.")
    if proof.get("two_consecutive_clean_runs") is not True:
        raise ValueError("Two-pass scanner proof is not complete and deterministic.")


def _finding_severity(item: dict[str, Any]) -> str:
    from nico.comprehensive_decision_grade_model_v5 import _severity

    return _severity(item)


def _finding_summary(scanner: dict[str, Any]) -> dict[str, Any]:
    by_category = {
        category: {
            "raw": 0,
            "material": 0,
            "review_required": 0,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
        }
        for category in ("dependency", "secret", "static")
    }
    tools = scanner.get("tools") if isinstance(scanner.get("tools"), dict) else {}
    for tool, payload in tools.items():
        if not isinstance(payload, dict):
            continue
        category = _TOOL_CATEGORY.get(str(tool), str(payload.get("category") or "unknown"))
        if category not in by_category:
            continue
        for item in payload.get("findings") or []:
            if not isinstance(item, dict):
                continue
            row = by_category[category]
            row["raw"] += 1
            if _is_test_only(item):
                row["excluded_test_only"] += 1
                continue
            severity = _finding_severity(item)
            verified_secret = category == "secret" and bool(item.get("Verified") or item.get("verified"))
            if severity in {"critical", "high"} or verified_secret:
                row["material"] += 1
            elif severity in {"medium", "unknown"}:
                row["review_required"] += 1
            else:
                row["approved_or_nonblocking"] += 1
    return {
        "raw_total": sum(item["raw"] for item in by_category.values()),
        "material_total": sum(item["material"] for item in by_category.values()),
        "review_required_total": sum(item["review_required"] for item in by_category.values()),
        "approved_or_nonblocking_total": sum(item["approved_or_nonblocking"] for item in by_category.values()),
        "excluded_test_only_total": sum(item["excluded_test_only"] for item in by_category.values()),
        "by_category": by_category,
        "test_only_findings_excluded_from_executive_risk": True,
        "complete_raw_artifacts_retained": True,
    }


def _safe_secret_finding(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("SourceMetadata") if isinstance(item.get("SourceMetadata"), dict) else {}
    data = source.get("Data") if isinstance(source.get("Data"), dict) else {}
    filesystem = data.get("Filesystem") if isinstance(data.get("Filesystem"), dict) else {}
    git = data.get("Git") if isinstance(data.get("Git"), dict) else {}
    path = _repository_path(
        item.get("File")
        or item.get("file")
        or filesystem.get("file")
        or git.get("file")
        or item.get("path")
        or ""
    )
    return {
        "title": "Potential secret candidate requires human triage; raw credential material is intentionally omitted.",
        "message": "Potential secret candidate requires human triage; raw credential material is intentionally omitted.",
        "rule_id": item.get("RuleID") or item.get("DetectorName") or item.get("DetectorType") or "secret-candidate",
        "file_path": path,
        "line": item.get("StartLine") or item.get("line"),
        "verified": bool(item.get("Verified") or item.get("verified")),
        "severity": item.get("severity") or "unknown",
        "secret_material_omitted": True,
    }


def _safe_finding(tool: str, item: dict[str, Any]) -> dict[str, Any]:
    if _TOOL_CATEGORY.get(tool) == "secret":
        return _safe_secret_finding(item)
    allowed = {
        "title",
        "message",
        "description",
        "issue_text",
        "issue_severity",
        "issue_confidence",
        "severity",
        "confidence",
        "level",
        "test_id",
        "check_id",
        "rule_id",
        "code",
        "id",
        "name",
        "package",
        "dependency",
        "installed_version",
        "fixed_version",
        "filename",
        "file_path",
        "path",
        "filePath",
        "line",
        "line_number",
        "start_line",
        "column",
    }
    output = {key: value for key, value in item.items() if key in allowed}
    extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
    if extra:
        output["extra"] = {
            key: value
            for key, value in extra.items()
            if key in {"message", "severity", "check_id", "rule_id", "lines"}
        }
    return output


def _finding_sort(item: dict[str, Any]) -> tuple[int, str, int, str]:
    order = {"critical": 0, "high": 1, "medium": 2, "unknown": 3, "low": 4}
    return (
        order.get(_finding_severity(item), 5),
        _finding_path(item),
        _finding_line(item) or 0,
        str(item.get("test_id") or item.get("check_id") or item.get("rule_id") or item.get("id") or ""),
    )


def _bounded_scanner_results(scanner: dict[str, Any], target_sha: str) -> list[dict[str, Any]]:
    tools = scanner.get("tools") if isinstance(scanner.get("tools"), dict) else {}
    output: list[dict[str, Any]] = []
    per_tool_limit = {
        "bandit": 6,
        "eslint": 4,
        "gitleaks": 3,
        "osv-scanner": 4,
        "trufflehog": 3,
    }
    for tool in sorted(tools):
        payload = tools.get(tool)
        if not isinstance(payload, dict):
            continue
        source_findings = [item for item in payload.get("findings") or [] if isinstance(item, dict)]
        candidates = [item for item in source_findings if not _is_test_only(item)]
        if tool == "bandit":
            candidates = [item for item in candidates if str(item.get("test_id") or "") != "B608"]
        selected = sorted(candidates, key=_finding_sort)[: per_tool_limit.get(tool, 2)]
        record = {
            key: deepcopy(value)
            for key, value in payload.items()
            if key not in {"findings", "_raw_artifact_blob"}
        }
        record.update(
            {
                "tool": tool,
                "target_commit_sha": target_sha,
                "run_id": scanner.get("run_id"),
                "finished_at": scanner.get("finished_at"),
                "current_run": True,
                "findings": [_safe_finding(tool, item) for item in selected],
                "findings_count": int(payload.get("findings_count") or len(source_findings)),
                "client_report_finding_sample_count": len(selected),
                "client_report_findings_are_bounded": len(selected) < len(source_findings),
                "complete_raw_finding_ledger_retained": True,
            }
        )
        output.append(record)
    return output


def _sql_review_records(scanner: dict[str, Any]) -> list[dict[str, Any]]:
    from nico.phase6_sql_dispositions_v1 import SQL_DISPOSITIONS

    bandit = ((scanner.get("tools") or {}).get("bandit") or {})
    output: list[dict[str, Any]] = []
    for item in bandit.get("findings") or []:
        if not isinstance(item, dict) or str(item.get("test_id") or "") != "B608":
            continue
        path = _finding_path(item)
        if path not in SQL_DISPOSITIONS:
            continue
        line = _finding_line(item)
        output.append(
            {
                "tool": "bandit",
                "rule_id": "B608",
                "priority": "P1",
                "category": "static",
                "title": "Possible SQL injection vector through string-based query construction.",
                "message": "Possible SQL injection vector through string-based query construction.",
                "file_path": path,
                "line": line,
                "fact": (
                    "Bandit B608 identified string-based SQL construction at the exact assessed source location. "
                    "Phase 6 performed a source-specific review instead of treating the analyzer message as verified exploitability."
                ),
                "evidence": (
                    f"tool=bandit; rule=B608; exact_commit_location={path}:{line or 0}; "
                    "complete_raw_artifact_retained=true"
                ),
                "confidence": "high",
                "acceptance_criteria": [
                    "The source-specific rationale remains valid for the exact assessed code.",
                    "The originating analyzer is rerun after any SQL construction change.",
                ],
                "human_review_required": True,
            }
        )
    return output


def _dependency_evidence(source: Path) -> dict[str, Any]:
    lockfiles = [
        path.relative_to(source).as_posix()
        for path in sorted(source.rglob("*"))
        if path.is_file()
        and path.name in {"package-lock.json", "poetry.lock", "Pipfile.lock", "pnpm-lock.yaml", "yarn.lock"}
        and not any(part in _EXCLUDED_PARTS for part in path.relative_to(source).parts)
    ]
    entries = 0
    requirements = source / "requirements.txt"
    if requirements.is_file():
        entries += sum(
            1
            for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    for path in source.rglob("package-lock.json"):
        relative = path.relative_to(source)
        if any(part in _EXCLUDED_PARTS for part in relative.parts):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        packages = payload.get("packages") if isinstance(payload, dict) else None
        dependencies = payload.get("dependencies") if isinstance(payload, dict) else None
        entries += max(0, len(packages or {}) - 1) if isinstance(packages, dict) else len(dependencies or {}) if isinstance(dependencies, dict) else 0
    return {
        "lockfile_paths": lockfiles,
        "dependency_entries": entries,
        "measurement": "requirements plus lockfile package records from the exact checkout",
    }


def _workflow_evidence(source: Path, runs: list[dict[str, Any]]) -> dict[str, Any]:
    workflow_files = [path for path in (source / ".github" / "workflows").glob("*.y*ml") if path.is_file()]
    completed = [item for item in runs if str(item.get("status") or "") == "completed"]
    successful = [item for item in completed if str(item.get("conclusion") or "") == "success"]
    non_success = [item for item in completed if str(item.get("conclusion") or "") != "success"]
    explicit_permissions = all(
        re.search(r"(?m)^permissions:\s*$", path.read_text(encoding="utf-8", errors="replace")) is not None
        for path in workflow_files
    ) if workflow_files else False
    return {
        "workflow_file_count": len(workflow_files),
        "workflow_run_count": len(runs),
        "successful_runs": len(successful),
        "non_success_runs": len(non_success),
        "jobs_observed": 0,
        "job_success_rate": round(len(successful) / len(completed), 4) if completed else None,
        "explicit_permissions_present": explicit_permissions,
        "active_or_queued_runs_excluded_from_non_success": True,
    }


def _repository_evidence(
    source: Path,
    files: dict[str, str],
    risk_scan: dict[str, Any],
    runs: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
) -> dict[str, Any]:
    source_paths = [path for path in files if not path.startswith("tests/")]
    test_paths = [path for path in files if path.startswith("tests/") or "/tests/" in f"/{path}"]
    merged_pulls = [item for item in pulls if item.get("merged_at")]
    commit_count = int(_git(source, "rev-list", "--count", "HEAD") or 0)
    return {
        "architecture_evidence": {
            "source_file_count": len(source_paths),
            "test_path_count": len(test_paths),
            "deployment_manifests": [
                path
                for path in ("Dockerfile", "railway.json", "render.yaml", "vercel.json")
                if (source / path).is_file()
            ],
        },
        "dependency_evidence": _dependency_evidence(source),
        "activity_evidence": {
            "commits_returned": commit_count,
            "pull_requests_returned": len(pulls),
            "merged_pull_requests": len(merged_pulls),
            "measurement": "exact Git history plus bounded GitHub pull-request metadata",
        },
        "workflow_evidence": _workflow_evidence(source, runs),
        "code_signal_evidence": {
            "risk_pattern_hits": len(risk_scan.get("risks") or []),
            "risk_pattern_samples": list(risk_scan.get("risks") or [])[:12],
            "potential_secret_pattern_hits": len(risk_scan.get("secrets") or []),
            "risk_scan_method": risk_scan.get("risk_scan_method"),
            "configuration_literals_treated_as_executable": risk_scan.get("configuration_literals_treated_as_executable"),
        },
        "unavailable_data_notes": [],
    }


def _build_assessment(
    *,
    repository: str,
    target_sha: str,
    run_id: str,
    source: Path,
    files: dict[str, str],
    scanner: dict[str, Any],
    complexity: dict[str, Any],
    risk_scan: dict[str, Any],
    workflow_runs: list[dict[str, Any]],
    pulls: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from nico.comprehensive_decision_grade_assessment_v5 import build_decision_grade_assessment

    finding_summary = _finding_summary(scanner)
    scanner_results = _bounded_scanner_results(scanner, target_sha)
    scan = {
        "status": "complete",
        "target_commit_sha": target_sha,
        "tools_run": sorted(scanner.get("required_scanner_statuses") or {}),
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "scanner_results": scanner_results,
        "finding_summary": finding_summary,
        "client_report_findings_are_bounded": True,
        "complete_raw_finding_ledger_retained": True,
        "unavailable_data_notes": [],
    }
    repo = _repository_evidence(source, files, risk_scan, workflow_runs, pulls)
    assessment = build_decision_grade_assessment(
        repository=repository,
        commit_sha=target_sha,
        run_id=run_id,
        repo=repo,
        complexity=complexity,
        scan=scan,
    )
    assessment["findings_register"] = [
        *(assessment.get("findings_register") or []),
        *_sql_review_records(scanner),
    ]
    assessment["scanner_execution_records"] = {
        item["tool"]: {
            key: item.get(key)
            for key in (
                "status",
                "target_commit_sha",
                "artifact_hash",
                "raw_artifact_sha256",
                "raw_artifact_retention_complete",
                "output_capture_complete",
                "verified_for_this_report",
                "findings_count",
            )
        }
        for item in scanner_results
    }
    assessment["scope_boundaries"] = [
        {
            "area": "Automated scanner detail",
            "boundary": (
                "Executive and detailed report registers contain a deterministic decision-relevant sample. "
                "Complete redacted raw scanner artifacts and hashes are retained separately for the exact SHA."
            ),
        },
        {
            "area": "Business and stakeholder context",
            "boundary": "No stakeholder interview or client financial input was supplied; no monetary outcome is claimed.",
        },
        {
            "area": "Production behavior",
            "boundary": "Repository, CI, and scanner evidence do not substitute for authorized live functional QA or human approval.",
        },
    ]
    assessment["assumption_register"] = [
        {
            "assumption_id": "A-01",
            "category": "identity",
            "description": "The checked-out Git commit is the immutable assessment target.",
            "source": "git rev-parse HEAD and two-pass scanner provenance",
            "confidence": "high",
            "sensitivity": "critical",
            "consequence_if_wrong": "All report facts would be invalid for the intended revision.",
        },
        {
            "assumption_id": "A-02",
            "category": "scope",
            "description": "Automated scanner results are bounded evidence, not proof of exploitability or absence of defects.",
            "source": "scanner execution contract",
            "confidence": "high",
            "sensitivity": "high",
            "consequence_if_wrong": "Findings could be overstated or understated without source review.",
        },
    ]
    assessment["how_to_use_report"] = [
        "Review concise executive risks first, then use canonical finding cards and source-reviewed dispositions for technical triage.",
        "Use the machine-readable JSON and CSV for exact identities, locations, mappings, and evidence fingerprints.",
        "Require an authorized human to accept or reject the exact immutable package before client delivery.",
    ]
    assessment["decision_postures"] = {
        "operate": {
            "status": "conditional",
            "conditions": ["Operate only inside the authorized assessed scope.", "Track unresolved material or review-required findings."],
        },
        "release": {
            "status": "conditional",
            "conditions": ["Assessed-commit required checks must be green.", "P0/P1 findings require disposition."],
        },
        "client_delivery": {
            "status": "blocked",
            "required_next_action": "Complete exact-package human review and approval.",
        },
    }
    assessment["delivery_status"] = "Human Review Required"
    assessment["report_scope"] = {
        "exact_sha": target_sha,
        "complete_scanner_status_count": len(scanner_results),
        "raw_scanner_finding_count": finding_summary["raw_total"],
        "client_report_finding_sample_count": sum(item["client_report_finding_sample_count"] for item in scanner_results),
        "test_only_findings_excluded_from_executive_risk": finding_summary["excluded_test_only_total"],
        "full_evidence_available_in_retained_artifacts": True,
    }
    return assessment, repo, scan


def _artifact_text(package: dict[str, Any], key: str) -> str:
    return str(package.get(key) or "")


def _filename_tokens(filename: str) -> dict[str, int]:
    upper = filename.upper()
    return {
        "FINAL-PENDING-APPROVAL": upper.count("FINAL-PENDING-APPROVAL"),
        "FINAL": upper.count("FINAL"),
        "DRAFT": upper.count("DRAFT"),
        "PENDING-APPROVAL": upper.count("PENDING-APPROVAL"),
    }


def _mapping_duplicates(findings: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    for item in findings:
        finding_id = str(item.get("finding_id") or item.get("id") or "unknown")
        for key in ("acceptance_criteria", "roadmap_mappings", "backlog_mappings", "related_locations"):
            values = [str(value) for value in item.get(key) or []]
            if len(values) != len({value.casefold() for value in values}):
                problems.append(f"{finding_id}:{key}")
    return problems


def _write_package(output: Path, stem: str, package: dict[str, Any]) -> dict[str, str]:
    markdown = _artifact_text(package, "markdown")
    html_text = _artifact_text(package, "html")
    pdf_bytes = base64.b64decode(package.get("pdf_base64") or "") if package.get("pdf_base64") else b""
    findings_csv = _artifact_text(package, "findings_csv")
    evidence_csv = _artifact_text(package, "evidence_ledger_csv")
    canonical = package.get("json") if isinstance(package.get("json"), dict) else {}
    json_text = json.dumps(canonical, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    artifacts = {
        f"{stem}.md": markdown.encode("utf-8"),
        f"{stem}.html": html_text.encode("utf-8"),
        f"{stem}.pdf": pdf_bytes,
        f"{stem}.json": json_text.encode("utf-8"),
        f"{stem}-findings.csv": findings_csv.encode("utf-8"),
        f"{stem}-evidence.csv": evidence_csv.encode("utf-8"),
    }
    hashes: dict[str, str] = {}
    for name, data in artifacts.items():
        (output / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the exact-SHA Phase 6 final Comprehensive verification package.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scanner-run", type=Path, required=True)
    parser.add_argument("--scanner-proof", type=Path, required=True)
    parser.add_argument("--workflow-runs", type=Path, required=True)
    parser.add_argument("--pulls", type=Path)
    parser.add_argument("--ci-truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", default="BoneManTGRM/NICO")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target_sha = _git_head(source)
    scanner = _read_json(args.scanner_run)
    proof = _read_json(args.scanner_proof)
    ci_truth = _read_json(args.ci_truth)
    _scanner_tools_complete(scanner, target_sha)
    _proof_complete(proof, target_sha)
    assessed_ci = ci_truth.get("assessed_commit") if isinstance(ci_truth.get("assessed_commit"), dict) else {}
    if assessed_ci.get("commit_sha") != target_sha or assessed_ci.get("all_required_checks_green") is not True:
        raise SystemExit("Assessed-commit required-check evidence is not green for the exact SHA.")

    files = _source_files(source)
    if not files:
        raise SystemExit("No eligible exact-SHA source files were found.")

    from nico.ci_history_classification_v1 import classify_workflow_history
    from nico.phase5_report_truth_v1 import scan_files_executable_only
    from nico.typescript_ast_complexity_v1 import _build_complexity

    risk_scan = scan_files_executable_only(files)
    complexity = _build_complexity(files)
    workflow_runs = _workflow_runs(args.workflow_runs)
    pulls = _pulls(args.pulls)
    default_health = ci_truth.get("current_default_branch") if isinstance(ci_truth.get("current_default_branch"), dict) else {}
    ci_summary = classify_workflow_history(
        workflow_runs,
        current_required_checks={"green": default_health.get("all_required_checks_green")},
    )
    ci_summary["current_branch_health"] = {
        "status": default_health.get("status") or "not_observed",
        "green": default_health.get("all_required_checks_green"),
        "commit_sha": default_health.get("commit_sha"),
        "branch": default_health.get("branch"),
        "observed_count": default_health.get("observed_count"),
        "required_count": default_health.get("required_count"),
    }

    run_id = f"phase6-{target_sha[:12]}"
    assessment, repo, scan = _build_assessment(
        repository=args.repository,
        target_sha=target_sha,
        run_id=run_id,
        source=source,
        files=files,
        scanner=scanner,
        complexity=complexity,
        risk_scan=risk_scan,
        workflow_runs=workflow_runs,
        pulls=pulls,
    )
    stage_results = {
        "immutable_repository_snapshot": {
            "status": "complete",
            "commit_sha": target_sha,
            "snapshot_commit_sha": target_sha,
            "summary": "The verification package used the exact full-history checkout.",
        },
        "repository_and_delivery_evidence": {
            "status": "complete",
            "commit_sha": target_sha,
            "repository_evidence": repo,
            "complexity_evidence": complexity,
            "summary": "Exact-checkout repository, dependency, workflow, activity, risk-pattern, and complexity evidence was measured.",
        },
        "dependency_security_static_analysis": {
            **deepcopy(scanner),
            "status": "complete",
            "commit_sha": target_sha,
            "summary": "Every required scanner completed with retained exact-SHA artifacts; findings remain independently reviewable.",
        },
        "deep_scanner_triage": {
            **deepcopy(scanner),
            "status": "complete",
            "commit_sha": target_sha,
            "summary": "The deterministic client report sample is backed by the complete redacted scanner ledger.",
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "commit_sha": target_sha,
            "assessment": assessment,
            "summary": "Technical score and evidence assurance were derived from the retained exact-SHA evidence model.",
        },
        "ci_cd_architecture_complexity_velocity": {
            "status": "complete",
            "commit_sha": target_sha,
            "workflow_evidence": {
                **repo["workflow_evidence"],
                "classified_history": ci_summary,
            },
            "ci_history_summary": ci_summary,
            "complexity_evidence": complexity,
            "summary": "Assessed-commit health, default-branch health, and bounded historical reliability are separate evidence records.",
        },
        "assessed_commit_required_checks": {
            **assessed_ci,
            "status_source": "phase6_exact_commit_workflow_matrix",
        },
        "current_default_branch_required_checks": {
            **default_health,
            "status_source": "phase6_default_branch_workflow_snapshot",
        },
    }

    # Importing the terminal bootstrap installs the complete final report stack,
    # including Phase 6 canonicalization after the existing English/Spanish finality layer.
    from nico.api import terminal_authority_bootstrap as terminal_bootstrap
    from nico import comprehensive_decision_grade_report_v5 as report
    from nico.phase6_canonical_truth_v2 import compare_language_factual_parity
    from nico.phase6_sql_dispositions_v1 import SQL_DISPOSITIONS

    assert terminal_bootstrap.PHASE6_FINAL_REMEDIATION["status"] == "installed"
    assert terminal_bootstrap.PHASE6_CANONICAL_TRUTH["status"] == "installed"

    identity = {
        "run_id": run_id,
        "repository": args.repository,
        "commit_sha": target_sha,
        "evidence_ledger_id": f"phase6-ledger-{target_sha[:16]}",
        "customer_id": "internal",
        "project_id": "nico-phase6-final-verification",
        "branch": "phase-6/report-deduplication-security-remediation",
        "nico_version": "phase6",
        "assessment_depth": "comprehensive",
    }
    english = report.build_comprehensive_report_package(
        identity={**identity, "report_language": "en", "locale": "en"},
        stage_results=deepcopy(stage_results),
    )
    spanish = report.build_comprehensive_report_package(
        identity={**identity, "report_language": "es-MX", "locale": "es-MX"},
        stage_results=deepcopy(stage_results),
    )
    english_package = english.get("report_package") if isinstance(english.get("report_package"), dict) else {}
    spanish_package = spanish.get("report_package") if isinstance(spanish.get("report_package"), dict) else {}
    english_assessment = english.get("assessment") if isinstance(english.get("assessment"), dict) else {}
    spanish_assessment = spanish.get("assessment") if isinstance(spanish.get("assessment"), dict) else {}
    english_json = english_package.get("json") if isinstance(english_package.get("json"), dict) else {}
    spanish_json = spanish_package.get("json") if isinstance(spanish_package.get("json"), dict) else {}
    parity = compare_language_factual_parity(
        english_assessment,
        spanish_assessment,
        english_identity=english_json.get("identity") if isinstance(english_json.get("identity"), dict) else identity,
        spanish_identity=spanish_json.get("identity") if isinstance(spanish_json.get("identity"), dict) else identity,
    )

    forbidden = (
        "Verified Change Since Phase 5 Baseline",
        "Phase 5 Verified Before/After Delta",
        "Why this is broader than Express",
    )
    english_surfaces = "\n".join(
        str(english_package.get(key) or "") for key in ("markdown", "html")
    )
    spanish_surfaces = "\n".join(
        str(spanish_package.get(key) or "") for key in ("markdown", "html")
    )
    forbidden_found = sorted({marker for marker in forbidden if marker in english_surfaces or marker in spanish_surfaces})
    health = english_assessment.get("evidence_health_summary") if isinstance(english_assessment.get("evidence_health_summary"), dict) else {}
    completed = sorted(str(item) for item in health.get("completed_scanners") or [])
    incomplete = [item for item in health.get("incomplete_scanners") or [] if isinstance(item, dict)]
    required_tools = sorted(scanner.get("required_scanner_statuses") or {})
    findings = [item for item in english_assessment.get("decision_grade_findings_register") or english_assessment.get("findings_register") or [] if isinstance(item, dict)]
    dispositions = [item for item in english_assessment.get("finding_dispositions") or [] if isinstance(item, dict)]
    disposition_paths = sorted({str(item.get("canonical_path") or "") for item in dispositions})
    integrity = english_assessment.get("finding_integrity") if isinstance(english_assessment.get("finding_integrity"), dict) else {}
    cross_format = english_package.get("canonical_truth_manifest") if isinstance(english_package.get("canonical_truth_manifest"), dict) else {}
    ci_health = english_assessment.get("ci_health") if isinstance(english_assessment.get("ci_health"), dict) else {}
    mapping_duplicates = _mapping_duplicates(findings)
    english_filename = str(english_package.get("pdf_filename") or "")
    spanish_filename = str(spanish_package.get("pdf_filename") or "")

    failures: list[str] = []
    if sorted(completed) != required_tools:
        failures.append(f"completed_scanners_mismatch:{completed}")
    if incomplete:
        failures.append(f"unexpected_incomplete_scanners:{incomplete}")
    if forbidden_found:
        failures.append(f"forbidden_customer_sections:{forbidden_found}")
    if any(key.startswith("phase5_") for key in english_package):
        failures.append("phase5_package_exports_remain")
    if integrity.get("stable_ids_unique") is not True:
        failures.append("finding_ids_not_unique")
    if integrity.get("canonical_locations_present") is not True:
        failures.append("canonical_locations_missing")
    if mapping_duplicates:
        failures.append(f"duplicate_mappings:{mapping_duplicates}")
    if sorted(disposition_paths) != sorted(SQL_DISPOSITIONS):
        failures.append(f"sql_disposition_coverage_mismatch:{disposition_paths}")
    if cross_format.get("status") != "valid":
        failures.append(f"cross_format_truth_invalid:{cross_format.get('violations')}")
    if parity.get("equivalent") is not True:
        failures.append("english_spanish_factual_parity_failed")
    assessed_report_health = ci_health.get("assessed_commit") if isinstance(ci_health.get("assessed_commit"), dict) else {}
    if assessed_report_health.get("green") is not True or assessed_report_health.get("commit_sha") != target_sha:
        failures.append(f"assessed_commit_health_not_green:{assessed_report_health}")
    if not english_package.get("pdf_base64") or not spanish_package.get("pdf_base64"):
        failures.append("pdf_artifact_missing")
    if english_filename.upper().count("FINAL-PENDING-APPROVAL") != 1:
        failures.append(f"english_filename_not_idempotent:{english_filename}")
    if "FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL" in english_filename.upper():
        failures.append("repeated_terminal_suffix")
    if english.get("client_delivery_allowed") is True or spanish.get("client_delivery_allowed") is True:
        failures.append("client_delivery_incorrectly_allowed")
    if failures:
        raise SystemExit("Phase 6 verification failed: " + " | ".join(failures))

    stem = f"nico-comprehensive-phase6-{target_sha[:12]}"
    english_hashes = _write_package(output, stem, english_package)
    spanish_hashes = _write_package(output, f"{stem}-es-MX", spanish_package)
    canonical_evidence = {
        "schema": "nico.phase6.verification_evidence.v1",
        "repository": args.repository,
        "exact_commit_sha": target_sha,
        "scanner_proof": proof,
        "scanner_artifact_hash": scanner.get("artifact_hash"),
        "required_scanner_statuses": scanner.get("required_scanner_statuses"),
        "scanner_finding_summary": scan["finding_summary"],
        "ci_truth": ci_truth,
        "ci_history_classification": ci_summary,
        "complexity": complexity,
        "risk_scan": risk_scan,
        "report_scope": english_assessment.get("report_scope"),
        "finding_integrity": integrity,
        "sql_source_review_coverage": english_assessment.get("sql_source_review_coverage"),
        "cross_format_truth": cross_format,
        "language_factual_parity": parity,
    }
    evidence_text = json.dumps(canonical_evidence, indent=2, sort_keys=True, ensure_ascii=False, default=str)
    evidence_name = f"{stem}-verification-evidence.json"
    (output / evidence_name).write_text(evidence_text, encoding="utf-8")
    summary = {
        "schema": "nico.phase6.final_verification_package.v1",
        "status": "verified",
        "repository": args.repository,
        "exact_commit_sha": target_sha,
        "two_consecutive_scanner_runs": proof.get("two_consecutive_clean_runs") is True,
        "required_scanner_statuses": scanner.get("required_scanner_statuses"),
        "report_completed_scanners": completed,
        "report_incomplete_scanners": incomplete,
        "technical_score": ((english_assessment.get("maturity_signal") or {}).get("presented_score")),
        "evidence_adjusted_score": english_assessment.get("canonical_evidence_adjusted_score", english_assessment.get("evidence_adjusted_score")),
        "finding_count": len(findings),
        "finding_ids_unique": integrity.get("stable_ids_unique"),
        "canonical_locations_present": integrity.get("canonical_locations_present"),
        "source_reviewed_sql_disposition_count": len(dispositions),
        "source_reviewed_sql_paths": disposition_paths,
        "duplicate_mapping_records": mapping_duplicates,
        "assessed_commit_ci": assessed_report_health,
        "current_default_branch_ci": ci_health.get("current_default_branch"),
        "bounded_historical_reliability": ci_health.get("bounded_historical_reliability"),
        "actionable_complexity": english_assessment.get("actionable_complexity"),
        "cross_format_truth_status": cross_format.get("status"),
        "cross_format_truth_sha256": cross_format.get("projection_sha256"),
        "english_spanish_factual_parity": parity,
        "english_pdf_filename": english_filename,
        "spanish_pdf_filename": spanish_filename,
        "english_filename_token_counts": _filename_tokens(english_filename),
        "spanish_filename_token_counts": _filename_tokens(spanish_filename),
        "english_pdf_page_count": english_package.get("pdf_page_count"),
        "spanish_pdf_page_count": spanish_package.get("pdf_page_count"),
        "phase5_customer_section_present": False,
        "express_comparison_section_present": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "report_status": english.get("status"),
        "report_reason": english.get("reason"),
        "artifacts": {
            **english_hashes,
            **spanish_hashes,
            evidence_name: hashlib.sha256(evidence_text.encode("utf-8")).hexdigest(),
        },
    }
    (output / "phase6-final-verification-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
