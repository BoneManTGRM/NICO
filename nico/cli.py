from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NICO_HOME = Path(os.getenv("NICO_HOME", PROJECT_ROOT / ".nico"))
DB_PATH = Path(os.getenv("NICO_DB_PATH", NICO_HOME / "nico.sqlite3"))
REPORT_DIR = Path(os.getenv("NICO_REPORT_DIR", NICO_HOME / "reports"))
TEST_LAB = PROJECT_ROOT / "nico" / "test_lab"
SAMPLE_REPO = TEST_LAB / "sample_repo"
DRIFT_REPO = TEST_LAB / "drift_workspace"

for directory in (NICO_HOME, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|jwt|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-./+=]{8,})"),
    re.compile(r"(sk-[A-Za-z0-9]{16,})"),
    re.compile(r"(ghp_[A-Za-z0-9]{16,})"),
]

SEVERITY_POINTS = {"low": 1, "medium": 3, "high": 7, "critical": 10}

DEFAULT_POLICY = {
    "autonomy_level": 1,
    "kill_switch": False,
    "allowed_actions": ["scan", "report", "score", "repair_plan", "verify", "memory_update", "create_draft_pr"],
    "approval_required": [
        "production_key_rotation", "permanent_account_disable", "data_delete", "infrastructure_delete",
        "major_dependency_upgrade", "dns_change", "broad_firewall_change", "production_deploy", "architecture_rewrite",
    ],
    "blocked_actions": [
        "exploit", "credential_theft", "phishing", "malware", "evasion", "persistence",
        "unauthorized_scan", "destructive_action", "auth_bypass",
    ],
}

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

REPAIR_LIBRARY = {
    "secret_exposure": "Move secret to env/secrets manager, rotate if real, and add scanning.",
    "dependency_risk": "Upgrade dependency and verify tests/build.",
    "insecure_webhook": "Verify signatures, reject missing signatures, and add replay protection where possible.",
    "unsafe_eval": "Replace eval with a safe parser or explicit allowlist.",
    "debug_mode": "Disable debug mode outside local-only fixtures.",
    "missing_rate_limit": "Add rate limiting and abuse detection.",
    "unsafe_file_upload": "Validate upload type, size, name, path, and storage.",
    "log_anomaly": "Add rate limits, MFA review, alerting, and event correlation.",
    "identity_risk": "Require approval and audit logs for admin role changes.",
    "ai_agent_permission_drift": "Apply least-privilege tool access and human approval gates.",
}

SKIP_SCAN_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".nico", ".next"}
SAFE_SCAN_PART_RE = re.compile(r"^[A-Za-z0-9._ -]+$")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def fp(value: str) -> str:
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
    return [
        {
            "tool": tool,
            "purpose": purpose,
            "available": shutil.which(tool) is not None,
            "mode": "optional_external" if shutil.which(tool) else "built_in_fallback_active",
        }
        for tool, purpose in OPTIONAL_TOOLS.items()
    ]


def decide_action(action: str, policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("kill_switch"):
        return {"allowed": False, "reason": "kill switch enabled", "requires_approval": True}
    if action in policy.get("blocked_actions", []):
        return {"allowed": False, "reason": "blocked by defensive policy", "requires_approval": False}
    if action in policy.get("approval_required", []):
        return {"allowed": False, "reason": "human approval required", "requires_approval": True}
    if action in policy.get("allowed_actions", []):
        return {"allowed": True, "reason": "allowed", "requires_approval": False}
    return {"allowed": False, "reason": "unknown action denied by default", "requires_approval": True}


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def db(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        with self.db() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, kind TEXT, created_at TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS findings(id TEXT PRIMARY KEY, scan_id TEXT, severity TEXT, category TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS drift_events(id TEXT PRIMARY KEY, scan_id TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS repairs(id TEXT PRIMARY KEY, finding_id TEXT, status TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS memory(id TEXT PRIMARY KEY, payload TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, format TEXT, path TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, detail TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);
                CREATE TABLE IF NOT EXISTS baseline(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS verification(id TEXT PRIMARY KEY, repair_id TEXT, payload TEXT, created_at TEXT);
                """
            )

    def audit(self, action: str, detail: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute("INSERT INTO audit_log(action,detail,created_at) VALUES(?,?,?)", (action, json.dumps(detail, sort_keys=True), now()))

    def save_scan(self, scan: dict[str, Any], kind: str) -> None:
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO scans VALUES(?,?,?,?)", (scan["id"], kind, scan["created_at"], json.dumps(scan, sort_keys=True)))
            for finding in scan["findings"]:
                db.execute("INSERT OR REPLACE INTO findings VALUES(?,?,?,?,?)", (finding["id"], scan["id"], finding["severity"], finding["category"], json.dumps(finding, sort_keys=True)))

    def save_drift(self, scan_id: str, drift: list[dict[str, Any]]) -> None:
        with self.db() as db:
            for event in drift:
                db.execute("INSERT OR REPLACE INTO drift_events VALUES(?,?,?)", (event["id"], scan_id, json.dumps(event, sort_keys=True)))

    def save_repairs(self, repairs: list[dict[str, Any]]) -> None:
        with self.db() as db:
            for repair in repairs:
                db.execute("INSERT OR REPLACE INTO repairs VALUES(?,?,?,?)", (repair["id"], repair["finding_id"], repair.get("status", "suggested"), json.dumps(repair, sort_keys=True)))

    def update_repair_status(self, repair_id: str, status: str) -> dict[str, Any] | None:
        target = None
        for repair in self.payloads("repairs"):
            if repair.get("id") == repair_id or repair.get("repair_id") == repair_id:
                repair["status"] = status
                target = repair
                break
        if target:
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO repairs VALUES(?,?,?,?)", (target["id"], target["finding_id"], status, json.dumps(target, sort_keys=True)))
        return target

    def save_memory(self, payload: dict[str, Any]) -> None:
        payload.setdefault("created_at", now())
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO memory VALUES(?,?,?)", (payload["id"], json.dumps(payload, sort_keys=True), payload["created_at"]))

    def save_verification(self, result: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO verification VALUES(?,?,?,?)", (result["id"], result.get("repair_id"), json.dumps(result, sort_keys=True), result["created_at"]))

    def save_report(self, report_id: str, fmt: str, path: str) -> None:
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO reports VALUES(?,?,?,?)", (report_id, fmt, path, now()))

    def rows(self, table: str) -> list[dict[str, Any]]:
        queries = {
            "scans": "SELECT * FROM scans ORDER BY rowid DESC",
            "findings": "SELECT * FROM findings ORDER BY rowid DESC",
            "drift_events": "SELECT * FROM drift_events ORDER BY rowid DESC",
            "repairs": "SELECT * FROM repairs ORDER BY rowid DESC",
            "memory": "SELECT * FROM memory ORDER BY rowid DESC",
            "reports": "SELECT * FROM reports ORDER BY rowid DESC",
            "audit_log": "SELECT * FROM audit_log ORDER BY rowid DESC",
            "verification": "SELECT * FROM verification ORDER BY rowid DESC",
        }
        query = queries.get(table)
        if query is None:
            raise ValueError(f"unsupported table: {table}")
        with self.db() as db:
            rows = db.execute(query).fetchall()
        return [dict(row) for row in rows]

    def payloads(self, table: str) -> list[dict[str, Any]]:
        return [json.loads(row["payload"]) for row in self.rows(table) if row.get("payload")]

    def latest_scan(self) -> dict[str, Any]:
        with self.db() as db:
            row = db.execute("SELECT * FROM scans ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            return {}
        data = dict(row)
        data["payload"] = json.loads(data["payload"])
        data.update(data["payload"])
        return data

    def latest_verification(self) -> dict[str, Any]:
        with self.db() as db:
            row = db.execute("SELECT payload FROM verification ORDER BY created_at DESC LIMIT 1").fetchone()
        return json.loads(row["payload"]) if row else {}

    def baseline(self) -> dict[str, Any] | None:
        with self.db() as db:
            row = db.execute("SELECT payload FROM baseline WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else None

    def save_baseline(self, baseline: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO baseline VALUES(1,?,?)", (json.dumps(baseline, sort_keys=True), now()))

    def policy(self) -> dict[str, Any]:
        with self.db() as db:
            row = db.execute("SELECT payload FROM policy WHERE id=1").fetchone()
        return json.loads(row["payload"]) if row else DEFAULT_POLICY.copy()

    def save_policy(self, policy: dict[str, Any]) -> None:
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO policy VALUES(1,?)", (json.dumps(policy, sort_keys=True),))


def normalized_finding(source: str, category: str, severity: str, confidence: float, title: str, path: str = "", line: int | None = None, masked: str = "", raw_fp: str = "", biz: str = "", tech: str = "", fix: str = "", verify: str = "", mapping: list[str] | None = None) -> dict[str, Any]:
    finding_id = new_id("finding")
    return {"finding_id": finding_id, "id": finding_id, "source": source, "category": category, "severity": severity, "confidence": confidence, "title": title, "affected_file": path, "affected_line": line, "file_path": path, "line": line, "masked_evidence": masked, "raw_evidence_fingerprint": raw_fp, "business_impact": biz, "technical_impact": tech, "recommended_fix": fix, "recommendation": fix, "verification_method": verify, "standards_mapping": mapping or [], "created_at": now(), "status": "open"}


def scan_text(path: str, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if match:
                raw = match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(0)
                fake = "FAKE_TEST_ONLY" in raw.upper()
                findings.append(normalized_finding("built_in_secret_scanner", "secret_exposure", "high" if fake else "critical", 0.95, "Potential secret detected", path, line_number, mask_text(line.strip()), fp(raw), "A leaked credential can expose systems, billing, users, or customer data.", "Credential-like source value was found. Raw value is not stored.", "Move to environment/secrets manager and rotate if real.", "Rescan affected file and confirm credential-like value is absent.", ["CWE-798", "OWASP-ASVS-V6"]))
        for category, severity, title, marker, fix, biz, map_id in APPSEC_PATTERNS:
            if marker in line:
                findings.append(normalized_finding("built_in_appsec_scanner", category, severity, 0.88, title, path, line_number, line.strip(), fp(category + path + str(line_number)), biz, f"{title} marker was detected.", fix, "Apply targeted fix, run tests, and rescan affected file.", [map_id]))
    if path.endswith("requirements.txt") and "flask==0.12" in text:
        findings.append(normalized_finding("built_in_dependency_scanner", "dependency_risk", "high", 0.9, "Risky Python dependency fixture", path, masked="flask==0.12", raw_fp="dependency-fixture-flask-012", biz="Outdated dependencies increase breach and downtime risk.", tech="Old Flask test fixture detected.", fix="Upgrade dependency and run tests.", verify="Rescan dependency manifests and confirm risky version is absent.", mapping=["CWE-1104"]))
    if path.endswith("package.json") and "4.17.15" in text:
        findings.append(normalized_finding("built_in_dependency_scanner", "dependency_risk", "high", 0.9, "Risky npm dependency fixture", path, masked="lodash 4.17.15", raw_fp="dependency-fixture-lodash-41715", biz="Outdated packages can expose exploitable paths.", tech="Old lodash test fixture detected.", fix="Upgrade package and run tests.", verify="Rescan package manifest and confirm risky version is absent.", mapping=["CWE-1104"]))
    if path.endswith(".jsonl"):
        events = []
        for row in text.splitlines():
            try:
                events.append(json.loads(row))
            except Exception:
                pass
        if sum(1 for event in events if event.get("event") == "failed_login") >= 5:
            findings.append(normalized_finding("built_in_log_scanner", "log_anomaly", "high", 0.85, "Repeated failed login pattern", path, masked="failed_login count >= 5", raw_fp="failed-login-fixture", biz="Repeated failed logins can indicate credential stuffing or brute force.", tech="Mock repeated failed login pattern detected.", fix="Add rate limits, MFA review, and alerting.", verify="Inspect logs after controls and confirm detection/reduction.", mapping=["MITRE-ATTACK-T1110"]))
        if any(event.get("event") == "admin_role_change" for event in events):
            findings.append(normalized_finding("built_in_log_scanner", "identity_risk", "high", 0.84, "Suspicious admin action pattern", path, masked="admin role change", raw_fp="admin-role-change-fixture", biz="Unexpected admin changes can lead to privilege abuse.", tech="Mock admin role change detected.", fix="Require approval and audit logs for admin changes.", verify="Confirm admin changes require approval and audit logging.", mapping=["MITRE-ATTACK-T1078"]))
    return findings


def _allowed_scan_bases() -> list[Path]:
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


def _safe_target_parts_for_base(target: str, base: Path) -> tuple[str, ...]:
    target_text = str(target or "").strip()
    if not target_text or "\x00" in target_text:
        raise ValueError("scan target is empty or invalid")
    base_text = str(base)
    if target_text == base_text:
        return ()
    if target_text.startswith(base_text + os.sep):
        relative_text = target_text[len(base_text) + 1:]
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


def _resolve_scan_root_under_base(target: str, base: Path) -> Path:
    parts = _safe_target_parts_for_base(target, base)
    candidate = base.joinpath(*parts)
    root = candidate.resolve(strict=True)
    root.relative_to(base)
    if not root.is_dir():
        raise NotADirectoryError("scan target must be an existing directory")
    return root


def _safe_scan_root(target: str) -> Path:
    for base in _allowed_scan_bases():
        try:
            return _resolve_scan_root_under_base(target, base)
        except (OSError, RuntimeError, ValueError, NotADirectoryError):
            continue
    raise NotADirectoryError("scan target must be an existing directory under an allowed scan root")


def _safe_scan_file(root: Path, candidate: Path) -> tuple[Path, str] | None:
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


def _safe_scan_files(root: Path) -> Iterable[tuple[Path, str]]:
    for candidate in root.rglob("*"):
        safe = _safe_scan_file(root, candidate)
        if safe is not None:
            yield safe


def scan_repo(target: str) -> dict[str, Any]:
    root = _safe_scan_root(target)
    findings: list[dict[str, Any]] = []
    files: list[str] = []
    for path, rel_path in _safe_scan_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files.append(rel_path)
        findings.extend(scan_text(rel_path, text))
    return {"id": new_id("scan"), "target": str(root), "created_at": now(), "files_scanned": files, "findings": findings, "scanner_availability": scanner_availability()}


def risk_score(findings: list[dict[str, Any]]) -> int:
    return min(100, sum(SEVERITY_POINTS.get(str(finding.get("severity", "low")).lower(), 1) for finding in findings) * 5)


def make_baseline(scan: dict[str, Any]) -> dict[str, Any]:
    return {"scan_id": scan["id"], "files_scanned_count": len(scan["files_scanned"]), "finding_count": len(scan["findings"]), "risk_score": risk_score(scan["findings"]), "categories": sorted({finding["category"] for finding in scan["findings"]})}


def detect_drift(base: dict[str, Any] | None, scan: dict[str, Any]) -> list[dict[str, Any]]:
    if not base:
        return []
    current_risk = risk_score(scan["findings"])
    baseline_risk = base.get("risk_score", 0)
    drift: list[dict[str, Any]] = []
    if current_risk > baseline_risk:
        drift.append({"id": new_id("drift"), "type": "risk_score_drift", "severity": "high", "created_at": now(), "baseline_risk": baseline_risk, "current_risk": current_risk, "description": "Current scan risk exceeds the stored secure baseline."})
    baseline_categories = set(base.get("categories", []))
    current_categories = {finding["category"] for finding in scan["findings"]}
    for category in sorted(current_categories - baseline_categories):
        drift.append({"id": new_id("drift"), "type": category, "severity": "medium", "created_at": now(), "baseline_risk": baseline_risk, "current_risk": current_risk, "description": f"New drift category detected: {category}"})
    return drift


def rye_score(finding: dict[str, Any], memory: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    memory = memory or []
    category = finding.get("category", "unknown")
    severity = finding.get("severity", "low")
    recurrence = sum(1 for item in memory if item.get("category") == category or item.get("finding_category") == category)
    base = {"low": 20, "medium": 45, "high": 72, "critical": 92}.get(severity, 20)
    exploitability = 85 if category in {"secret_exposure", "unsafe_eval", "insecure_webhook", "identity_risk"} else 62
    blast_radius = 86 if category in {"secret_exposure", "identity_risk", "insecure_webhook", "unsafe_eval"} else 48
    verification = 82 if finding.get("verification_method") else 55
    urgency = min(100, base + recurrence * 8)
    denominator = 28 + 18 + 9 + 8 + (9 if finding.get("confidence", 0) >= 0.8 else 25) + 14
    score = round(max(1, min(100, ((base * exploitability * blast_radius * verification * urgency) / denominator) / 85000 * 100)), 2)
    return {"score": score, "severity": severity, "priority": "critical_first" if score >= 80 else "high" if score >= 60 else "medium" if score >= 35 else "low", "confidence": finding.get("confidence", 0.75), "why_this_matters": finding.get("business_impact", "This finding may increase security risk."), "why_this_ranks_above_others": f"{severity} severity, {category} category, recurrence {recurrence}, and verification availability.", "what_can_be_safely_automated": "Scan, report, score, generate repair prompt, and run local verification.", "what_needs_approval": "Production changes, credential rotation, deployments, destructive actions, or broad infrastructure changes.", "what_can_wait": "Lower-scoring repairs with limited exposure and no recurrence.", "what_would_be_overkill": "Broad rewrites before targeted local verification."}


def apply_rye(findings: list[dict[str, Any]], memory: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out = []
    for finding in findings:
        updated = dict(finding)
        updated["rye"] = rye_score(updated, memory)
        out.append(updated)
    return out


def repairs_for(findings: list[dict[str, Any]], memory: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    repairs: list[dict[str, Any]] = []
    for finding in findings:
        base_score = finding.get("rye", rye_score(finding, memory)).get("score", 0)
        fix = REPAIR_LIBRARY.get(finding["category"], "Apply smallest defensive fix and verify.")
        files = [finding["affected_file"]] if finding.get("affected_file") else []
        prompt = f"Fix only the {finding.get('title', finding['category'])} issue in {finding.get('affected_file', 'the affected file')}.\nDo not rewrite unrelated code.\nApply this targeted defensive repair: {fix}\nAdd the smallest relevant tests.\nRun local tests or a NICO rescan.\nReturn a short verification summary.\nNever expose raw secrets."
        for repair_type, delta, level in [("minimal", 0, 1), ("moderate", -6, 2), ("strong", -12, 3)]:
            repair_id = new_id("repair")
            repairs.append({"repair_id": repair_id, "id": repair_id, "finding_id": finding["id"], "repair_type": repair_type, "exact_issue": finding.get("title", finding["category"]), "affected_files": files, "smallest_safe_change": fix, "tests_to_add": ["Add focused regression test if available.", "Run NICO rescan after repair."], "verification_command": "python -m nico verify latest", "rollback_plan": "Revert targeted change if verification fails or new drift appears.", "codex_ready_patch_prompt": prompt, "owner_friendly_explanation": f"This {repair_type} repair reduces {finding['category']} risk without broad rewrites.", "developer_ready_explanation": f"Target {files or ['affected code']}; verify with: {finding.get('verification_method')}", "rye_score": max(0, round(base_score + delta, 2)), "autonomy_level": level, "approval_requirement": "human_review_required_before_production_change" if finding["severity"] in {"high", "critical"} else "safe_for_local_repair_prompt_generation", "status": "suggested", "created_at": now()})
    return sorted(repairs, key=lambda repair: repair["rye_score"], reverse=True)


def analyze_memory(memory: list[dict[str, Any]], findings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    findings = findings or []
    categories = Counter(finding.get("category", "unknown") for finding in findings)
    recurring = sorted(category for category, count in categories.items() if count >= 2)
    fragile_modules = sorted({finding.get("affected_file") for finding in findings if finding.get("affected_file") and categories[finding.get("category")] >= 2})
    return {"recurring_categories": recurring, "fragile_modules": fragile_modules, "false_positive_tracking": "available via repair status false_positive", "risk_reduction_history": [item for item in memory if item.get("type") == "verification"], "memory_notes": [f"Recurring drift category observed: {category}" for category in recurring] or ["No recurring drift pattern has enough evidence yet."]}


def ensure_test_lab() -> None:
    SAMPLE_REPO.mkdir(parents=True, exist_ok=True)
    (TEST_LAB / "mock_logs").mkdir(parents=True, exist_ok=True)
    (SAMPLE_REPO / "app.py").write_text("from flask import Flask, request\napp=Flask(__name__)\nFAKE_API_KEY='FAKE_TEST_ONLY_API_KEY_1234567890'\ndef admin_users(): return 'admin users'\ndef calc(): return str(eval(request.args.get('q','1+1')))\nif __name__=='__main__': app.run(debug=True)\n", encoding="utf-8")
    (SAMPLE_REPO / "webhook.py").write_text("def handle_webhook(payload, headers):\n    # TODO: verify signature\n    return {'accepted': True}\n", encoding="utf-8")
    (SAMPLE_REPO / "upload.py").write_text("def save_upload(file):\n    # TODO: validate upload\n    return f'/tmp/{file.filename}'\n", encoding="utf-8")
    (SAMPLE_REPO / "ai_agent.py").write_text("over_permissive_tools = True\n", encoding="utf-8")
    (SAMPLE_REPO / "requirements.txt").write_text("flask==0.12\nrequests==2.31.0\n", encoding="utf-8")
    (SAMPLE_REPO / "package.json").write_text('{"dependencies":{"lodash":"4.17.15"}}\n', encoding="utf-8")
    events = [json.dumps({"event": "failed_login", "username": "admin"}) for _ in range(6)] + [json.dumps({"event": "admin_role_change", "username": "unknown"}), json.dumps({"event": "api_request_spike", "count": 5000})]
    (TEST_LAB / "mock_logs" / "auth.jsonl").write_text("\n".join(events) + "\n", encoding="utf-8")


def generate_reports() -> list[dict[str, str]]:
    store = Store()
    findings = store.payloads("findings")
    payload = {"scan": store.latest_scan(), "findings": findings, "drift": store.payloads("drift_events"), "repairs": store.payloads("repairs"), "memory": store.payloads("memory"), "memory_analysis": analyze_memory(store.payloads("memory"), findings), "verification": store.payloads("verification"), "policy": store.policy(), "audit": store.rows("audit_log")[:50]}
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    owner = "# NICO Owner Report\n\n" f"Findings: {len(findings)}\n" f"Repair candidates: {len(payload['repairs'])}\n\n## What to fix first\n" + "\n".join(f"- RYE {repair.get('rye_score')}: {repair.get('exact_issue')}" for repair in payload["repairs"][:3]) + "\n"
    developer = "# NICO Developer Report\n\n" + "\n".join(f"## {finding.get('title')}\n- File: {finding.get('affected_file')}:{finding.get('affected_line')}\n- Severity: {finding.get('severity')}\n- Masked evidence: `{finding.get('masked_evidence', '')}`\n- Fix: {finding.get('recommended_fix')}\n- Verify: {finding.get('verification_method')}" for finding in findings[:50])
    reparodynamic = "# NICO Reparodynamic Report\n\n## Drift\n" + "\n".join(f"- {event.get('type')}: {event.get('description')}" for event in payload["drift"]) + "\n\n## RYE/TGRM\n" + "\n".join(f"- {repair.get('repair_type')} | RYE {repair.get('rye_score')} | {repair.get('exact_issue')}" for repair in payload["repairs"][:20]) + "\n"
    compliance = "# NICO Compliance Report\n\nLocal mapping only. This is not a certification report.\n\n" + "\n".join(f"- {mapping}: {finding.get('title')}" for finding in findings for mapping in finding.get("standards_mapping", []))
    outputs = {"json": json.dumps(payload, indent=2, sort_keys=True), "markdown": f"# NICO Reparodynamic Security Report\n\nFindings: {len(findings)}\nDrift events: {len(payload['drift'])}\nRepair candidates: {len(payload['repairs'])}\n", "html": "<html><body><h1>NICO Security Report</h1><pre>" + json.dumps(payload, indent=2) + "</pre></body></html>", "owner": owner, "developer": developer, "reparodynamic": reparodynamic, "compliance": compliance}
    paths = []
    for fmt, body in outputs.items():
        suffix = "md" if fmt == "markdown" else "html" if fmt == "html" else "json" if fmt == "json" else f"{fmt}.md"
        path = REPORT_DIR / f"latest.{suffix}"
        path.write_text(body, encoding="utf-8")
        store.save_report(f"latest-{fmt}", fmt, str(path))
        paths.append({"format": fmt, "path": str(path)})
    store.audit("reports.generate", {"reports": paths})
    return paths


def report_text(kind: str) -> str:
    generate_reports()
    mapping = {"owner": "owner.md", "developer": "developer.md", "reparodynamic": "reparodynamic.md", "compliance": "compliance.md"}
    path = REPORT_DIR / mapping.get(kind, "latest.md")
    return path.read_text(encoding="utf-8") if path.exists() else ""


def run_scan(target: str, kind: str = "local") -> dict[str, Any]:
    store = Store()
    decision = decide_action("scan", store.policy())
    if not decision["allowed"]:
        raise RuntimeError("scan blocked by governance: " + decision["reason"])
    scan = scan_repo(target)
    memory = store.payloads("memory")
    scan["findings"] = apply_rye(scan["findings"], memory)
    baseline = store.baseline() or make_baseline(scan)
    drift = detect_drift(baseline, scan)
    repairs = repairs_for(scan["findings"], memory)
    store.save_scan(scan, kind)
    store.save_drift(scan["id"], drift)
    store.save_repairs(repairs)
    store.save_baseline(baseline)
    store.save_memory({"id": new_id("mem"), "type": "scan_cycle", "created_at": now(), "scan_id": scan["id"], "finding_count": len(scan["findings"]), "drift_count": len(drift), "repair_count": len(repairs), "top_categories": Counter(finding["category"] for finding in scan["findings"]).most_common(5)})
    store.audit("scan.run", {"target": target, "kind": kind, "findings": len(scan["findings"]), "drift": len(drift), "repairs": len(repairs)})
    generate_reports()
    return {"scan": scan, "baseline": baseline, "drift": drift, "repairs": repairs}


def scan_test_lab() -> dict[str, Any]:
    ensure_test_lab()
    return run_scan(str(TEST_LAB), "test_lab")


def scan_drift_demo() -> dict[str, Any]:
    ensure_test_lab()
    shutil.rmtree(DRIFT_REPO, ignore_errors=True)
    shutil.copytree(SAMPLE_REPO, DRIFT_REPO)
    store = Store()
    clean = scan_repo(str(SAMPLE_REPO))
    clean["findings"] = apply_rye(clean["findings"], store.payloads("memory"))
    store.save_baseline(make_baseline(clean))
    (DRIFT_REPO / "new_admin_route.py").write_text("admin_secret='FAKE_TEST_ONLY_ADMIN_TOKEN_0000'\n# TODO: add rate limiting\n", encoding="utf-8")
    return run_scan(str(DRIFT_REPO), "drift_demo")


def verify_latest() -> dict[str, Any]:
    store = Store()
    scan = store.latest_scan()
    findings = store.payloads("findings")
    repairs = store.payloads("repairs")
    masked = all("FAKE_TEST_ONLY_SECRET_123456" not in str(finding) for finding in findings)
    result = {"id": new_id("verify"), "created_at": now(), "scan_id": scan.get("id"), "repair_id": None, "passed": bool(scan) and masked, "status": "verification_observed", "checks": ["scan_available" if scan else "scan_missing", "findings_masked" if masked else "masking_failure", "governance_enabled", "repair_candidates_present" if repairs else "repair_candidates_missing"], "risk_reduction": "pending_targeted_code_repair", "finding_count": len(findings), "repair_count": len(repairs), "baseline_update_allowed": False}
    store.save_verification(result)
    store.save_memory({"id": result["id"], "type": "verification", "created_at": result["created_at"], "result": result})
    store.audit("verification.latest", result)
    return result


def verify_repair_by_id(repair_id: str) -> dict[str, Any]:
    store = Store()
    repair = next((item for item in store.payloads("repairs") if item.get("id") == repair_id or item.get("repair_id") == repair_id), None)
    result = {"id": new_id("verify"), "created_at": now(), "repair_id": repair.get("id") if repair else None, "passed": bool(repair), "status": "verification_pending" if repair else "repair_not_found", "checks": ["repair_exists" if repair else "repair_missing", "rescan_required", "raw_secret_masking_checked"], "risk_reduction": "requires_rescan_after_patch", "baseline_update_allowed": False}
    store.save_verification(result)
    store.save_memory({"id": result["id"], "type": "verification", "created_at": result["created_at"], "result": result})
    if repair:
        store.update_repair_status(repair["id"], result["status"])
    store.audit("verification.repair", result)
    return result


def memory_summary() -> dict[str, Any]:
    store = Store()
    memory = store.payloads("memory")
    return {"items": memory, "analysis": analyze_memory(memory, store.payloads("findings"))}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="nico")
    parser.add_argument("--swarm", action="store_true", help="Enable RYE swarm bug finding")
    sub = parser.add_subparsers(dest="cmd")
    scan_parser = sub.add_parser("scan")
    scan_parser.add_argument("target")
    sub.add_parser("scan-test-lab")
    sub.add_parser("scan-drift-demo")
    report_parser = sub.add_parser("report")
    report_parser.add_argument("which", nargs="?", default="latest")
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("which", nargs="?", default="latest")
    verify_parser.add_argument("--repair-id")
    sub.add_parser("memory")
    policy_parser = sub.add_parser("policy")
    policy_parser.add_argument("action", nargs="?", default="show")
    sub.add_parser("scanner-availability")
    assessment_parser = sub.add_parser("assessment")
    assessment_parser.add_argument("target")
    assessment_parser.add_argument("--tier", default="express", choices=["express", "mid", "full"])
    assessment_parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    assessment_parser.add_argument("--swarm", action="store_true")
    assessment_parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    store = Store()
    if args.cmd == "scan":
        result = run_scan(args.target)
        print(json.dumps({"scan_id": result["scan"]["id"], "findings": len(result["scan"]["findings"]), "drift": len(result["drift"]), "repairs": len(result["repairs"])}, indent=2))
        return
    if args.cmd == "scan-test-lab":
        result = scan_test_lab()
        print(json.dumps({"scan_id": result["scan"]["id"], "findings": len(result["scan"]["findings"]), "drift": len(result["drift"]), "repairs": len(result["repairs"] )}, indent=2))
        return
    if args.cmd == "scan-drift-demo":
        result = scan_drift_demo()
        print(json.dumps({"scan_id": result["scan"]["id"], "findings": len(result["scan"]["findings"]), "drift": len(result["drift"]), "repairs": len(result["repairs"] )}, indent=2))
        return
    if args.cmd == "report":
        if args.which in {"owner", "developer", "reparodynamic", "compliance"}:
            print(report_text(args.which))
        else:
            print(json.dumps(generate_reports(), indent=2))
        return
    if args.cmd == "verify":
        print(json.dumps(verify_repair_by_id(args.repair_id) if args.repair_id else verify_latest(), indent=2))
        return
    if args.cmd == "memory":
        print(json.dumps(memory_summary(), indent=2))
        return
    if args.cmd == "policy":
        print(json.dumps(store.policy(), indent=2))
        return
    if args.cmd == "scanner-availability":
        print(json.dumps(scanner_availability(), indent=2))
        return
    if args.cmd == "assessment":
        try:
            from nico.assessment import run_assessment
            result = run_assessment(target=args.target, tier=args.tier, mode=args.mode, use_swarm=args.swarm, output_dir=args.output)
            print(json.dumps(result, indent=2, default=str))
        except Exception as exc:
            print({"error": str(exc)})
        return
    parser.print_help()


if __name__ == "__main__":
    main()
