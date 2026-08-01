from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.request import Request

import pytest

from scripts import install_hosted_scanner_binaries as installer


def _tool(name: str) -> dict:
    return next(item for item in installer.TOOLS if item["name"] == name)


def test_pinned_linux_assets_do_not_require_release_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    expected = {
        "osv-scanner": (
            "osv-scanner_linux_amd64",
            "https://github.com/google/osv-scanner/releases/download/v2.3.8/osv-scanner_linux_amd64",
        ),
        "gitleaks": (
            "gitleaks_8.30.1_linux_x64.tar.gz",
            "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_x64.tar.gz",
        ),
        "trufflehog": (
            "trufflehog_3.95.0_linux_amd64.tar.gz",
            "https://github.com/trufflesecurity/trufflehog/releases/download/v3.95.0/trufflehog_3.95.0_linux_amd64.tar.gz",
        ),
    }

    for name, (asset_name, asset_url) in expected.items():
        tool = _tool(name)
        tag = installer._release_tag(tool)
        assert installer._asset_name(tool, tag, "asset_name_template") == asset_name
        assert installer._asset_url(tool["repository"], tag, asset_name) == asset_url
        request: Request = installer._request(asset_url)
        assert request.get_header("Authorization") is None
        assert "api.github.com" not in request.full_url


def test_authenticated_download_remains_ephemeral(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ephemeral-token")
    request = installer._request(
        "https://github.com/google/osv-scanner/releases/download/v2.3.8/osv-scanner_linux_amd64"
    )
    assert request.get_header("Authorization") == "Bearer ephemeral-token"
    assert "ephemeral-token" not in request.full_url


def test_checksum_manifest_requires_exact_asset_identity() -> None:
    manifest = (
        b"0" * 64
        + b"  unrelated.tar.gz\n"
        + b"1" * 64
        + b" *trufflehog_3.95.0_linux_amd64.tar.gz\n"
    )
    assert installer._checksum_from_manifest(
        manifest,
        "trufflehog_3.95.0_linux_amd64.tar.gz",
    ) == "1" * 64
    with pytest.raises(RuntimeError, match="did not contain"):
        installer._checksum_from_manifest(manifest, "other.tar.gz")


def test_tampered_scanner_asset_is_rejected(tmp_path: Path) -> None:
    artifact = tmp_path / "scanner"
    artifact.write_bytes(b"tampered")
    expected = hashlib.sha256(b"expected").hexdigest()
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        installer._verify_sha256(artifact, expected)


def test_all_pinned_tools_have_bounded_release_metadata() -> None:
    for tool in installer.TOOLS:
        tag = installer._release_tag(tool)
        asset_name = installer._asset_name(tool, tag, "asset_name_template")
        assert installer.SAFE_ASSET_NAME.fullmatch(asset_name)
        assert tool["repository"].count("/") == 1
        assert tool.get("asset_sha256") or tool.get("checksum_name_template")
