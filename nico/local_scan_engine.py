from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|jwt|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"),
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{16,})"),
]

OPTIONAL_TOOLS = {
    "gitleaks": "secret scanning",
    "trufflehog": "secret scanning",
    "osv-scanner": "dependency scanning",
    "pip-audit": "python dependency scanning",
    "npm": "npm audit availability",
    "scorecard": "OpenSSF scorecard",
    "semgrep": "code security scanning",
    "bandit": "python static analysis",
    "eslint": "javascript/typescript static analysis",
}

APPSEC_PATTERNS = [
    ("unsafe_eval", "critical", "Unsafe eval usage", "eval(", "Replace eval with a safe parser or allowlist.", "User-controlled eval can lead to code execution.", "CWE-95"),
    ("debug_mode", "high", "Debug mode enabled", "debug=True", "Disable debug mode outside local fixtures.", "Debug mode can expose internals.", "CWE-489"),
    ("missing_rate_limit", "medium", "Rate limiting TODO", "TODO: add rate limiting", "Add rate limiting and abuse detection.", "Missing throttling increases abuse risk.", "CWE-307"),
    ("insecure_webhook", "high", "Webhook signature missing", "TODO: verify signature", "Verify webhook signatures and add replay protection.", "Unsigned webhooks can allow forged events.", "CWE-345"),
    ("unsafe_file_upload", "high", "Unsafe upload fixture", "TODO: validate upload", "Validate file type, size, name, path, and storage.", "Unsafe upload handling can expose data or execution paths.", "CWE-434"),
    ("ai_agent_permission_drift", "high", "AI over-permission fixture", "over_permissive_tools = True", "Restrict AI-agent tools to least privilege.", "Over-permissioned AI tools can exceed intended access boundaries.", "OWASP-LLM-A06"),
]

SEVERITY_POINTS = {"low": 1, "medium": 3, "high": 7, "critical": 10}
SKIP_SCAN_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".nico", ".next"}
SAFE_SCAN_PART_RE = re.compile(r"^[A-Za-z0-9._ -]+$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def mask(value: str) -> str:
    return "***" if len(value) <= 8 else value[:4] + "…" + value[-4:]


def mask_text(text: str) -> str:
    out = text
    for pattern in SECRET_PATTERNS:
        out = pattern.sub(
            lambda match: (
                match.group(1) + '="' + mask(match.group(2)) + '"'
                if match.lastindex and match.lastindex >= 2
                else mask(match.group(0))
            ),
            out,
        )
    return out


def scanner_availability() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool, purpose in OPTIONAL_TOOLS.items():
        available = shutil.which(tool) is not None
        result.append(
            {
                "tool": tool,
                "purpose": purpose,
                "available": available,
                "mode": "optional_external" if available else "built_in_fallback_active",
            }
        )
    return result


def normalized_finding(
    source: str,
    category: str,
    severity: str,
    confidence: float,
    title: str,
    path: str = "",
    line: int | None = None,
    masked: str = "",
    raw_fp: str = "",
    biz: str = "",
    tech: str = "",
    fix: str = "",
    verify: str = "",
    mapping: list[str] | None = None,
) -> dict[str, Any]:
    finding_id = new_id("finding")
    return {
        "finding_id": finding_id,
        "id": finding_id,
        "source": source,
        "category": category,
        "severity": severity,
        "confidence": confidence,
        "title": title,
        "affected_file": path,
        "affected_line": line,
        "file_path": path,
        "line": line,
        "masked_evidence": masked,
        "raw_evidence_fingerprint": raw_fp,
        "business_impact": biz,
        "technical_impact": tech,
        "recommended_fix": fix,
        "recommendation": fix,
        "verification_method": verify,
        "standards_mapping": mapping or [],
        "created_at": now(),
        "status": "open",
    }


def scan_text(path: str, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                raw = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0)
                fake = "FAKE_TEST_ONLY" in raw.upper()
                findings.append(
                    normalized_finding(
                        "built_in_secret_scanner",
                        "secret_exposure",
                        "high" if fake else "critical",
                        0.95,
                        "Potential secret detected",
                        path,
                        line_number,
                        mask_text(line.strip()),
                        fingerprint(raw),
                        "A leaked credential can expose systems, billing, users, or customer data.",
                        "Credential-like source value was found. Raw value is not stored.",
                        "Move to environment/secrets manager and rotate if real.",
                        "Rescan affected file and confirm credential-like value is absent.",
                        ["CWE-798", "OWASP-ASVS-V6"],
                    )
                )
        for category, severity, title, marker, fix, biz, map_id in APPSEC_PATTERNS:
            if marker in line:
                findings.append(
                    normalized_finding(
                        "built_in_appsec_scanner",
                        category,
                        severity,
                        0.88,
                        title,
                        path,
                        line_number,
                        line.strip(),
                        fingerprint(category + path + str(line_number)),
                        biz,
                        f"{title} marker was detected.",
                        fix,
                        "Apply targeted fix, run tests, and rescan affected file.",
                        [map_id],
                    )
                )
    if path.endswith("requirements.txt") and "flask==0.12" in text:
        findings.append(
            normalized_finding(
                "built_in_dependency_scanner",
                "dependency_risk",
                "high",
                0.9,
                "Risky Python dependency fixture",
                path,
                masked="flask==0.12",
                raw_fp="dependency-fixture-flask-012",
                biz="Outdated dependencies increase breach and downtime risk.",
                tech="Old Flask test fixture detected.",
                fix="Upgrade dependency and run tests.",
                verify="Rescan dependency manifests and confirm risky version is absent.",
                mapping=["CWE-1104"],
            )
        )
    if path.endswith("package.json") and "4.17.15" in text:
        findings.append(
            normalized_finding(
                "built_in_dependency_scanner",
                "dependency_risk",
                "high",
                0.9,
                "Risky npm dependency fixture",
                path,
                masked="lodash 4.17.15",
                raw_fp="dependency-fixture-lodash-41715",
                biz="Outdated packages can expose exploitable paths.",
                tech="Old lodash test fixture detected.",
                fix="Upgrade package and run tests.",
                verify="Rescan package manifest and confirm risky version is absent.",
                mapping=["CWE-1104"],
            )
        )
    if path.endswith(".jsonl"):
        events = []
        for row in text.splitlines():
            try:
                events.append(json.loads(row))
            except Exception:
                pass
        if sum(1 for event in events if event.get("event") == "failed_login") >= 5:
            findings.append(
                normalized_finding(
                    "built_in_log_scanner",
                    "log_anomaly",
                    "high",
                    0.85,
                    "Repeated failed login pattern",
                    path,
                    masked="failed_login count >= 5",
                    raw_fp="failed-login-fixture",
                    biz="Repeated failed logins can indicate credential stuffing or brute force.",
                    tech="Mock repeated failed login pattern detected.",
                    fix="Add rate limits, MFA review, and alerting.",
                    verify="Inspect logs after controls and confirm detection/reduction.",
                    mapping=["MITRE-ATTACK-T1110"],
                )
            )
        if any(event.get("event") == "admin_role_change" for event in events):
            findings.append(
                normalized_finding(
                    "built_in_log_scanner",
                    "identity_risk",
                    "high",
                    0.84,
                    "Suspicious admin action pattern",
                    path,
                    masked="admin role change",
                    raw_fp="admin-role-change-fixture",
                    biz="Unexpected admin changes can lead to privilege abuse.",
                    tech="Mock admin role change detected.",
                    fix="Require approval and audit logs for admin changes.",
                    verify="Confirm admin changes require approval and audit logging.",
                    mapping=["MITRE-ATTACK-T1078"],
                )
            )
    return findings


def allowed_scan_bases() -> list[Path]:
    configured = os.getenv("NICO_ALLOWED_SCAN_ROOTS") or os.getenv("NICO_ALLOWED_SCAN_ROOT") or str(Path.cwd())
    bases: list[Path] = []
    for raw_base in configured.split(os.pathsep):
        raw_base = raw_base.strip()
        if not raw_base:
            continue
        try:
            base = Path(raw_base).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if base.is_dir():
            bases.append(base)
    if not bases:
        bases.append(Path.cwd().resolve())
    return bases


def safe_target_parts_for_base(target: str, base: Path) -> tuple[str, ...]:
    target_text = str(target or "").strip()
    if not target_text or "\x00" in target_text:
        raise ValueError("scan target is empty or invalid")
    base_text = str(base)
    if target_text == base_text:
        return ()
    if target_text.startswith(base_text + os.sep):
        relative_text = target_text[len(base_text) + 1 :]
    elif os.path.isabs(target_text):
        raise ValueError("absolute scan target is outside the allowed root")
    else:
        relative_text = target_text
    if "\\" in relative_text:
        raise ValueError("scan target separators are invalid")
    parts = tuple(part for part in relative_text.split("/") if part)
    if any(part in {".", ".."} or not SAFE_SCAN_PART_RE.fullmatch(part) for part in parts):
        raise ValueError("scan target contains unsafe path components")
    return parts


def resolve_scan_root_under_base(target: str, base: Path) -> Path:
    parts = safe_target_parts_for_base(target, base)
    candidate = base.joinpath(*parts)
    root = candidate.resolve(strict=True)
    root.relative_to(base)
    if not root.is_dir():
        raise NotADirectoryError("scan target must be an existing directory")
    return root


def safe_scan_root(target: str) -> Path:
    for base in allowed_scan_bases():
        try:
            return resolve_scan_root_under_base(target, base)
        except (OSError, RuntimeError, ValueError, NotADirectoryError):
            continue
    raise NotADirectoryError("scan target must be an existing directory under an allowed scan root")


def safe_scan_file(root: Path, candidate: Path) -> tuple[Path, str] | None:
    try:
        if candidate.is_symlink():
            return None
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    if resolved.is_dir() or resolved.is_symlink():
        return None
    if any(part in SKIP_SCAN_DIRS for part in relative.parts):
        return None
    return resolved, str(relative)


def safe_scan_files(root: Path) -> Iterable[tuple[Path, str]]:
    for candidate in root.rglob("*"):
        safe = safe_scan_file(root, candidate)
        if safe is not None:
            yield safe


def scan_repo(target: str) -> dict[str, Any]:
    root = safe_scan_root(target)
    findings: list[dict[str, Any]] = []
    files: list[str] = []
    for path, rel_path in safe_scan_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files.append(rel_path)
        findings.extend(scan_text(rel_path, text))
    return {
        "id": new_id("scan"),
        "target": str(root),
        "created_at": now(),
        "files_scanned": files,
        "findings": findings,
        "scanner_availability": scanner_availability(),
    }


def risk_score(findings: list[dict[str, Any]]) -> int:
    return min(
        100,
        sum(SEVERITY_POINTS.get(str(finding.get("severity", "low")).lower(), 1) for finding in findings) * 5,
    )


def make_baseline(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "scan_id": scan["id"],
        "files_scanned_count": len(scan["files_scanned"]),
        "finding_count": len(scan["findings"]),
        "risk_score": risk_score(scan["findings"]),
        "categories": sorted({finding["category"] for finding in scan["findings"]}),
    }


def detect_drift(base: dict[str, Any] | None, scan: dict[str, Any]) -> list[dict[str, Any]]:
    if not base:
        return []
    current_risk = risk_score(scan["findings"])
    baseline_risk = base.get("risk_score", 0)
    drift: list[dict[str, Any]] = []
    if current_risk > baseline_risk:
        drift.append(
            {
                "id": new_id("drift"),
                "type": "risk_score_drift",
                "severity": "high",
                "created_at": now(),
                "baseline_risk": baseline_risk,
                "current_risk": current_risk,
                "description": "Current scan risk exceeds the stored secure baseline.",
            }
        )
    baseline_categories = set(base.get("categories", []))
    current_categories = {finding["category"] for finding in scan["findings"]}
    for category in sorted(current_categories - baseline_categories):
        drift.append(
            {
                "id": new_id("drift"),
                "type": category,
                "severity": "medium",
                "created_at": now(),
                "baseline_risk": baseline_risk,
                "current_risk": current_risk,
                "description": f"New drift category detected: {category}",
            }
        )
    return drift
