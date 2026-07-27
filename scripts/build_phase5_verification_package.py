#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _git_head(source: Path) -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip().lower()


def _source_files(source: Path) -> dict[str, str]:
    excluded_parts = {
        ".git", ".next", ".venv", "venv", "node_modules", "dist", "build",
        "coverage", "__pycache__", ".pytest_cache", ".mypy_cache",
    }
    allowed = {".py", ".js", ".jsx", ".ts", ".tsx"}
    files: dict[str, str] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.casefold() not in allowed:
            continue
        relative = path.relative_to(source)
        if any(part in excluded_parts for part in relative.parts):
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
    runs = payload.get("workflow_runs") or payload.get("runs") or []
    return [dict(item) for item in runs if isinstance(item, dict)]


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
    }
    if incomplete:
        raise ValueError(f"Required scanner proof is incomplete: {incomplete}")


def _proof_complete(proof: dict[str, Any], target_sha: str) -> None:
    if proof.get("target_commit_sha") != target_sha:
        raise ValueError("Two-pass scanner proof target SHA does not match the exact source SHA.")
    if proof.get("two_consecutive_clean_runs") is not True:
        raise ValueError("Two-pass scanner proof is not complete and equivalent.")


def _assessment(*, tls_open: bool, complexity: dict[str, Any]) -> dict[str, Any]:
    tracked = complexity.get("tracked_function_metrics") if isinstance(complexity.get("tracked_function_metrics"), dict) else {}
    architecture_findings = []
    for name, item in sorted(tracked.items()):
        if not isinstance(item, dict):
            continue
        architecture_findings.append(
            {
                "finding_id": f"phase5-current-complexity-{name}",
                "category": "architecture",
                "title": f"Current complexity measurement: {name}",
                "priority": "P2" if int(item.get("cyclomatic_complexity") or 0) > 30 else "P3",
                "location": f"{item.get('path') or 'unknown'}:{item.get('line') or 0}",
                "evidence": (
                    f"cyclomatic_complexity={int(item.get('cyclomatic_complexity') or 0)}; "
                    f"cognitive_complexity={item.get('cognitive_complexity')}; "
                    f"loc={int(item.get('loc') or 0)}; method={item.get('method') or 'unknown'}"
                ),
                "fact": "Exact-SHA analyzer measurement retained for Phase 5 comparison.",
                "recommendation": "Continue reducing any function above the repository threshold without changing behavior.",
                "residual_risk": "Complexity may still remain in untracked functions or parser-limited files.",
                "human_review_required": True,
            }
        )
    findings: list[dict[str, Any]] = [
        {"finding_id": "phase5-baseline-bandit", "category": "evidence", "title": "bandit evidence failed"},
        {"finding_id": "phase5-baseline-eslint", "category": "evidence", "title": "eslint evidence failed"},
        {"finding_id": "phase5-baseline-gitleaks", "category": "evidence", "title": "gitleaks evidence partial"},
        {"finding_id": "phase5-baseline-osv", "category": "evidence", "title": "osv-scanner evidence partial"},
        *architecture_findings,
    ]
    if tls_open:
        findings.append(
            {
                "finding_id": "phase5-current-tls-verify-disabled",
                "category": "security",
                "title": "tls_verify_disabled executable finding remains open",
                "priority": "P1",
                "evidence": "An executable exact-SHA risk pattern matched TLS verification disablement.",
                "human_review_required": True,
            }
        )
    return {
        "maturity_signal": {"score": 85, "presented_score": 85},
        "canonical_evidence_adjusted_score": 83,
        "sections": [
            {
                "id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 92,
                "evidence": [], "findings": ["osv-scanner evidence was partial at the Phase 5 baseline"],
                "unavailable": ["osv-scanner exact-SHA evidence unavailable at baseline"],
            },
            {
                "id": "secrets_review", "label": "Secrets Exposure Review", "score": 93,
                "evidence": [], "findings": ["gitleaks evidence was partial at the Phase 5 baseline"],
                "unavailable": ["gitleaks exact-SHA evidence unavailable at baseline"],
            },
            {
                "id": "static_analysis", "label": "Static Analysis", "score": 79,
                "evidence": [], "findings": ["Failed static tools: bandit, eslint"],
                "unavailable": ["bandit evidence unavailable", "eslint evidence unavailable"],
            },
            {
                "id": "ci_cd", "label": "CI/CD Analysis", "score": 78,
                "evidence": [], "findings": ["Historical workflow runs were reported only as raw non-success outcomes."],
                "unavailable": [],
            },
            {
                "id": "architecture", "label": "Architecture and Complexity", "score": 82,
                "evidence": ["Exact-SHA complexity analyzer output retained."],
                "findings": [], "unavailable": list(complexity.get("unavailable_data_notes") or []),
            },
        ],
        "findings_register": findings,
        "decision_postures": {},
        "how_to_use_report": [
            "Use the verified delta table to distinguish repaired evidence boundaries from unchanged engineering risk.",
            "Require human review before any client delivery decision.",
        ],
        "scope_boundaries": [
            "This package verifies the exact repository SHA and retained automated evidence only.",
            "It does not substitute for stakeholder discovery, live functional QA, or production authorization.",
        ],
        "assumption_register": [
            {
                "assumption": "The checked-out Git commit is the immutable assessment target.",
                "validation": "git rev-parse HEAD equals the scanner proof target SHA.",
                "impact_if_wrong": "All reported deltas would be invalid.",
            }
        ],
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an exact-SHA Phase 5 before/after verification package.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--scanner-run", type=Path, required=True)
    parser.add_argument("--scanner-proof", type=Path, required=True)
    parser.add_argument("--workflow-runs", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", default="BoneManTGRM/NICO")
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target_sha = _git_head(source)
    scanner = _read_json(args.scanner_run)
    proof = _read_json(args.scanner_proof)
    _scanner_tools_complete(scanner, target_sha)
    _proof_complete(proof, target_sha)

    files = _source_files(source)
    if not files:
        raise SystemExit("No eligible exact-SHA source files were found.")

    from nico.ci_history_classification_v1 import classify_workflow_history
    from nico.phase5_report_truth_v1 import scan_files_executable_only
    from nico.phase5_report_truth_v2 import install_phase5_report_truth_v2
    from nico.phase5_visible_outcome_appendix_v1 import install_phase5_visible_outcome_appendix_v1
    from nico.typescript_ast_complexity_v1 import _build_complexity

    risk_scan = scan_files_executable_only(files)
    tls_open = any("tls_verify_disabled" in str(item).casefold() for item in risk_scan.get("risks") or [])
    complexity = _build_complexity(files)
    tracked = complexity.get("tracked_function_metrics") if isinstance(complexity.get("tracked_function_metrics"), dict) else {}
    if "_build_complexity" not in tracked:
        raise SystemExit("Exact-SHA tracked complexity metric for _build_complexity was not produced.")

    runs = _workflow_runs(args.workflow_runs)
    ci_summary = classify_workflow_history(runs, current_required_checks={})
    assessment = _assessment(tls_open=tls_open, complexity=complexity)
    stage_results = {
        "evidence_reconciliation_and_scoring": {"commit_sha": target_sha, "assessment": assessment},
        "deep_scanner_triage": scanner,
        "ci_cd_architecture_complexity_velocity": {
            "commit_sha": target_sha,
            "workflow_evidence": {"classified_history": ci_summary},
            "complexity_evidence": complexity,
        },
    }

    install_phase5_report_truth_v2()
    install_phase5_visible_outcome_appendix_v1()
    from nico import comprehensive_decision_grade_report_v5 as report

    result = report.build_comprehensive_report_package(
        identity={
            "run_id": f"phase5-{target_sha[:12]}",
            "repository": args.repository,
            "commit_sha": target_sha,
            "evidence_ledger_id": f"phase5-ledger-{target_sha[:16]}",
            "customer_id": "internal",
            "project_id": "nico-phase5",
            "branch": "phase-5/report-truth-outcomes",
            "nico_version": "phase5",
        },
        stage_results=stage_results,
    )
    package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
    outcomes = package.get("phase5_verified_outcomes") if isinstance(package.get("phase5_verified_outcomes"), dict) else {}
    markdown = str(package.get("markdown") or "")
    html_text = str(package.get("html") or "")
    pdf_bytes = base64.b64decode(package.get("pdf_base64") or "") if package.get("pdf_base64") else b""
    csv_text = str(package.get("phase5_verified_outcomes_csv") or "")

    required_markers = (
        "Verified Change Since Phase 5 Baseline",
        "Phase 5 Verified Before/After Delta",
        "bandit",
        "eslint",
        "gitleaks",
        "osv-scanner",
        "Workflow outcome classes:",
        "_build_complexity",
    )
    missing_markers = [marker for marker in required_markers if marker not in markdown]
    if missing_markers:
        raise SystemExit(f"Generated report is missing visible Phase 5 markers: {missing_markers}")
    if outcomes.get("current_commit_sha") != target_sha:
        raise SystemExit("Generated outcome payload is not bound to the exact source SHA.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise SystemExit(f"PDF generation failed: {package.get('pdf_error') or result.get('reason')}")
    if not csv_text.strip():
        raise SystemExit("Phase 5 outcome CSV was not generated.")

    stem = f"nico-phase5-verification-{target_sha[:12]}"
    (output / f"{stem}.md").write_text(markdown, encoding="utf-8")
    (output / f"{stem}.html").write_text(html_text, encoding="utf-8")
    (output / f"{stem}.pdf").write_bytes(pdf_bytes)
    (output / f"{stem}.csv").write_text(csv_text, encoding="utf-8")
    canonical = {
        "exact_commit_sha": target_sha,
        "repository": args.repository,
        "scanner_proof": proof,
        "scanner_artifact_hash": scanner.get("artifact_hash"),
        "scanner_statuses": scanner.get("required_scanner_statuses"),
        "ci_history_classification": ci_summary,
        "complexity": complexity,
        "risk_scan": risk_scan,
        "report_result": result,
    }
    json_text = json.dumps(canonical, indent=2, sort_keys=True, default=str)
    (output / f"{stem}.json").write_text(json_text, encoding="utf-8")
    summary = {
        "schema": "nico.phase5.verification_package.v1",
        "status": "verified",
        "repository": args.repository,
        "exact_commit_sha": target_sha,
        "two_consecutive_scanner_runs": proof.get("two_consecutive_clean_runs") is True,
        "required_scanner_statuses": scanner.get("required_scanner_statuses"),
        "tls_verify_disabled_finding_open": outcomes.get("tls_verify_disabled_finding_open"),
        "complexity_changes": outcomes.get("complexity_changes"),
        "scanner_status_changes": outcomes.get("scanner_status_changes"),
        "ci_history_classification_visible": outcomes.get("ci_history_classification_visible"),
        "report_status": result.get("status"),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "artifacts": {
            f"{stem}.md": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            f"{stem}.html": hashlib.sha256(html_text.encode("utf-8")).hexdigest(),
            f"{stem}.pdf": hashlib.sha256(pdf_bytes).hexdigest(),
            f"{stem}.csv": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
            f"{stem}.json": hashlib.sha256(json_text.encode("utf-8")).hexdigest(),
        },
    }
    (output / "phase5-verification-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
