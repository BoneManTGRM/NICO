from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from nico.dependency_scanner_triage import (
    corroborate_dependency_records,
    parse_npm_audit,
    parse_osv,
    parse_pip_audit,
)
from nico.exact_snapshot_secret_history import parse_gitleaks_findings, parse_trufflehog_findings
from nico.exact_snapshot_static_triage import parse_static_findings
from nico.secret_history_triage import classify_history_findings


def _read(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _json(path: Path | None) -> Any:
    text = _read(path).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
        if not starts:
            return None
        try:
            return json.loads(text[min(starts) :])
        except json.JSONDecodeError:
            return None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _fingerprint(*parts: Any) -> str:
    material = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(material.encode("utf-8", errors="replace")).hexdigest()[:20]


def dependency_records(osv_payload: Any, pip_payload: Any, npm_payload: Any) -> dict[str, Any]:
    osv = parse_osv(osv_payload)
    pip = parse_pip_audit(pip_payload)
    npm = parse_npm_audit(npm_payload)
    scanner = {
        "scanner_results": [
            {
                "scanner": "osv-scanner",
                "execution_completed": osv_payload is not None,
                "dependency_records": osv,
            },
            {
                "scanner": "pip-audit",
                "execution_completed": pip_payload is not None,
                "resolved_versions": pip.get("resolved_versions") or {},
                "dependency_records": pip.get("vulnerabilities") or [],
            },
            {
                "scanner": "npm-audit",
                "execution_completed": npm_payload is not None,
                "dependency_records": npm.get("vulnerabilities") or [],
            },
        ]
    }
    correlated = corroborate_dependency_records(scanner)
    return {
        "osv_grouped": osv,
        "pip": pip.get("vulnerabilities") or [],
        "npm": npm.get("vulnerabilities") or [],
        "material": correlated.get("material_records") or [],
        "review": correlated.get("review_records") or [],
        "pip_resolved_versions": pip.get("resolved_versions") or {},
        "scanner_completion": {
            "osv": bool(correlated.get("osv_completed")),
            "pip_audit": bool(correlated.get("pip_audit_completed")),
            "npm_audit": bool(correlated.get("npm_audit_completed")),
        },
    }


def static_records(tool: str, text: str) -> tuple[list[dict[str, Any]], str | None]:
    findings, parse_error = parse_static_findings(tool, text)
    records = []
    for item in findings:
        if not item.get("material"):
            continue
        records.append(
            {
                "fingerprint": _fingerprint(tool, item.get("rule_id"), item.get("path"), item.get("line")),
                "tool": tool,
                "rule_id": item.get("rule_id") or "unknown",
                "path": item.get("path") or "",
                "line": int(item.get("line") or 0),
                "severity": item.get("severity") or "unknown",
                "confidence": item.get("confidence") or "unknown",
                "message": item.get("message") or "",
                "remediation": "Review the exact code path, apply the narrowest safe repair, add a regression test, and rerun the same analyzer.",
            }
        )
    return sorted(records, key=lambda item: (item["path"], item["line"], item["rule_id"])), parse_error


def secret_records(gitleaks_text: str, trufflehog_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    gitleaks, gitleaks_error = parse_gitleaks_findings(gitleaks_text) if gitleaks_text.strip() else ([], "Gitleaks output missing.")
    trufflehog, trufflehog_error = parse_trufflehog_findings(trufflehog_text) if trufflehog_text.strip() else ([], "TruffleHog output missing.")
    records = []
    for item in classify_history_findings([*gitleaks, *trufflehog]):
        records.append(
            {
                "fingerprint": _fingerprint(item.get("tool"), item.get("rule_id"), item.get("path"), item.get("line"), item.get("commit_fingerprint")),
                "tool": item.get("tool") or "unknown",
                "rule_id": item.get("rule_id") or "unknown",
                "path": item.get("path") or "",
                "line": int(item.get("line") or 0),
                "commit_fingerprint": item.get("commit_fingerprint") or "",
                "verified": bool(item.get("verified")),
                "test_only": bool(item.get("test_only")),
                "material": bool(item.get("material")),
                "review_required": bool(item.get("review_required")),
                "disposition": item.get("disposition") or "review",
                "remediation": "Rotate confirmed credentials outside this artifact; review production candidates; keep synthetic test fixtures distinct from production exposure.",
            }
        )
    errors = [item for item in (gitleaks_error, trufflehog_error) if item]
    return sorted(records, key=lambda item: (item["tool"], item["path"], item["line"])), errors


def _typescript_summary(path: Path | None, exit_code: str) -> dict[str, Any]:
    lines = [line.strip() for line in _read(path).splitlines() if line.strip()]
    return {
        "exit_code": int(exit_code) if str(exit_code).strip().lstrip("-").isdigit() else None,
        "completed": str(exit_code).strip() == "0",
        "diagnostics": lines[:100],
    }


def _markdown(manifest: dict[str, Any]) -> str:
    summary = _dict(manifest.get("summary"))
    lines = [
        "# NICO Remediation Manifest",
        "",
        "This artifact contains sanitized package, advisory, rule, path, line, and fingerprint metadata only. It intentionally excludes credential values and source snippets.",
        "",
        "## Summary",
        "",
        f"- Corroborated dependency vulnerabilities: {summary.get('dependency_material', 0)}",
        f"- Dependency records requiring review: {summary.get('dependency_review', 0)}",
        f"- Grouped OSV records: {summary.get('osv_grouped_records', 0)}",
        f"- Material Bandit findings: {summary.get('bandit_material', 0)}",
        f"- Material Semgrep findings: {summary.get('semgrep_material', 0)}",
        f"- Material secret-history findings: {summary.get('secret_history_material', 0)}",
        f"- Excluded test-only secret matches: {summary.get('secret_history_test_only', 0)}",
        f"- TypeScript validation completed: {summary.get('typescript_completed', False)}",
        "",
        "## Corroborated dependency findings",
        "",
    ]
    dependencies = _dict(manifest.get("dependencies"))
    material = _list(dependencies.get("material"))
    review = _list(dependencies.get("review"))
    if not material:
        lines.append("No corroborated installed dependency vulnerability was recorded.")
    for item in material:
        lines.append(
            f"- `{item.get('package')}@{item.get('installed_version')}` ({item.get('ecosystem')}) — {item.get('advisory_ids') or []}; fixed={item.get('fixed_versions') or 'not supplied'}"
        )
    lines.extend(["", "## Dependency review records", ""])
    if not review:
        lines.append("None recorded.")
    for item in review:
        lines.append(
            f"- `{item.get('package')}@{item.get('installed_version')}` ({item.get('ecosystem')}) — {item.get('disposition_reason') or 'review required'}"
        )
    lines.extend(["", "## Material static findings", ""])
    static = _list(manifest.get("static"))
    if not static:
        lines.append("None recorded.")
    for item in static:
        lines.append(
            f"- `{item.get('tool')}:{item.get('rule_id')}` — `{item.get('path')}:{item.get('line')}`; severity={item.get('severity')}; confidence={item.get('confidence')}; {item.get('message')}"
        )
    lines.extend(["", "## Secret-history matches", ""])
    secrets = _list(manifest.get("secret_history"))
    if not secrets:
        lines.append("None recorded.")
    for item in secrets:
        lines.append(
            f"- `{item.get('tool')}:{item.get('rule_id')}` — `{item.get('path')}:{item.get('line')}`; verified={item.get('verified')}; disposition={item.get('disposition')}"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osv", type=Path)
    parser.add_argument("--pip-audit", type=Path)
    parser.add_argument("--npm-audit", type=Path)
    parser.add_argument("--bandit", type=Path)
    parser.add_argument("--semgrep", type=Path)
    parser.add_argument("--gitleaks", type=Path)
    parser.add_argument("--trufflehog", type=Path)
    parser.add_argument("--typescript", type=Path)
    parser.add_argument("--typescript-exit", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dependencies = dependency_records(_json(args.osv), _json(args.pip_audit), _json(args.npm_audit))
    bandit, bandit_error = static_records("bandit", _read(args.bandit))
    semgrep, semgrep_error = static_records("semgrep", _read(args.semgrep))
    secret_history, secret_errors = secret_records(_read(args.gitleaks), _read(args.trufflehog))
    typescript = _typescript_summary(args.typescript, args.typescript_exit)
    manifest = {
        "artifact_schema": "nico.remediation_manifest.v2",
        "summary": {
            "dependency_material": len(_list(dependencies.get("material"))),
            "dependency_review": len(_list(dependencies.get("review"))),
            "osv_grouped_records": len(_list(dependencies.get("osv_grouped"))),
            "bandit_material": len(bandit),
            "semgrep_material": len(semgrep),
            "secret_history_material": sum(bool(item.get("material")) for item in secret_history),
            "secret_history_test_only": sum(bool(item.get("test_only")) and not bool(item.get("verified")) for item in secret_history),
            "typescript_completed": bool(typescript.get("completed")),
        },
        "dependencies": dependencies,
        "static": [*bandit, *semgrep],
        "secret_history": secret_history,
        "typescript": typescript,
        "parse_warnings": [item for item in (bandit_error, semgrep_error, *secret_errors) if item],
        "guardrail": "No credential values or source snippets are included. Scanner disagreements remain visible. Findings still require human validation before code changes, credential rotation, accepted-risk disposition, or client approval.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(_markdown(manifest) + "\n", encoding="utf-8")
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
