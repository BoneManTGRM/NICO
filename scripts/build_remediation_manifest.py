from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from nico.exact_snapshot_secret_history import parse_gitleaks_findings, parse_trufflehog_findings
from nico.exact_snapshot_static_triage import parse_static_findings


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


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _fixed_versions(vulnerability: dict[str, Any]) -> list[str]:
    versions: set[str] = set()
    for affected in _list(vulnerability.get("affected")):
        for range_item in _list(_dict(affected).get("ranges")):
            for event in _list(_dict(range_item).get("events")):
                fixed = str(_dict(event).get("fixed") or "").strip()
                if fixed:
                    versions.add(fixed)
    return sorted(versions)


def osv_records(payload: Any) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for node in _walk(payload):
        if not isinstance(node, dict):
            continue
        package = _dict(node.get("package"))
        vulnerabilities = node.get("vulnerabilities") if isinstance(node.get("vulnerabilities"), list) else node.get("vulns")
        if not package or not isinstance(vulnerabilities, list):
            continue
        name = str(package.get("name") or "unknown")
        version = str(package.get("version") or "unknown")
        ecosystem = str(package.get("ecosystem") or package.get("purl") or "unknown")
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                continue
            vulnerability_id = str(vulnerability.get("id") or _dict(vulnerability.get("database_specific")).get("id") or "unknown")
            aliases = sorted({str(item) for item in _list(vulnerability.get("aliases")) if str(item)})
            fixed_versions = _fixed_versions(vulnerability)
            key = _fingerprint(ecosystem, name, version, vulnerability_id)
            records[key] = {
                "fingerprint": key,
                "id": vulnerability_id,
                "aliases": aliases,
                "package": name,
                "installed_version": version,
                "ecosystem": ecosystem,
                "fixed_versions": fixed_versions,
                "remediation": (
                    f"Upgrade {name} from {version} to a non-vulnerable version"
                    + (f" such as {fixed_versions[0]} or later" if fixed_versions else " identified by the package ecosystem")
                    + ", then rerun OSV-Scanner."
                ),
            }
    return sorted(records.values(), key=lambda item: (item["ecosystem"], item["package"], item["id"]))


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


def npm_records(payload: Any) -> list[dict[str, Any]]:
    vulnerabilities = _dict(_dict(payload).get("vulnerabilities"))
    records = []
    for package, value in vulnerabilities.items():
        item = _dict(value)
        via = []
        for cause in _list(item.get("via")):
            if isinstance(cause, str):
                via.append(cause)
            elif isinstance(cause, dict):
                via.append(str(cause.get("title") or cause.get("name") or cause.get("source") or "advisory"))
        records.append(
            {
                "fingerprint": _fingerprint("npm", package, item.get("range"), item.get("severity")),
                "package": package,
                "severity": item.get("severity") or "unknown",
                "direct": bool(item.get("isDirect")),
                "range": item.get("range") or "",
                "via": sorted(set(via)),
                "fix_available": item.get("fixAvailable"),
                "remediation": "Update the affected direct dependency or its owning dependency chain, regenerate package-lock.json, and rerun npm audit.",
            }
        )
    return sorted(records, key=lambda item: (item["severity"], item["package"]))


def secret_records(gitleaks_text: str, trufflehog_text: str) -> tuple[list[dict[str, Any]], list[str]]:
    gitleaks, gitleaks_error = parse_gitleaks_findings(gitleaks_text) if gitleaks_text.strip() else ([], "Gitleaks output missing.")
    trufflehog, trufflehog_error = parse_trufflehog_findings(trufflehog_text) if trufflehog_text.strip() else ([], "TruffleHog output missing.")
    records = []
    for item in [*gitleaks, *trufflehog]:
        records.append(
            {
                "fingerprint": _fingerprint(item.get("tool"), item.get("rule_id"), item.get("path"), item.get("line"), item.get("commit_fingerprint")),
                "tool": item.get("tool") or "unknown",
                "rule_id": item.get("rule_id") or "unknown",
                "path": item.get("path") or "",
                "line": int(item.get("line") or 0),
                "commit_fingerprint": item.get("commit_fingerprint") or "",
                "verified": bool(item.get("verified")),
                "remediation": "Validate outside this artifact, rotate any confirmed credential, remove it from current and historical content, and rerun both full-history scanners.",
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
        "This artifact contains sanitized package, rule, path, line, and fingerprint metadata only. It intentionally excludes credential values and source snippets.",
        "",
        "## Summary",
        "",
        f"- OSV vulnerability records: {summary.get('osv_vulnerabilities', 0)}",
        f"- npm vulnerability packages: {summary.get('npm_vulnerability_packages', 0)}",
        f"- Material Bandit findings: {summary.get('bandit_material', 0)}",
        f"- Material Semgrep findings: {summary.get('semgrep_material', 0)}",
        f"- Secret-history candidates: {summary.get('secret_history_candidates', 0)}",
        f"- TypeScript validation completed: {summary.get('typescript_completed', False)}",
        "",
    ]
    for title, key in (
        ("OSV dependency records", "osv"),
        ("npm dependency records", "npm"),
        ("Material static findings", "static"),
        ("Secret-history candidates", "secret_history"),
    ):
        lines.extend([f"## {title}", ""])
        items = _list(manifest.get(key))
        if not items:
            lines.extend(["None recorded.", ""])
            continue
        for item in items:
            if key == "osv":
                lines.append(f"- `{item.get('id')}` — `{item.get('package')}@{item.get('installed_version')}` ({item.get('ecosystem')}); fixed={item.get('fixed_versions') or 'not supplied'}")
            elif key == "npm":
                lines.append(f"- `{item.get('package')}` — severity={item.get('severity')}; range=`{item.get('range')}`; direct={item.get('direct')}")
            elif key == "static":
                lines.append(f"- `{item.get('tool')}:{item.get('rule_id')}` — `{item.get('path')}:{item.get('line')}`; severity={item.get('severity')}; confidence={item.get('confidence')}; {item.get('message')}")
            else:
                lines.append(f"- `{item.get('tool')}:{item.get('rule_id')}` — `{item.get('path')}:{item.get('line')}`; commit={item.get('commit_fingerprint') or 'unknown'}; verified={item.get('verified')}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--osv", type=Path)
    parser.add_argument("--npm-audit", type=Path)
    parser.add_argument("--bandit", type=Path)
    parser.add_argument("--semgrep", type=Path)
    parser.add_argument("--gitleaks", type=Path)
    parser.add_argument("--trufflehog", type=Path)
    parser.add_argument("--typescript", type=Path)
    parser.add_argument("--typescript-exit", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    osv = osv_records(_json(args.osv))
    npm = npm_records(_json(args.npm_audit))
    bandit, bandit_error = static_records("bandit", _read(args.bandit))
    semgrep, semgrep_error = static_records("semgrep", _read(args.semgrep))
    secret_history, secret_errors = secret_records(_read(args.gitleaks), _read(args.trufflehog))
    typescript = _typescript_summary(args.typescript, args.typescript_exit)
    manifest = {
        "artifact_schema": "nico.remediation_manifest.v1",
        "summary": {
            "osv_vulnerabilities": len(osv),
            "npm_vulnerability_packages": len(npm),
            "bandit_material": len(bandit),
            "semgrep_material": len(semgrep),
            "secret_history_candidates": len(secret_history),
            "typescript_completed": bool(typescript.get("completed")),
        },
        "osv": osv,
        "npm": npm,
        "static": [*bandit, *semgrep],
        "secret_history": secret_history,
        "typescript": typescript,
        "parse_warnings": [item for item in (bandit_error, semgrep_error, *secret_errors) if item],
        "guardrail": "No credential values or source snippets are included. Findings still require human validation before code changes, credential rotation, accepted-risk disposition, or client approval.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(_markdown(manifest) + "\n", encoding="utf-8")
    print(json.dumps(manifest["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
