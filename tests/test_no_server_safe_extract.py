from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from nico.no_server_assessment import safe_extract_tar, safe_extract_zip


def test_safe_zip_extracts_regular_files_and_blocks_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "regular.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("project/app.py", "print('ok')\n")
    destination = tmp_path / "zip-output"
    safe_extract_zip(archive, destination)
    assert (destination / "project" / "app.py").read_text(encoding="utf-8") == "print('ok')\n"

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as zf:
        zf.writestr("../escape.py", "bad")
    with pytest.raises(RuntimeError):
        safe_extract_zip(traversal, tmp_path / "blocked-zip")


def test_safe_zip_blocks_symlinks(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    member = zipfile.ZipInfo("project/link")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(member, "/tmp/target")
    with pytest.raises(RuntimeError):
        safe_extract_zip(archive, tmp_path / "blocked-link")


def test_safe_tar_extracts_regular_files_and_blocks_links(tmp_path: Path) -> None:
    archive = tmp_path / "regular.tar.gz"
    payload = b"print('ok')\n"
    with tarfile.open(archive, "w:gz") as tf:
        member = tarfile.TarInfo("project/app.py")
        member.size = len(payload)
        tf.addfile(member, io.BytesIO(payload))
    destination = tmp_path / "tar-output"
    safe_extract_tar(archive, destination)
    assert (destination / "project" / "app.py").read_bytes() == payload

    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as tf:
        member = tarfile.TarInfo("project/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/tmp/target"
        tf.addfile(member)
    with pytest.raises(RuntimeError):
        safe_extract_tar(linked, tmp_path / "blocked-tar")
