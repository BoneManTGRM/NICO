from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import install_hosted_scanner_binaries as installer


def test_validated_https_url_rejects_untrusted_schemes_and_hosts() -> None:
    assert installer._validated_https_url("https://api.github.com/repos/google/osv-scanner/releases/latest").startswith("https://")
    with pytest.raises(RuntimeError):
        installer._validated_https_url("file:///tmp/scanner")
    with pytest.raises(RuntimeError):
        installer._validated_https_url("https://example.com/scanner.tar.gz")
    with pytest.raises(RuntimeError):
        installer._validated_https_url("https://user:password@github.com/tool")


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
