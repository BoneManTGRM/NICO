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
    approved_public_verifiers = 0
    triage: list[dict[str, Any]] = []
    for finding in data:
        if not isinstance(finding, dict):
            blocking += 1
            continue
        path = str(finding.get("File") or "")
        rule = str(finding.get("RuleID") or "")
        secret = str(finding.get("Secret") or "")
        approved_test_placeholder = (
            path.startswith("tests/")
            and rule == "generic-api-key"
            and secret == "REDACTED"
        )
        approved_public_verifier = (
            path == "nico/admin_security.py"
            and rule == "generic-api-key"
            and secret == "REDACTED"
            and str(finding.get("Match") or "").startswith(
                'DEPLOYED_SARA_OPERATOR_PASSWORD_SHA256 = "'
            )
        )
        approved = approved_test_placeholder or approved_public_verifier
        if approved_test_placeholder:
            approved_test_placeholders += 1
            disposition = "approved_test_placeholder"
        elif approved_public_verifier:
            approved_public_verifiers += 1
            disposition = "approved_public_verifier_digest"
        else:
            blocking += 1
            disposition = "blocking"
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
        approved_public_verifiers=approved_public_verifiers,
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
    approved_nonsecret_identifiers = 0
    triage: list[dict[str, Any]] = []
    for finding in findings:
        path = _trufflehog_source_path(finding)
        verified = finding.get("Verified") is True
        fixture_path = path.startswith("tests/") or path == ".env.example"
        if verified:
            disposition = "blocking_verified_secret"
            blocking += 1
        elif (
            path == "docs/operator-report-approval.md"
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            in {
                "baad0101f41fbbf2c15da26fee7ec21b0b5a069aa0763ffd267a155607a77b16",
                "583d7cd14d26cb9df88cbd31b72a31873c25f050af9988d8190617889d46f9cb",
            }
        ):
            # PR #1589 evidence: Railway deployment metadata confirms this exact
            # UUID is the deployment ID for 906daf8, not an authentication token.
            # PR #1592: fresh Railway metadata likewise confirms the second
            # digest is the successful f549dd2 production deployment identifier.
            # Retain the finding; never exempt verified values or other UUIDs.
            disposition = "approved_nonsecret_deployment_identifier"
            approved_nonsecret_identifiers += 1
        elif (
            path == "docs/human-report-repair-acceptance.md"
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            == "c0bf88741ce6e66e63e896c5ceb8e4e882ed2049facd3a88cc1d6826cd6dd2e9"
        ):
            # PR #1593: owner authorized this exact disposition after fresh
            # Railway metadata confirmed the successful 7fde559 deployment ID.
            # Verified findings still block above; retain this finding as evidence.
            disposition = "approved_nonsecret_deployment_identifier"
            approved_nonsecret_identifiers += 1
        elif (
            path == "NICO-Ship-Checkpoint.md"
            and finding.get("Verified") is False
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            == "74578dc40d97154cfd69c5767cb023643eba010802aba8dc329306074433c3c8"
        ):
            # PR #1618: authenticated Railway deployment metadata and the exact
            # retained scanner artifact identify this value as the successful
            # 59dfa4d deployment ID, not a credential. Retain the observation;
            # other values, paths, detectors and all verified secrets still block.
            disposition = "approved_nonsecret_deployment_identifier"
            approved_nonsecret_identifiers += 1
        elif (
            path == "NICO-Ship-Checkpoint.md"
            and finding.get("Verified") is False
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            == "0ca2174e3995d9ab44fc39f79cace1ebe0ee83e6a2d55ed1ece16ebcee500a21"
        ):
            # PR #1620: authenticated Railway project metadata and retained
            # CI artifact 10583914606 establish this exact nonsecret project ID.
            # Preserve the observation; verified values and other paths block.
            disposition = "approved_nonsecret_project_identifier"
            approved_nonsecret_identifiers += 1
        elif (
            path == "NICO-Ship-Checkpoint.md"
            and finding.get("Verified") is False
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            == "ab15a06f193e60201aa9e3bf61638905457c681a70fcce1083d13c6c2e9a49d9"
        ):
            # PR #1620: connector response identifies this exact value as its
            # read-only discovery conversation ID (CI artifact 10584863453).
            # No credential exemption extends to other values or verified hits.
            disposition = "approved_nonsecret_thread_identifier"
            approved_nonsecret_identifiers += 1
        elif (
            path == "NICO-Ship-Checkpoint.md"
            and finding.get("Verified") is False
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            in {
                "c8c06a22b8d59fc397706d825d2a827cfed0aa2a96b77375bfac5fc2e9aeebdc",
                "20ac6fd29475931e12bf0ed0699f2bb90b015473b06b0ee851d7ea66c22d9106",
                "38d4c5aa49b3148fd4733253d6c9f9a26b7cceea4b6094c9f40f452901c694c2",
                "759a908e7712d7e3fde18658d8a8b87010c0982dfd3928128b5649bf6dc5928b",
                "1e54f8132a238ed92b61943930014e12096ab783906227a47c490c90bdb888f9",
                "06f64a07f6c593ff3a046b7c11c0f2cfe6d7a0dde3772495a8305dce9c765a01",
                "946d01d249e1722b696f5b5c41e4516a659221a79d0ea9eb037d83e7722ed610",
                "6d4640b92e987e8f4f2165f9aeff775cff9de58ffcc1f7f43d5e95035ca04395",
                "2b28038ac24e811f5f664df493ecd9296b09c7917b51a54974bcb5cbcfb5ddce",
                "6fca1bec657f5f87061bb05e4f689a3f669c66ddd8d93f1bdb90da530db2e452",
                "ef9eb96c9686e4314a4a0dfed94e8c026ca73e7e350895ac129ce57164da3d10",
            }
        ):
            # Artifact10589039830 and authenticated Railway deployment metadata
            # identify this exact value as a prior successful deployment ID.
            # Retain the hit; other values and all verified secrets still block.
            # Artifact10593284621 plus Railway deployment metadata establish
            # the second exact digest as the serving 16ea1be deployment ID.
            # PR1628 artifact10605665271 and native Railway metadata establish
            # the final two digests as exact deployment IDs for source2f340194.
            # PR1629 artifact10606379512 and native Railway metadata establish
            # the fifth digest as the serving c5748f4 deployment ID, not a token.
            # PR1630 artifact10609745470 and native Railway metadata establish
            # the sixth digest as the serving 3d43c7a deployment ID, not a token.
            # PR1627 artifact10612373526 and native Railway metadata establish
            # the two added digests as current/replaced 34ddac28 deployment IDs.
            # PR1627 artifact10670704430 and native Railway metadata establish
            # the last digest as the SUCCESS d5b3de33 serving deployment ID.
            # Artifact10697678746 and native Railway metadata establish the
            # added digest as the SUCCESS 065baca8 serving deployment ID.
            # PR1641 artifact10717384136 and authenticated Railway metadata
            # identify the added digest as the replaced initial d5b3de33 deployment.
            # Its REMOVED status does not make the deployment ID a credential.
            disposition = "approved_nonsecret_deployment_identifier"
            approved_nonsecret_identifiers += 1
        elif (
            path == "NICO-Ship-Checkpoint.md"
            and finding.get("Verified") is False
            and finding.get("DetectorName") == "RailwayApp"
            and hashlib.sha256(str(finding.get("Raw") or "").encode()).hexdigest()
            == "55a16aefae99e52dade482f9cecc291d6b5b5a97a92910132fcaa43f9ec8e6c5"
        ):
            # Artifact10593284621 and authenticated Railway service metadata
            # identify this exact value as the NICO service ID, not a token.
            disposition = "approved_nonsecret_service_identifier"
            approved_nonsecret_identifiers += 1
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
        approved_nonsecret_identifiers=approved_nonsecret_identifiers,
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
