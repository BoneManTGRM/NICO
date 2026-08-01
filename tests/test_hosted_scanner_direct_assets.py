from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import install_hosted_scanner_binaries as installer


def _tool(name: str) -> dict:
    return next(item for item in installer.TOOLS if item["name"] == name)


def test_default_scanners_have_tokenless_direct_asset_contracts() -> None:
    osv = _tool("osv-scanner")
    gitleaks = _tool("gitleaks")
    trufflehog = _tool("trufflehog")

    assert installer._asset_name(osv["direct_asset_template"], osv["default_tag"]) == "osv-scanner_linux_amd64"
    assert installer._asset_name(gitleaks["direct_asset_template"], gitleaks["default_tag"]) == "gitleaks_8.30.1_linux_x64.tar.gz"
    assert installer._asset_name(trufflehog["direct_asset_template"], trufflehog["default_tag"]) == "trufflehog_3.95.0_linux_amd64.tar.gz"

    for tool in installer.TOOLS:
        url = installer._direct_asset_url(
            tool["repository"],
            tool["default_tag"],
            installer._asset_name(tool["direct_asset_template"], tool["default_tag"]),
        )
        assert url.startswith("https://github.com/")
        assert "/releases/download/" in url
        assert "api.github.com" not in url

    assert len(osv["direct_sha256"]) == 64
    assert len(gitleaks["direct_sha256"]) == 64
    assert trufflehog["checksum_manifest_template"] == "trufflehog_{version}_checksums.txt"


def test_checksum_manifest_requires_exact_asset_identity() -> None:
    asset = "trufflehog_3.95.0_linux_amd64.tar.gz"
    digest = "a" * 64
    payload = f"{digest}  trufflehog_3.95.0_darwin_amd64.tar.gz\n{digest}  {asset}\n".encode()

    assert installer._parse_checksum_manifest(payload, asset) == digest
    with pytest.raises(RuntimeError, match="omitted"):
        installer._parse_checksum_manifest(payload, "trufflehog_3.95.0_linux_arm64.tar.gz")


def test_direct_asset_sha256_verification_fails_closed(tmp_path: Path) -> None:
    artifact = tmp_path / "scanner"
    artifact.write_bytes(b"verified scanner release asset")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()

    installer._verify_sha256(artifact, expected)
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        installer._verify_sha256(artifact, "0" * 64)


def test_default_install_path_does_not_call_release_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    tool = dict(_tool("osv-scanner"))
    monkeypatch.setattr(installer, "INSTALL_DIR", tmp_path / "bin")

    def forbidden_release(*args, **kwargs):
        raise AssertionError("default pinned installation must not query the GitHub Releases API")

    def fake_direct(selected: dict, tag: str) -> None:
        assert selected == tool
        assert tag == tool["default_tag"]
        target = installer.INSTALL_DIR / tool["binary"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"binary")
        target.chmod(0o755)

    monkeypatch.setattr(installer, "_release", forbidden_release)
    monkeypatch.setattr(installer, "_install_direct_pinned_asset", fake_direct)

    assert installer.install_tool(tool) == tool["default_tag"]
