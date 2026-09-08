"""Real collector composition with the installed archive and AST extensions."""
from __future__ import annotations

import io
import zipfile

import pytest

import test_source_architecture_profile_evidence as fixture
from nico import full_source_archive_profile_v1 as archive
from nico import snapshot_repository_evidence as snapshot
from nico.repository_profile_coverage_v1 import profile_coverage


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        for path, content in files.items():
            output.writestr("source/" + path, content)
    return stream.getvalue()


def installed_profile(monkeypatch, files, *, missing=()):
    monkeypatch.setattr(snapshot, "_profile", snapshot._profile)
    archive.install_full_source_archive_profile_v1()
    monkeypatch.setattr(archive, "_download_archive", lambda *args: zip_bytes(files))
    context, captured = fixture.identities()
    return snapshot.collect_snapshot_repository_evidence(
        context, captured, store=fixture.Store(),
        client=fixture.SnapshotClient(fixture.FILES, truncated=True, missing=missing),
    )


def test_archive_extends_truncated_inventory_without_losing_run_or_coverage(monkeypatch):
    files = {**fixture.FILES, "additional.py": "def f():\n    return 1\n"}
    repository, complexity = installed_profile(monkeypatch, files, missing=("app.py",))
    coverage = complexity["profile_coverage"]
    assert "additional.py" in coverage["analyzed_source_paths"]
    assert "app.py" in coverage["analyzed_source_paths"]
    assert "app.py" not in coverage["unavailable_paths"]
    assert coverage["inventory_complete"] is False
    assert coverage["whole_repository_coverage_percent"] is None
    assert coverage["file_limit"] == 90 + archive.MAX_SOURCE_FILES
    assert coverage["per_file_byte_limit"] == archive.MAX_SOURCE_FILE_BYTES
    assert coverage["collection_limits"]["bounded_api"]["file_limit"] == 90
    assert repository["architecture_evidence"]["source_observation"]["commit_sha"] == fixture.SHA


def test_archive_order_keeps_same_bounded_sample_and_names_exclusions(monkeypatch):
    files = {"z.py": "z=1", "b.py": "b=1", "a.py": "a=1", "large.py": "#" * 101}
    monkeypatch.setattr(archive, "MAX_SOURCE_FILES", 2)
    monkeypatch.setattr(archive, "MAX_SOURCE_FILE_BYTES", 100)
    forward = archive._archive_sources(zip_bytes(files))
    reverse = archive._archive_sources(zip_bytes(dict(reversed(list(files.items())))))
    assert forward == reverse
    assert list(forward[0]) == ["a.py", "b.py"]
    assert forward[1]["source_size_excluded_paths"] == ["large.py"]
    assert forward[1]["source_limit_excluded_paths"] == ["z.py"]


def test_installed_ast_omission_uses_actual_analysis_membership(monkeypatch):
    from nico import typescript_ast_complexity_v1 as ast_metrics
    from nico.full_assessment_complexity_evidence import collect_complexity_evidence
    files = {"app.py": "def f():\n    return 1\n", "invalid.ts": "not valid typescript"}
    monkeypatch.setattr(ast_metrics, "_run_typescript_ast", lambda files: {
        "status": "complete", "analyses": [], "import_graph": {},
    })
    measured = collect_complexity_evidence(files)
    coverage = profile_coverage({"tree_paths": list(files), "files": files,
                                 "tree_collection_succeeded": True, "tree_truncated": False}, measured)
    assert measured["analyzed_source_paths"] == ["app.py"]
    assert coverage["analyzed_source_files"] == 1
    assert coverage["sampled_unanalyzed_source_paths"] == ["invalid.ts"]
    assert coverage["eligible_source_coverage_percent"] == 50
    assert any("invalid.ts" in note for note in coverage["parser_notes"])


@pytest.mark.parametrize("paths", [["foreign.py"], ["app.py", "app.py"]])
def test_coverage_rejects_foreign_or_duplicated_actual_membership(paths):
    with pytest.raises(ValueError, match="profile_analysis"):
        profile_coverage({"tree_paths": ["app.py"], "files": {"app.py": "x=1"}},
                         {"files_analyzed": 1, "analyzed_source_paths": paths})
