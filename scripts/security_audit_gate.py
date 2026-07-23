from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VERSION = "nico.security_audit_gate.v2"
SEMGREP_BLOCKING_RULES = {
    "yaml.github-actions.security.run-shell-injection.run-shell-injection",
}
REQUIRED_TOOLS = {
    "pip-audit",
    "npm-audit",
    "bandit",
    "semgrep",
    "osv-scanner",
    "gitleaks",
    "trufflehog",
    "typescript",
    "credential-scan",
}


def _read_json(root: Path, name: str) -> tuple[Any, str | None]:
    path = root / name
    if not path.is_file() or path.stat().st_size == 0:
        return None, "artifact_missing_or_empty"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="strict")), None
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, f"artifact_invalid:{type(exc).__name__}"


def _read_json_lines(root: Path, name: str) -> tuple[list[dict[str, Any]] | None, str | None]:
    path = root / name
    if not path.is_file():
        return None, "artifact_missing"
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return None, f"artifact_invalid:{type(exc).__name__}"
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            return None, f"invalid_json_line:{line_number}"
        if not isinstance(item, dict):
            return None, f"unexpected_json_line_shape:{line_number}"
        findings.append(item)
    return findings, None


def _digest(root: Path, name: str) -> str | None:
    path = root / name
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _record(root: Path, artifact: str, status: str, count: int, **extra: Any) -> dict[str, Any]:
    return {
        "status": status,
        "finding_count": max(0, int(count)),
        "artifact": artifact,
        "artifact_hash": _digest(root, artifact),
        **extra,
    }


def _pip_audit(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "pip-audit.json")
    if error or not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
        return _record(root, "pip-audit.json", "unavailable", 0, reason=error or "unexpected_json_shape")
    vulnerabilities = sum(
        len(item.get("vulns") or []) for item in data["dependencies"] if isinstance(item, dict)
    )
    return _record(root, "pip-audit.json", "completed", vulnerabilities)


def _npm_audit(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "npm-audit.json")
    metadata = data.get("metadata") if isinstance(data, dict) else None
    counts = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if error or not isinstance(counts, dict):
        return _record(root, "npm-audit.json", "unavailable", 0, reason=error or "unexpected_json_shape")
    normalized = {
        level: int(counts.get(level) or 0)
        for level in ("info", "low", "moderate", "high", "critical", "total")
    }
    return _record(
        root,
        "npm-audit.json",
        "completed",
        normalized["total"],
        severity_counts=normalized,
    )


def _bandit(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "bandit.json")
    results = data.get("results") if isinstance(data, dict) else None
    triage, triage_error = _read_json(root, "bandit-triage.json")
    if error or not isinstance(results, list) or triage_error or not isinstance(triage, dict):
        return _record(
            root,
            "bandit.json",
            "unavailable",
            0,
            reason=error or triage_error or "unexpected_json_shape",
        )
    return _record(
        root,
        "bandit.json",
        "completed",
        len(results),
        blocking=int(triage.get("blocking") or 0),
        needs_review=int(triage.get("needs_review") or 0),
        candidate_false_positive=int(triage.get("candidate_false_positive") or 0),
        triage_artifact_hash=_digest(root, "bandit-triage.json"),
    )


def _semgrep(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "semgrep.json")
    results = data.get("results") if isinstance(data, dict) else None
    errors = data.get("errors") if isinstance(data, dict) else None
    if error or not isinstance(results, list) or not isinstance(errors, list):
        return _record(root, "semgrep.json", "unavailable", 0, reason=error or "unexpected_json_shape")
    fatal_errors = [
        item
        for item in errors
        if isinstance(item, dict)
        and str(item.get("level") or "").lower() in {"error", "fatal"}
    ]
    blocking_items: list[dict[str, str]] = []
    review_items: list[dict[str, str]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        check_id = str(result.get("check_id") or "unknown")
        path = str(result.get("path") or "")
        evidence = {"check_id": check_id, "path": path}
        if check_id in SEMGREP_BLOCKING_RULES:
            blocking_items.append(evidence)
        else:
            review_items.append(evidence)
    status = "completed" if not fatal_errors else "failed"
    return _record(
        root,
        "semgrep.json",
        status,
        len(results),
        scanner_error_count=len(fatal_errors),
        blocking=len(blocking_items),
        needs_review=len(review_items),
        blocking_items=blocking_items[:50],
    )


def _osv(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "osv-scanner.json")
    if error or not isinstance(data, dict) or not isinstance(data.get("results"), list):
        reason = data.get("reason") if isinstance(data, dict) else None
        return _record(
            root,
            "osv-scanner.json",
            "unavailable",
            0,
            reason=reason or error or "unexpected_json_shape",
        )
    count = 0
    for result in data["results"]:
        if not isinstance(result, dict):
            continue
        for package in result.get("packages") or []:
            if isinstance(package, dict):
                count += len(package.get("vulnerabilities") or [])
    return _record(
        root,
        "osv-scanner.json",
        "completed",
        count,
        disposition="supplemental_review_required" if count else "completed_clean",
    )


def _summary_tool(root: Path, summary_name: str) -> dict[str, Any]:
    data, error = _read_json(root, summary_name)
    if error or not isinstance(data, dict):
        return _record(root, summary_name, "unavailable", 0, reason=error or "unexpected_json_shape")
    return _record(
        root,
        summary_name,
        str(data.get("status") or "unavailable"),
        int(data.get("finding_count") or 0),
    )


def _gitleaks(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "gitleaks.json")
    summary, summary_error = _read_json(root, "gitleaks-summary.json")
    if (
        error
        or not isinstance(data, list)
        or summary_error
        or not isinstance(summary, dict)
        or str(summary.get("status") or "") != "completed"
    ):
        return _record(
            root,
            "gitleaks.json",
            "unavailable",
            0,
            reason=error or summary_error or "unexpected_json_shape",
        )

    blocking = 0
    approved_test_placeholders = 0
    triage: list[dict[str, Any]] = []
    for finding in data:
        if not isinstance(finding, dict):
            blocking += 1
            continue
        path = str(finding.get("File") or "")
        rule = str(finding.get("RuleID") or "")
        secret = str(finding.get("Secret") or "")
        approved = (
            path.startswith("tests/")
            and rule == "generic-api-key"
            and secret == "REDACTED"
        )
        disposition = "approved_test_placeholder" if approved else "blocking"
        if approved:
            approved_test_placeholders += 1
        else:
            blocking += 1
        triage.append(
            {
                "fingerprint": str(finding.get("Fingerprint") or ""),
                "file": path,
                "line": finding.get("StartLine"),
                "rule_id": rule,
                "disposition": disposition,
            }
        )
    return _record(
        root,
        "gitleaks.json",
        "completed",
        len(data),
        blocking=blocking,
        needs_review=0,
        approved_test_placeholders=approved_test_placeholders,
        triage=triage[:200],
        summary_artifact_hash=_digest(root, "gitleaks-summary.json"),
    )


def _trufflehog_source_path(finding: dict[str, Any]) -> str:
    metadata = finding.get("SourceMetadata")
    data = metadata.get("Data") if isinstance(metadata, dict) else None
    git = data.get("Git") if isinstance(data, dict) else None
    return str(git.get("file") or "") if isinstance(git, dict) else ""


def _trufflehog(root: Path) -> dict[str, Any]:
    findings, error = _read_json_lines(root, "trufflehog.json")
    summary, summary_error = _read_json(root, "trufflehog-summary.json")
    if (
        error
        or findings is None
        or summary_error
        or not isinstance(summary, dict)
        or str(summary.get("status") or "") != "completed"
    ):
        return _record(
            root,
            "trufflehog.json",
            "unavailable",
            0,
            reason=error or summary_error or "unexpected_json_shape",
        )

    blocking = 0
    needs_review = 0
    approved_test_placeholders = 0
    triage: list[dict[str, Any]] = []
    for finding in findings:
        path = _trufflehog_source_path(finding)
        verified = finding.get("Verified") is True
        fixture_path = path.startswith("tests/") or path == ".env.example"
        if verified:
            disposition = "blocking_verified_secret"
            blocking += 1
        elif fixture_path:
            disposition = "approved_unverified_test_placeholder"
            approved_test_placeholders += 1
        else:
            disposition = "blocking_unverified_non_fixture"
            blocking += 1
        triage.append(
            {
                "file": path,
                "detector": str(finding.get("DetectorName") or "unknown"),
                "verified": verified,
                "disposition": disposition,
            }
        )
    return _record(
        root,
        "trufflehog.json",
        "completed",
        len(findings),
        blocking=blocking,
        needs_review=needs_review,
        approved_test_placeholders=approved_test_placeholders,
        triage=triage[:200],
        summary_artifact_hash=_digest(root, "trufflehog-summary.json"),
    )


def _eslint(root: Path) -> dict[str, Any]:
    summary, error = _read_json(root, "eslint-summary.json")
    if error or not isinstance(summary, dict):
        return _record(root, "eslint-summary.json", "unavailable", 0, reason=error or "unexpected_json_shape")
    return _record(
        root,
        "eslint-summary.json",
        str(summary.get("status") or "unavailable"),
        int(summary.get("finding_count") or 0),
        error_count=int(summary.get("error_count") or 0),
        warning_count=int(summary.get("warning_count") or 0),
        configured=bool(summary.get("configured")),
    )


def _credential_scan(root: Path) -> dict[str, Any]:
    data, error = _read_json(root, "credential-scan.json")
    findings = data.get("findings") if isinstance(data, dict) else None
    if error or not isinstance(findings, list):
        return _record(root, "credential-scan.json", "unavailable", 0, reason=error or "unexpected_json_shape")
    return _record(root, "credential-scan.json", "completed", len(findings))


def evaluate_gate(tools: dict[str, dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for name in sorted(REQUIRED_TOOLS):
        status = str((tools.get(name) or {}).get("status") or "unavailable")
        if status not in {"completed", "completed_clean"}:
            blockers.append(f"required scanner {name} status is {status}")

    pip_findings = int((tools.get("pip-audit") or {}).get("finding_count") or 0)
    npm_findings = int((tools.get("npm-audit") or {}).get("finding_count") or 0)
    if pip_findings:
        blockers.append(f"pip-audit reported {pip_findings} known vulnerabilities")
    if npm_findings:
        blockers.append(f"npm audit reported {npm_findings} known production vulnerabilities")

    credential_findings = int((tools.get("credential-scan") or {}).get("finding_count") or 0)
    if credential_findings:
        blockers.append(f"credential-scan reported {credential_findings} high-confidence secrets")

    for name in ("gitleaks", "trufflehog"):
        count = int((tools.get(name) or {}).get("blocking") or 0)
        if count:
            blockers.append(f"{name} reported {count} unapproved potential secrets")

    bandit_blocking = int((tools.get("bandit") or {}).get("blocking") or 0)
    if bandit_blocking:
        blockers.append(f"Bandit reported {bandit_blocking} high/critical findings")

    semgrep_blocking = int((tools.get("semgrep") or {}).get("blocking") or 0)
    if semgrep_blocking:
        blockers.append(f"Semgrep reported {semgrep_blocking} high-confidence blocking findings")

    typescript_findings = int((tools.get("typescript") or {}).get("finding_count") or 0)
    if typescript_findings:
        blockers.append(f"TypeScript reported {typescript_findings} errors")

    eslint = tools.get("eslint") or {}
    if eslint.get("configured") and int(eslint.get("error_count") or 0):
        blockers.append(f"ESLint reported {int(eslint.get('error_count') or 0)} errors")
    return blockers


def evaluate_review_required(tools: dict[str, dict[str, Any]]) -> list[str]:
    review: list[str] = []
    for name in ("bandit", "semgrep", "osv-scanner", "gitleaks", "trufflehog"):
        tool = tools.get(name) or {}
        count = int(tool.get("needs_review") or 0)
        if name == "osv-scanner":
            count = int(tool.get("finding_count") or 0)
        if count:
            review.append(f"{name} retained {count} non-blocking findings for human review")
    for name in ("bandit", "gitleaks", "trufflehog"):
        tool = tools.get(name) or {}
        candidates = int(
            tool.get("candidate_false_positive")
            or tool.get("approved_test_placeholders")
            or 0
        )
        if candidates:
            review.append(f"{name} retained {candidates} triaged candidates with evidence")
    return review


def build_manifest(root: Path, *, repository: str = "", run_id: str = "") -> dict[str, Any]:
    tools = {
        "pip-audit": _pip_audit(root),
        "npm-audit": _npm_audit(root),
        "bandit": _bandit(root),
        "semgrep": _semgrep(root),
        "osv-scanner": _osv(root),
        "gitleaks": _gitleaks(root),
        "trufflehog": _trufflehog(root),
        "typescript": _summary_tool(root, "typescript-summary.json"),
        "eslint": _eslint(root),
        "credential-scan": _credential_scan(root),
    }
    blockers = evaluate_gate(tools)
    review_required = evaluate_review_required(tools)
    generated_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    return {
        "artifact_schema": VERSION,
        "worker_execution_state": "failed" if blockers else "completed",
        "repository": repository,
        "run_id": run_id,
        "generated_at": generated_at,
        "tools": tools,
        "security_gate": {
            "status": "blocked" if blockers else "passed",
            "blockers": blockers,
            "review_required": review_required,
            "known_production_dependency_vulnerabilities_allowed": False,
            "missing_required_scanners_allowed": False,
            "untriaged_secret_findings_allowed": False,
            "high_confidence_workflow_injection_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and enforce NICO security audit evidence")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="scanner-worker-artifact.json")
    parser.add_argument("--gate-output", default="security-gate.json")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = build_manifest(
        root,
        repository=os.getenv("GITHUB_REPOSITORY", ""),
        run_id=os.getenv("GITHUB_RUN_ID", ""),
    )
    (root / args.output).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    gate = manifest["security_gate"]
    (root / args.gate_output).write_text(
        json.dumps(gate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(gate, sort_keys=True))
    return 1 if args.enforce and gate["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
