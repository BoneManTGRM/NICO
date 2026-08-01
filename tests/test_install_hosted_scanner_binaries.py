from __future__ import annotations

import hashlib
import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import install_hosted_scanner_binaries as installer


def test_validated_https_url_rejects_untrusted_schemes_hosts_and_api() -> None:
    direct = (
        "https://github.com/google/osv-scanner/releases/download/"
        "v2.3.8/osv-scanner_linux_amd64"
    )
    assert installer._validated_https_url(direct) == direct
    with pytest.raises(RuntimeError):
        installer._validated_https_url(
            "https://api.github.com/repos/google/osv-scanner/releases/tags/v2.3.8"
        )
    with pytest.raises(RuntimeError):
        installer._validated_https_url("file:///tmp/scanner")
    with pytest.raises(RuntimeError):
        installer._validated_https_url("https://example.com/scanner.tar.gz")
    with pytest.raises(RuntimeError):
        installer._validated_https_url("https://user:password@github.com/tool")


def test_default_scanner_release_tags_are_explicit_and_overrideable(monkeypatch) -> None:
    defaults = {str(tool["name"]): installer._release_tag(tool) for tool in installer.TOOLS}

    assert defaults == {
        "osv-scanner": "v2.3.8",
        "gitleaks": "v8.30.1",
        "trufflehog": "v3.95.0",
    }

    monkeypatch.setenv("NICO_GITLEAKS_VERSION", "v8.30.0")
    gitleaks = next(tool for tool in installer.TOOLS if tool["name"] == "gitleaks")
    assert installer._release_tag(gitleaks) == "v8.30.0"

    monkeypatch.setenv("NICO_GITLEAKS_VERSION", "../../latest")
    with pytest.raises(RuntimeError):
        installer._release_tag(gitleaks)


def test_direct_asset_identity_uses_exact_repository_tag_and_name() -> None:
    assert installer._asset_url(
        "google/osv-scanner",
        "v2.3.8",
        "osv-scanner_linux_amd64",
    ) == (
        "https://github.com/google/osv-scanner/releases/download/"
        "v2.3.8/osv-scanner_linux_amd64"
    )
    with pytest.raises(RuntimeError):
        installer._asset_url(
            "google/osv-scanner",
            "../../latest",
            "osv-scanner_linux_amd64",
        )
    with pytest.raises(RuntimeError):
        installer._asset_url(
            "google/osv-scanner",
            "v2.3.8",
            "../scanner",
        )


def test_safe_zip_extraction_blocks_traversal_and_symlinks(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as zf:
        zf.writestr("../escape", b"bad")
    with pytest.raises(RuntimeError):
        installer._safe_extract_zip(traversal, tmp_path / "out-traversal")

    symlink = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("scanner-link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, "w") as zf:
        zf.writestr(info, "target")
    with pytest.raises(RuntimeError):
        installer._safe_extract_zip(symlink, tmp_path / "out-symlink")


def test_safe_tar_extraction_allows_regular_file_and_blocks_links(tmp_path: Path) -> None:
    archive = tmp_path / "scanner.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        payload = b"binary"
        regular = tarfile.TarInfo("bin/scanner")
        regular.size = len(payload)
        tf.addfile(regular, io.BytesIO(payload))
    output = tmp_path / "out"
    installer._safe_extract_tar(archive, output)
    assert (output / "bin" / "scanner").read_bytes() == b"binary"

    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as tf:
        item = tarfile.TarInfo("scanner-link")
        item.type = tarfile.SYMTYPE
        item.linkname = "/tmp/target"
        tf.addfile(item)
    with pytest.raises(RuntimeError):
        installer._safe_extract_tar(linked, tmp_path / "out-linked")


def test_bounded_download_rejects_oversized_payload() -> None:
    with pytest.raises(RuntimeError):
        installer._read_bounded(io.BytesIO(b"12345"), limit=4)


def test_install_tool_verifies_configured_directory_without_requiring_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    install_dir = tmp_path / "scanners"
    archive_bytes = b"archive"
    monkeypatch.setattr(installer, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(
        installer,
        "_download",
        lambda _url, destination: destination.write_bytes(archive_bytes),
    )
    monkeypatch.setattr(
        installer,
        "_expected_sha256",
        lambda _tool, _tag, _asset_name: hashlib.sha256(archive_bytes).hexdigest(),
    )

    def fake_install(_archive: Path, _asset_name: str, binary: str) -> None:
        install_dir.mkdir(parents=True, exist_ok=True)
        target = install_dir / binary
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        target.chmod(0o755)

    monkeypatch.setattr(installer, "_install_archive", fake_install)
    tag = installer.install_tool(
        {
            "name": "example",
            "repository": "owner/repository",
            "version_env": "",
            "default_tag": "v1.0.0",
            "asset_name_template": "example_{version}_linux_amd64.tar.gz",
            "asset_sha256": hashlib.sha256(archive_bytes).hexdigest(),
            "binary": "example",
        }
    )

    assert tag == "v1.0.0"
    assert (install_dir / "example").is_file()
