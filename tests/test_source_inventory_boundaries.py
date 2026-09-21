"""Owned source transport fixtures; no repository code or analyzer executes."""
import io
import stat
import subprocess
import zipfile

import pytest

from nico import snapshot_repository_evidence as snapshot
from nico import full_source_archive_profile_v1 as archive_profile
from nico.repository_profile_coverage_v1 import profile_coverage

POINTER = "version https://git-lfs.github.com/spec/v1\noid sha256:" + "a" * 64 + "\nsize 1000000\n"


@pytest.fixture
def owned_git(monkeypatch, tmp_path):
    origin = tmp_path / "owned"
    origin.mkdir()
    def git(*args):
        return subprocess.run(["git", *args], cwd=origin, check=True, capture_output=True, text=True).stdout.strip()
    git("init")
    (origin / "README.md").write_text("Owned fixture\n")
    (origin / "source.cpp").write_text(POINTER)
    (origin / "alias.cpp").symlink_to("README.md")
    git("add", ".")
    git("update-index", "--add", "--cacheinfo", "160000," + "d" * 40 + ",dependency.cpp")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "owned transport fixture")
    monkeypatch.setattr(snapshot.snapshot_capture, "_configure_public_origin",
        lambda path, url: subprocess.run(["git", "remote", "add", "origin", str(origin)], cwd=path, check=True))
    monkeypatch.setattr(snapshot.snapshot_capture, "_git_fetch_exact_sha",
        lambda path, sha, env, runner: subprocess.run(["git", "fetch", "--depth=1", "origin", sha],
                                                    cwd=path, capture_output=True, text=True))
    return git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")


def test_exact_git_accounts_for_submodules_lfs_and_symlinks_without_reading_content(owned_git):
    profile, error = snapshot._public_git_profile("owned/control", *owned_git)
    assert not error
    assert profile["tree_paths"] == ["README.md", "alias.cpp", "dependency.cpp", "source.cpp"]
    assert profile["files"] == {"README.md": "Owned fixture\n"}
    assert set(profile["unavailable_paths"]) == {"alias.cpp", "dependency.cpp", "source.cpp"}
    assert profile["submodule_entries"] == [{"path": "dependency.cpp", "commit_sha": "d" * 40}]
    assert profile["lfs_pointer_entries"] == [{"path": "source.cpp", "oid": "sha256:" + "a" * 64,
                                               "size_bytes": 1000000}]
    assert profile["source_profile"]["source_files_loaded"] == 0
    coverage = profile_coverage(profile, {"files_analyzed": 0, "analyzed_source_paths": []})
    assert coverage["inventory_complete"] and coverage["observed_repository_paths"] == 4
    assert coverage["observed_source_files"] == 2  # a gitlink named .cpp is not a source file
    assert coverage["submodule_entries"] == profile["submodule_entries"]
    assert coverage["lfs_pointer_entries"] == profile["lfs_pointer_entries"]


def test_exact_git_history_uses_independent_budget(owned_git, monkeypatch):
    from nico import scanner_worker
    monkeypatch.setattr(scanner_worker, "MAX_REPO_BYTES", 10)
    profile, error = snapshot._public_git_profile("owned/control", *owned_git)
    assert not error and profile is not None
    assert profile["git_history_observation"]["git_history_bytes"] > 10
    assert profile["git_history_observation"]["source_bytes"] == 0
    monkeypatch.setattr(scanner_worker, "MAX_GIT_HISTORY_BYTES", 10)
    profile, error = snapshot._public_git_profile("owned/control", *owned_git)
    assert profile is None and error == "public_git_history_size_limit_exceeded"


def test_api_inventory_preserves_unavailable_parent_entries(monkeypatch):
    entries = [{"path": "dependency.cpp", "type": "commit", "mode": "160000", "sha": "d" * 40},
               {"path": "source.cpp", "type": "blob", "mode": "100644", "sha": "b" * 40, "size": len(POINTER)},
               {"path": "alias.cpp", "type": "blob", "mode": "120000", "sha": "c" * 40, "size": 10}]
    monkeypatch.setattr(snapshot, "_get_json", lambda *a: ({"tree": entries, "sha": "b" * 40}, None))
    monkeypatch.setattr(snapshot, "_contents", lambda *a: ([], None))
    monkeypatch.setattr(snapshot, "should_fetch_path", lambda *a: True)
    monkeypatch.setattr(snapshot, "_text_file", lambda c, r, p, ref: (POINTER if p == "source.cpp" else "README.md", None))
    function = snapshot._profile
    while hasattr(function, "__wrapped__"):
        function = function.__wrapped__
    profile = function(None, "owned/control", {"commit_sha": "a" * 40})
    assert set(profile["tree_paths"]) == {"dependency.cpp", "source.cpp", "alias.cpp"}
    assert not profile["files"] and set(profile["unavailable_paths"]) == set(profile["tree_paths"])


def test_archive_cannot_promote_lfs_pointers_or_symlinks_to_source():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("root/source.cpp", POINTER)
        link = zipfile.ZipInfo("root/alias.cpp")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "source.cpp")
        archive.writestr("root/ordinary.py", "value = 1\n")
    files, metadata = archive_profile._archive_sources(buffer.getvalue())
    assert files == {"ordinary.py": "value = 1\n"}
    assert metadata["source_files_loaded"] == 1
    assert set(metadata["unavailable_paths"]) == {"source.cpp", "alias.cpp"}


@pytest.mark.parametrize("mutation", ["missing_sha", "invalid_sha", "duplicate", "bad_mode", "negative_size", "bad_path"])
def test_malformed_api_inventory_cannot_claim_completeness(monkeypatch, mutation):
    row = {"path": "README.md", "type": "blob", "mode": "100644", "sha": "a" * 40, "size": 3}
    entries = [row]
    if mutation == "missing_sha":
        row.pop("sha")
    elif mutation == "invalid_sha":
        row["sha"] = "not-an-object"
    elif mutation == "duplicate":
        entries.append({**row, "sha": "b" * 40})
    elif mutation == "bad_mode":
        row["mode"] = "160000"
    elif mutation == "negative_size":
        row["size"] = -1
    else:
        row["path"] = "../README.md"
    monkeypatch.setattr(snapshot, "_get_json", lambda *a: ({"tree": entries, "sha": "b" * 40}, None))
    monkeypatch.setattr(snapshot, "_contents", lambda *a: ([], None))
    monkeypatch.setattr(snapshot, "_text_file", lambda *a: ("abc", None))
    function = snapshot._profile
    while hasattr(function, "__wrapped__"):
        function = function.__wrapped__
    result = function(None, "owned/control", {"commit_sha": "a" * 40})
    assert result["tree_collection_succeeded"] is False


def test_lfs_pointer_reads_consume_archive_budget(monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("root/a.cpp", POINTER)
        archive.writestr("root/b.cpp", POINTER)
        archive.writestr("root/c.py", "x=1")
    monkeypatch.setattr(archive_profile, "MAX_SOURCE_FILES", 1)
    files, metadata = archive_profile._archive_sources(buffer.getvalue())
    assert not files and metadata["source_files_inspected"] == 1
    assert metadata["source_limit_excluded_paths"] == ["b.cpp", "c.py"]
