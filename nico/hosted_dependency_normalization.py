from __future__ import annotations

import re
from typing import Any


def normalize_requirement_name(raw_name: str) -> str:
    """Return the package name without PEP 508 extras.

    OSV package names must not include extras such as PyJWT[crypto]. Extras change
    install behavior but are not part of the package identity.
    """

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
    """Patch hosted_assessment dependency parsing without changing report semantics.

    This keeps the hosted Express report honest: it can still disclose OSV findings,
    but it must query OSV with normalized exact package identities rather than PEP
    extras or range fragments that create misleading vulnerability records.
    """

    from nico import hosted_assessment

    hosted_assessment.parse_requirements = parse_requirements_normalized

    original_query_osv = hosted_assessment.query_osv

    def query_osv_normalized(dependencies: list[dict[str, str]]) -> tuple[list[str], list[str]]:
        normalized = exact_osv_dependencies(dependencies)
        if not normalized:
            return [], ["OSV lookup skipped because no exact normalized dependency versions were available from the inspected manifests."]
        return original_query_osv(normalized)

    hosted_assessment.query_osv = query_osv_normalized
