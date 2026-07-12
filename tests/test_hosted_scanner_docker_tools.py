from pathlib import Path


def test_dockerfile_installs_hosted_scanner_tools():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "pip install --no-cache-dir pip-audit bandit semgrep coverage" in dockerfile
    assert "npm install -g eslint typescript" in dockerfile
    assert "install_hosted_scanner_binaries.py" in dockerfile
    assert "NICO_ENABLE_HOSTED_SCANNER_AUTORUN=true" in dockerfile
    assert "NICO_ALLOW_PROJECT_COMMANDS=true" in dockerfile
    assert "USER nico" in dockerfile


def test_dockerfile_keeps_dependency_install_scripts_disabled_and_reproducible():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert "npm ci --ignore-scripts --no-audit --no-fund" in dockerfile
    assert "npm install --legacy-peer-deps" not in dockerfile


def test_hosted_scanner_binary_installer_targets_missing_yellow_section_tools():
    installer = Path("scripts/install_hosted_scanner_binaries.py").read_text(encoding="utf-8")

    assert "google/osv-scanner" in installer
    assert "gitleaks/gitleaks" in installer
    assert "trufflesecurity/trufflehog" in installer
    assert "osv-scanner" in installer
    assert "gitleaks" in installer
    assert "trufflehog" in installer


def test_hosted_scanner_binary_installer_is_best_effort_by_default():
    installer = Path("scripts/install_hosted_scanner_binaries.py").read_text(encoding="utf-8")

    assert 'NICO_SCANNER_INSTALL_STRICT", "false"' in installer
    assert "warning: could not install" in installer
    assert "if STRICT_INSTALL" in installer
