"""Dependency Audit Module (Phase 2)

Basic local dependency detection and hygiene analysis.
No external vulnerability scanning yet (requires tools like pip-audit, npm audit).
"""

from pathlib import Path

KNOWN_RISKY = {
    "flask==0.12": "Very old Flask with known vulnerabilities",
    "lodash@4.17.15": "Known vulnerable lodash version",
}


def audit_dependencies(target: str) -> dict:
    result = {
        "target": target,
        "status": "limited",
        "dependencies": [],
        "risky_dependencies": [],
        "limitations": []
    }

    path = Path(target)
    if not path.exists():
        result["limitations"].append("Target path does not exist")
        return result

    # Detect common dependency files
    dep_files = []
    for pattern in ["requirements.txt", "pyproject.toml", "package.json", "Pipfile", "poetry.lock"]:
        matches = list(path.rglob(pattern))
        dep_files.extend([str(m) for m in matches])

    if not dep_files:
        result["limitations"].append("No common dependency files found (requirements.txt, package.json, etc.)")
        return result

    result["dependencies"] = dep_files

    # Very basic static check for known risky versions
    for dep_file in dep_files:
        try:
            content = Path(dep_file).read_text(encoding="utf-8", errors="ignore")
            for risky, reason in KNOWN_RISKY.items():
                if risky in content:
                    result["risky_dependencies"].append({
                        "file": dep_file,
                        "dependency": risky,
                        "reason": reason
                    })
        except Exception:
            continue

    if result["risky_dependencies"]:
        result["status"] = "completed_with_findings"
    else:
        result["status"] = "completed"

    result["limitations"].append("Static analysis only. No live vulnerability database check performed.")
    if not any(tool in ["pip-audit", "npm audit"] for tool in []):  # placeholder
        result["limitations"].append("Install pip-audit or npm audit for better results")

    return result
