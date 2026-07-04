"""CI/CD Audit Module (Phase 2)

Basic static analysis of CI/CD configuration and release process.
"""

from pathlib import Path


def audit_cicd(target: str) -> dict:
    result = {
        "target": target,
        "status": "limited",
        "workflows": [],
        "has_ci": False,
        "limitations": []
    }

    path = Path(target)
    if not path.exists():
        result["limitations"].append("Target does not exist")
        return result

    # Look for common CI/CD files
    ci_files = []
    for pattern in [".github/workflows/*.yml", ".github/workflows/*.yaml", "Dockerfile", "docker-compose*.yml", ".gitlab-ci.yml", "Jenkinsfile"]:
        matches = list(path.glob(pattern)) if "*" in pattern else list(path.rglob(pattern))
        ci_files.extend([str(m) for m in matches])

    if ci_files:
        result["has_ci"] = True
        result["workflows"] = ci_files
        result["status"] = "completed"
    else:
        result["limitations"].append("No common CI/CD configuration files found (.github/workflows, Dockerfile, etc.)")

    result["limitations"].append("Static file detection only. No workflow run history or pass/fail rates available.")
    result["limitations"].append("Real CI/CD quality requires GitHub token + workflow run data.")

    return result
