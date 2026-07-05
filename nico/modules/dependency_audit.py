"""Dependency Audit Module (Phase 3)

Static detection + optional real vulnerability scanning via pip-audit and npm audit.
"""

import json
import shutil
import subprocess
from pathlib import Path


KNOWN_RISKY = {
    "flask==0.12": "Very old Flask with known vulnerabilities",
    "lodash@4.17.15": "Known vulnerable lodash version",
}


def _run_pip_audit(target_dir: Path) -> list[dict]:
    if not shutil.which("pip-audit"):
        return []
    try:
        cmd = ["pip-audit", "--format", "json", "--path", str(target_dir)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode not in (0, 1):  # 1 = vulnerabilities found is still success
            return []
        data = json.loads(proc.stdout or "[]")
        vulns = []
        for item in data:
            for vuln in item.get("vulns", []):
                vulns.append({
                    "dependency": f"{item.get('name')}=={item.get('version')}",
                    "file": "requirements / pip",
                    "reason": f"{vuln.get('id')}: {vuln.get('description', '')[:120]}",
                    "severity": vuln.get("severity", "unknown").lower(),
                })
        return vulns
    except Exception:
        return []


def _run_npm_audit(target_dir: Path) -> list[dict]:
    if not shutil.which("npm"):
        return []
    lockfile = target_dir / "package-lock.json"
    if not lockfile.exists():
        return []
    try:
        cmd = ["npm", "audit", "--json"]
        proc = subprocess.run(cmd, cwd=target_dir, capture_output=True, text=True, timeout=60)
        if proc.returncode not in (0, 1):
            return []
        data = json.loads(proc.stdout or "{}")
        vulns = []
        vulnerabilities = data.get("vulnerabilities", {})
        for name, info in vulnerabilities.items():
            via = info.get("via", [{}])[0] if info.get("via") else {}
            vulns.append({
                "dependency": name,
                "file": "package.json / npm",
                "reason": f"{via.get('title', via.get('url', ''))}",
                "severity": info.get("severity", "unknown").lower(),
            })
        return vulns
    except Exception:
        return []


def audit_dependencies(target: str) -> dict:
    result = {
        "target": target,
        "status": "limited",
        "dependencies": [],
        "risky_dependencies": [],
        "vulnerabilities_found": 0,
        "critical_count": 0,
        "high_count": 0,
        "limitations": []
    }

    path = Path(target)
    if not path.exists():
        result["limitations"].append("Target path does not exist")
        return result

    # Detect dependency files
    dep_files = []
    for pattern in ["requirements.txt", "pyproject.toml", "package.json", "Pipfile", "poetry.lock"]:
        matches = list(path.rglob(pattern))
        dep_files.extend([str(m) for m in matches])

    if not dep_files:
        result["limitations"].append("No common dependency files found")
        return result

    result["dependencies"] = dep_files

    # Static risky version check (fallback)
    for dep_file in dep_files:
        try:
            content = Path(dep_file).read_text(encoding="utf-8", errors="ignore")
            for risky, reason in KNOWN_RISKY.items():
                if risky in content:
                    result["risky_dependencies"].append({
                        "file": dep_file,
                        "dependency": risky,
                        "reason": reason,
                        "severity": "high",
                    })
        except Exception:
            continue

    # Real vulnerability scanning
    pip_vulns = _run_pip_audit(path)
    npm_vulns = _run_npm_audit(path)

    all_vulns = pip_vulns + npm_vulns
    result["risky_dependencies"].extend(all_vulns)
    result["vulnerabilities_found"] = len(all_vulns)

    for v in all_vulns:
        sev = v.get("severity", "")
        if sev == "critical":
            result["critical_count"] += 1
        elif sev == "high":
            result["high_count"] += 1

    if result["risky_dependencies"] or result["vulnerabilities_found"] > 0:
        result["status"] = "completed_with_findings"
    else:
        result["status"] = "completed"

    result["limitations"].append("Real vulnerability data from pip-audit/npm audit when available.")
    if not shutil.which("pip-audit"):
        result["limitations"].append("pip-audit not installed (recommended for Python projects)")
    if not shutil.which("npm"):
        result["limitations"].append("npm not available (recommended for Node.js projects)")

    return result
