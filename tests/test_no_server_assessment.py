from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from nico.no_server_assessment import (
    AuthorizationError,
    run_local_assessment,
    safe_extract_tar,
    safe_extract_zip,
)


def test_local_assessment_requires_authorization(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("print('hello')\n", encoding="utf-8")
    try:
        run_local_assessment(str(project), authorized=False)
        assert False, "expected authorization gate to block"
    except AuthorizationError as exc:
        assert "--authorized" in str(exc)


def test_local_assessment_generates_report(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "app.py").write_text("# TODO: add rate limiting\n", encoding="utf-8")
    (project / "requirements.txt").write_text("requests>=2.31\n", encoding="utf-8")
    (project / "README.md").write_text("# Test project\n", encoding="utf-8")
    monkeypatch.setenv("NICO_ALLOWED_SCAN_ROOT", str(tmp_path))

    result = run_local_assessment(str(project), authorized=True)

    assert result["status"] == "completed"
    assert result["mode"] == "no-server-local-first"
    assert result["target_type"] == "local"
    assert "Code Audit" in result["maturity_semaphore"]
    assert result["evidence_log"]


def test_safe_zip_extraction_blocks_traversal_and_symlink(tmp_path: Path) -> None:
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as zf:
        zf.writestr("../outside.txt", "blocked")
    with pytest.raises(RuntimeError):
        safe_extract_zip(traversal, tmp_path / "zip-out")
    assert not (tmp_path / "outside.txt").exists()

    linked = tmp_path / "linked.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(linked, "w") as zf:
        zf.writestr(info, "target")
    with pytest.raises(RuntimeError):
        safe_extract_zip(linked, tmp_path / "zip-link-out")


def test_safe_tar_extraction_allows_files_and_blocks_links(tmp_path: Path) -> None:
    normal = tmp_path / "normal.tar.gz"
    with tarfile.open(normal, "w:gz") as tf:
        payload = b"safe"
        item = tarfile.TarInfo("project/app.py")
        item.size = len(payload)
        tf.addfile(item, io.BytesIO(payload))
    destination = tmp_path / "tar-out"
    safe_extract_tar(normal, destination)
    assert (destination / "project" / "app.py").read_bytes() == b"safe"

    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as tf:
        item = tarfile.TarInfo("project/link")
        item.type = tarfile.SYMTYPE
        item.linkname = "/tmp/target"
        tf.addfile(item)
    with pytest.raises(RuntimeError):
        safe_extract_tar(linked, tmp_path / "tar-link-out")
