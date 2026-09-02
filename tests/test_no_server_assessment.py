from __future__ import annotations

import io
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

import nico.no_server_assessment as no_server

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


def test_no_server_analysis_recognizes_node_ci_and_skips_python_only_tool(tmp_path, monkeypatch):
    project = tmp_path / "project"
    workflow = project / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("steps:\n  - run: npm run verify\n", encoding="utf-8")
    (project / "package.json").write_text('{"scripts":{"verify":"node --test"}}\n', encoding="utf-8")
    (project / "package-lock.json").write_text("{}\n", encoding="utf-8")
    files = no_server.collect_text_files(project)
    monkeypatch.setattr(
        no_server,
        "scanner_availability",
        lambda: [
            {"tool": "osv-scanner", "purpose": "dependency scanning", "available": False},
            {"tool": "pip-audit", "purpose": "python dependency scanning", "available": False},
            {"tool": "npm", "purpose": "npm audit availability", "available": True},
        ],
    )

    cicd = no_server.analyze_cicd(project, files)
    dependencies = no_server.analyze_dependencies(project, files, [])

    assert "Test/lint/build signal in workflow text: True." in cicd["evidence"]
    assert not any("no obvious test/lint/build command" in item for item in cicd["findings"])
    assert not any("pip-audit" in item for item in dependencies["unavailable_data"])


def test_github_assessment_temp_project_is_inside_default_allowed_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    observed: dict[str, Path] = {}

    def fake_download(_repo: str, destination: Path) -> Path:
        root = destination / "repo" / "project"
        root.mkdir(parents=True)
        observed["destination"] = destination
        return root

    def fake_scan(target: str, *, kind: str):
        observed["target"] = Path(target)
        assert kind == "no_server_github"
        return {"scan": {"findings": [], "files_scanned": []}, "repairs": []}

    monkeypatch.setattr(no_server, "download_github_repo", fake_download)
    monkeypatch.setattr(no_server, "run_scan", fake_scan)
    monkeypatch.setattr(no_server, "build_report", lambda *_args: {"status": "completed"})

    result = no_server.run_github_assessment("BoneManTGRM/SARA", authorized=True)

    assert result == {"status": "completed"}
    assert observed["destination"].parent == tmp_path
    assert observed["target"].is_relative_to(tmp_path)


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
