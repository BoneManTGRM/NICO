from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_requirements_include_core_python_scanners_without_semgrep_runtime_conflict():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "pip-audit" in requirements
    assert "bandit" in requirements
    assert "semgrep" not in requirements.lower()
    assert '"semgrep' not in pyproject.lower()


def test_dockerfile_installs_worker_runtime_dependencies_and_isolates_semgrep():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "git" in dockerfile
    assert "nodejs" in dockerfile
    assert "npm" in dockerfile
    assert "npm install -g eslint" in dockerfile
    assert "NICO_SEMGREP_HOME=/opt/nico-tools/semgrep" in dockerfile
    assert 'python -m venv "$NICO_SEMGREP_HOME"' in dockerfile
    assert '"semgrep==${NICO_SEMGREP_VERSION}"' in dockerfile
    assert 'ln -s "$NICO_SEMGREP_HOME/bin/semgrep" /usr/local/bin/semgrep' in dockerfile
    assert "pip install --no-cache-dir pip-audit bandit semgrep" not in dockerfile


def test_worker_tooling_docs_keep_unavailable_claims_honest():
    doc = (ROOT / "docs" / "WORKER_TOOLING_V6.md").read_text(encoding="utf-8")
    assert "Unavailable scanner evidence is not treated as a clean result" in doc
    assert "Human review remains required" in doc
