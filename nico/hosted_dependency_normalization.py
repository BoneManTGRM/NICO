from __future__ import annotations

import re
from typing import Any


def normalize_requirement_name(raw_name: str) -> str:
    """Return the package name without PEP 508 extras."""

    return re.sub(r"\[[^\]]+\]", "", str(raw_name or "")).strip()


def parse_requirement_line(raw_line: str) -> dict[str, str] | None:
    line = raw_line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        return None
    match = re.match(
        r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(==|~=|>=|<=|>|<)?\s*([^;#\s]+)?",
        line,
    )
    if not match:
        return None
    name, operator, version = match.groups()
    version = str(version or "").strip()
    if version.startswith("["):
        version = ""
    return {
        "name": normalize_requirement_name(name),
        "operator": operator or "",
        "version": version,
        "ecosystem": "PyPI",
        "source": "requirements.txt",
    }


def parse_requirements_normalized(text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for line in text.splitlines():
        item = parse_requirement_line(line)
        if item and item.get("name"):
            deps.append(item)
    return deps


def exact_osv_dependencies(dependencies: list[dict[str, Any]]) -> list[dict[str, str]]:
    exact: list[dict[str, str]] = []
    for dep in dependencies:
        name = normalize_requirement_name(str(dep.get("name") or ""))
        version = str(dep.get("version") or "").strip()
        operator = str(dep.get("operator") or "").strip()
        ecosystem = str(dep.get("ecosystem") or "").strip() or "PyPI"
        if not name or not version or version in {"*", "latest"}:
            continue
        if version.startswith("[") or any(marker in version for marker in [">", "<", "=", "[", "]", " "]):
            continue
        if operator and operator != "==":
            continue
        exact.append({"name": name, "version": version, "ecosystem": ecosystem})
    return exact


def patch_hosted_assessment_dependency_parsing() -> None:
    """Patch hosted assessment dependency parsing and OSV queries.

    This is intentionally idempotent. It also wraps run_github_assessment so a
    long-lived hosted process cannot keep using an older unnormalized parser.
    """

    from nico import hosted_assessment

    original_query_osv = getattr(hosted_assessment, "_nico_original_query_osv", None)
    if original_query_osv is None:
        original_query_osv = hosted_assessment.query_osv
        hosted_assessment._nico_original_query_osv = original_query_osv

    original_run = getattr(hosted_assessment, "_nico_original_run_github_assessment", None)
    if original_run is None:
        original_run = hosted_assessment.run_github_assessment
        hosted_assessment._nico_original_run_github_assessment = original_run

    def query_osv_normalized(dependencies: list[dict[str, str]]) -> tuple[list[str], list[str]]:
        normalized = exact_osv_dependencies(dependencies)
        if not normalized:
            return [], ["OSV lookup skipped because no exact normalized dependency versions were available from the inspected manifests."]
        return original_query_osv(normalized)

    def run_github_assessment_normalized(request: dict[str, Any]) -> dict[str, Any]:
        hosted_assessment.parse_requirements = parse_requirements_normalized
        hosted_assessment.query_osv = query_osv_normalized
        return original_run(request)

    hosted_assessment.parse_requirements = parse_requirements_normalized
    hosted_assessment.query_osv = query_osv_normalized
    hosted_assessment.run_github_assessment = run_github_assessment_normalized
