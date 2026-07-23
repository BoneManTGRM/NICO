from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/security-audit.yml"
PACKAGE = ROOT / "apps/web/package.json"
CONFIG = ROOT / "apps/web/next.config.js"


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
    package = PACKAGE.read_text(encoding="utf-8")
    config = CONFIG.read_text(encoding="utf-8")
    assert '"next": "16.2.11"' in package
    assert '"sharp": "0.35.0"' in package
    assert "unoptimized: true" in config
