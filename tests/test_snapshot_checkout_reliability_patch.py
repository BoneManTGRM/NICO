from __future__ import annotations

import io
import zipfile
from pathlib import Path

from nico.snapshot_checkout_reliability_patch import _archive_checkout


def _archive() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("NICO-deadbeef/pyproject.toml", "[project]\nname='nico'\n")
        archive.writestr("NICO-deadbeef/nico/example.py", "VALUE = 1\n")
    return buffer.getvalue()


def test_archive_fallback_is_bound_to_exact_commit(monkeypatch, tmp_path: Path) -> None:
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return _archive()

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    commit = "a" * 40
    repo_path, actual_sha, notes = _archive_checkout("BoneManTGRM/NICO", commit, tmp_path)

    assert repo_path == tmp_path / "repo"
    assert actual_sha == commit
    assert (repo_path / "pyproject.toml").is_file()
    assert (repo_path / "nico" / "example.py").is_file()
    assert any("Git-history scanners are unavailable" in note for note in notes)


def test_archive_fallback_rejects_unsafe_paths(monkeypatch, tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("NICO-deadbeef/../../escape.txt", "unsafe")

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit: int) -> bytes:
            return buffer.getvalue()

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    repo_path, actual_sha, notes = _archive_checkout("BoneManTGRM/NICO", "b" * 40, tmp_path)

    assert repo_path is None
    assert actual_sha == ""
    assert not (tmp_path / "escape.txt").exists()
    assert any("extraction failed safely" in note for note in notes)
