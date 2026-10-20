from __future__ import annotations

import json
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/security-audit.yml"
PROVIDER_ACCEPTANCE = ROOT / ".github/workflows/provider-live-acceptance.yml"
HARDENING_ACCEPTANCE = ROOT / ".github/workflows/post-release-hardening-acceptance.yml"
PACKAGE = ROOT / "apps/web/package.json"
CONFIG = ROOT / "apps/web/next.config.js"
REQUIREMENTS = ROOT / "requirements.txt"
PYPROJECT = ROOT / "pyproject.toml"


def _semver_core(version: str) -> tuple[int, int, int]:
    core = version.split("-", 1)[0]
    parts = core.split(".")
    assert len(parts) >= 3, f"Expected a three-part semantic version, got {version!r}"
    return tuple(int(part) for part in parts[:3])


def test_security_workflow_uses_pinned_isolated_scanners_and_no_latest_installs() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "semgrep==1.170.0" in source
    assert "scripts/install_hosted_scanner_binaries.py" in source
    assert 'NICO_SCANNER_INSTALL_STRICT: "true"' in source
    assert "@latest" not in source
    assert "npm ci --ignore-scripts --no-audit --no-fund" in source


def test_security_evidence_is_uploaded_before_fail_closed_enforcement() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    upload = "Upload audit evidence before enforcement"
    enforce = "Require complete clean security evidence"
    assert upload in source
    assert enforce in source
    assert source.index(upload) < source.index(enforce)
    assert "python scripts/security_audit_gate.py --enforce" in source


def test_frontend_dependency_override_removes_vulnerable_image_optimizer_path() -> None:
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    config = CONFIG.read_text(encoding="utf-8")
    next_version = package["dependencies"]["next"]
    assert _semver_core(next_version) >= (16, 2, 11)
    # GHSA-wq5f-xc86-pv6w affects Sharp <0.35.5, including the former pin.
    sharp_version = package["overrides"]["sharp"]
    assert _semver_core(sharp_version) >= (0, 35, 5)
    lock = json.loads((PACKAGE.parent / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/sharp"]["version"] == sharp_version
    assert "unoptimized: true" in config


def test_pypdf_security_floor_excludes_cve_2026_71852_affected_pin() -> None:
    requirements = {
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    pinned_pypdf = next(
        requirement.split("==", 1)[1]
        for requirement in requirements
        if requirement.startswith("pypdf==")
    )
    assert _semver_core(pinned_pypdf) >= (6, 15, 0)
    assert "pypdf==6.14.2" not in requirements
    assert '"pypdf>=6.15.0,<7"' in pyproject
    assert '"pypdf>=6.14.2,<7"' not in pyproject


def test_pillow_security_floor_and_python_support_are_consistent() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    python_versions = SpecifierSet(project["requires-python"])
    assert "3.10" not in python_versions
    assert "3.11" in python_versions
    pillow = next(Requirement(value) for value in project["dependencies"]
                  if Requirement(value).name.lower() == "pillow")
    assert pillow.marker is None  # No installation path may bypass the floor.
    assert "12.3.0" not in pillow.specifier
    assert "13.0.0" in pillow.specifier
    assert str(pillow.specifier) == "<14,>=13.0.0"
    assert "pillow==13.0.0" in REQUIREMENTS.read_text().splitlines()
    assert "Python 3.11 or newer" in (ROOT / "docs/LOCAL_DEVELOPMENT.md").read_text()


def test_ci_runs_pdf_regressions_under_verified_pillow_version() -> None:
    workflow = (ROOT / ".github/workflows/nico-ci.yml").read_text()
    shards = workflow.split("  test_shards:", 1)[1].split("  test:\n", 1)[0]
    assert "pip install -r requirements.txt" in shards
    assert "assert version('Pillow') == '13.0.0'" in shards
    assert shards.index("assert version('Pillow')") < shards.index("- name: Run isolated test files")
    assert 'Path("tests").rglob("test_*.py")' in shards
    assert "set(assigned) != set(files)" in shards
    for filename in ("test_scorecard_cell_layout.py", "test_client_pdf_compose_v2.py",
                     "test_pdf_cap_failure_diagnostics.py",
                     "test_pillow_reportlab_image_compatibility.py"):
        assert (ROOT / "tests" / filename).is_file()
    assert "poppler-utils" in shards
    assert "pip-audit -r requirements.txt" in WORKFLOW.read_text()


def test_provider_dispatch_inputs_are_passed_through_environment() -> None:
    source = PROVIDER_ACCEPTANCE.read_text(encoding="utf-8")
    assert "ACCEPTANCE_PROVIDER: ${{ inputs.provider }}" in source
    assert "ACCEPTANCE_REPOSITORY: ${{ inputs.repository }}" in source
    assert "ACCEPTANCE_REVISION: ${{ inputs.revision }}" in source
    assert '--provider "${ACCEPTANCE_PROVIDER}"' in source
    assert '--repository "${ACCEPTANCE_REPOSITORY}"' in source
    assert '--revision "${ACCEPTANCE_REVISION}"' in source
    assert "--provider '${{ inputs.provider }}'" not in source
    assert "--repository '${{ inputs.repository }}'" not in source
    assert "--revision '${{ inputs.revision }}'" not in source
    assert "test '${{ steps.acceptance.outcome }}'" not in source


def test_hardening_dispatch_inputs_are_passed_through_environment() -> None:
    source = HARDENING_ACCEPTANCE.read_text(encoding="utf-8")
    assert "EXPECTED_SHA: ${{ inputs.expected_sha }}" in source
    assert '--expected-sha "${EXPECTED_SHA}"' in source
    assert "--expected-sha '${{ inputs.expected_sha }}'" not in source
    assert "test '${{ steps.acceptance.outcome }}'" not in source
