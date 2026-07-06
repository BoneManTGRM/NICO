from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_requirements_include_core_scanner_tools():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "pip-audit" in requirements
    assert "bandit" in requirements
    assert "semgrep" in requirements


def test_dockerfile_installs_worker_runtime_dependencies():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "git" in dockerfile
    assert "nodejs" in dockerfile
    assert "npm" in dockerfile
    assert "npm install -g eslint" in dockerfile


def test_worker_tooling_docs_keep_unavailable_claims_honest():
    doc = (ROOT / "docs" / "WORKER_TOOLING_V6.md").read_text(encoding="utf-8")
    assert "Unavailable scanner evidence is not treated as a clean result" in doc
    assert "Human review remains required" in doc
