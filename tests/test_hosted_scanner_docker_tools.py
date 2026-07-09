from pathlib import Path


def test_dockerfile_installs_hosted_scanner_tools():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "pip install --no-cache-dir pip-audit bandit semgrep coverage" in dockerfile
    assert "npm install -g eslint typescript" in dockerfile
    assert "install_hosted_scanner_binaries.py" in dockerfile
    assert "NICO_ENABLE_HOSTED_SCANNER_AUTORUN=true" in dockerfile
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in dockerfile


def test_dockerfile_keeps_project_install_scripts_disabled():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "npm install --legacy-peer-deps --ignore-scripts" in dockerfile
    assert "npm ci" not in dockerfile


def test_hosted_scanner_binary_installer_targets_missing_yellow_section_tools():
    installer = Path("scripts/install_hosted_scanner_binaries.py").read_text(encoding="utf-8")

    assert "google/osv-scanner" in installer
    assert "gitleaks/gitleaks" in installer
    assert "trufflesecurity/trufflehog" in installer
    assert "osv-scanner" in installer
    assert "gitleaks" in installer
    assert "trufflehog" in installer
