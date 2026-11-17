from pathlib import Path
import json
import tomllib

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]


def assert_shared_dependencies_exclude_semgrep(requirements: str, pyproject: str) -> None:
    shared = [
        Requirement(line.split(" #", 1)[0].strip())
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    names = {canonicalize_name(item.name) for item in shared}
    assert {"pip-audit", "bandit"} <= names
    document = tomllib.loads(pyproject)
    project = document.get("project", {})
    entries = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        entries.extend(group)
    entries.extend(document.get("build-system", {}).get("requires", []))
    names.update(canonicalize_name(Requirement(entry).name) for entry in entries)
    assert "semgrep" not in names, "Semgrep must remain isolated from shared dependencies"


def test_shared_requirements_include_core_python_scanners_without_semgrep_runtime_conflict():
    assert_shared_dependencies_exclude_semgrep(
        (ROOT / "requirements.txt").read_text(encoding="utf-8"),
        (ROOT / "pyproject.toml").read_text(encoding="utf-8"),
    )


def test_semgrep_package_resource_is_not_a_dependency():
    assert_shared_dependencies_exclude_semgrep(
        "pip-audit==2.10.1\nbandit==1.9.4\n",
        '[project]\ndependencies = []\n'
        '[tool.setuptools.package-data]\nnico = ["semgrep_rules_v1.yml"]\n',
    )


@pytest.mark.parametrize("location", ["requirements", "runtime", "optional", "build"])
@pytest.mark.parametrize("dependency", ["semgrep==1.185.0", "Semgrep[extra]>=1; python_version < '3.0'"])
def test_real_semgrep_dependency_is_rejected(location, dependency):
    requirements = "pip-audit==2.10.1\nbandit==1.9.4\n"
    document = '[tool.setuptools.package-data]\nnico = ["semgrep_rules_v1.yml"]\n'
    if location == "requirements":
        requirements += dependency + "\n"
    else:
        section, key = {
            "runtime": ("project", "dependencies"),
            "optional": ("project.optional-dependencies", "scanners"),
            "build": ("build-system", "requires"),
        }[location]
        document += f"[{section}]\n{key} = [{json.dumps(dependency)}]\n"
    with pytest.raises(AssertionError, match="Semgrep must remain isolated"):
        assert_shared_dependencies_exclude_semgrep(requirements, document)


def test_dockerfile_installs_worker_runtime_dependencies_and_isolates_semgrep():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "git" in dockerfile
    assert "FROM node:24-bookworm-slim AS node-runtime" in dockerfile
    assert "COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node" in dockerfile
    assert "COPY --from=node-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules" in dockerfile
    assert "ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm" in dockerfile
    assert "ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx" in dockerfile
    assert "ARG NICO_ESLINT_VERSION=9.39.3" in dockerfile
    assert "ARG NICO_TYPESCRIPT_VERSION=6.0.3" in dockerfile
    assert '"eslint@${NICO_ESLINT_VERSION}"' in dockerfile
    assert '"typescript@${NICO_TYPESCRIPT_VERSION}"' in dockerfile
    assert "NICO_SEMGREP_HOME=/opt/nico-tools/semgrep" in dockerfile
    assert 'python -m venv "$NICO_SEMGREP_HOME"' in dockerfile
    assert '"semgrep==${NICO_SEMGREP_VERSION}"' in dockerfile
    assert 'ln -s "$NICO_SEMGREP_HOME/bin/semgrep" /usr/local/bin/semgrep' in dockerfile
    assert "pip install --no-cache-dir pip-audit bandit semgrep" not in dockerfile


def test_worker_tooling_docs_keep_unavailable_claims_honest():
    doc = (ROOT / "docs" / "WORKER_TOOLING_V6.md").read_text(encoding="utf-8")
    assert "Unavailable scanner evidence is not treated as a clean result" in doc
    assert "Human review remains required" in doc
