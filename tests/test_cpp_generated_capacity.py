"""Measured raw-data expansion must fit the shared, still-bounded snapshot path."""
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from nico import assessment_cpp_project_snapshot as snapshot
from nico import assessment_cpp_project_compiler as compiler
from tests.test_cpp_project_snapshot import contexts, layout


def test_expanded_raw_header_is_captured_without_changing_aggregate_budget(tmp_path):
    build, destination = layout(tmp_path)
    # Synthetic byte-table expansion: 16 source characters per raw byte plus
    # one newline per eight bytes. No upstream source or executable is used.
    raw_size = 1_582_208
    header = b'std::byte{0x00},' * raw_size + b'\n' * (raw_size // 8)
    assert len(header) == 25_513_104
    (build / 'generated/expanded.h').write_bytes(header)
    value = snapshot.capture_project_snapshot(build, destination, snapshot.project_snapshot_request(contexts()))
    assert value['files']['generated/expanded.h']['bytes'] == len(header)
    assert value['files']['generated/expanded.h']['sha256'] == sha256(header).hexdigest()
    assert (destination / 'generated/expanded.h').read_bytes() == header
    assert snapshot.validate_project_snapshot(value, contexts()) == value
    assert snapshot.PROJECT_GENERATED_MAX_BYTES == 32 * 1024 * 1024
    assert snapshot.PROJECT_GENERATED_STREAM_LIMIT == 48 * 1024 * 1024
    assert value['analysis_executed'] is False
    assert value['header_dependencies_verified'] is False


def test_compiler_and_snapshot_share_the_same_generated_input_bound(tmp_path, monkeypatch):
    root = tmp_path / 'private'; root.mkdir()
    raw = b'owned synthetic bytes'; (root / 'owned.h').write_bytes(raw)
    called = []
    # Model the isolated analyst's file ownership only; preserve real contents
    # and the actual bounded reader invocation.
    original = compiler._stable_bytes
    def reader(root, relative, maximum):
        called.append(maximum)
        return original(root, relative, maximum)
    monkeypatch.setattr(compiler, '_stable_bytes', reader)
    monkeypatch.setattr(Path, 'lstat', lambda self: SimpleNamespace(st_uid=1001, st_mode=0o100444))
    compiler._verify_input(root, 'owned.h', sha256(raw).hexdigest(), len(raw), True)
    assert called == [snapshot.PROJECT_GENERATED_MAX_FILE_BYTES]
    assert called[0] == 32 * 1024 * 1024
    assert f'GENERATED_FILE_LIMIT={snapshot.PROJECT_GENERATED_MAX_FILE_BYTES}' in compiler.PROGRAM


def test_generated_file_above_hard_bound_still_fails_before_publication(tmp_path):
    build, destination = layout(tmp_path)
    with (build / 'generated/too_large.h').open('wb') as handle:
        handle.truncate(32 * 1024 * 1024 + 1)
    with pytest.raises(ValueError):
        snapshot.capture_project_snapshot(build, destination, snapshot.project_snapshot_request(contexts()))
    assert not destination.exists()
    assert not list(destination.parent.glob('.project-generated-*'))


def test_aggregate_cap_still_rejects_individually_valid_files(tmp_path, monkeypatch):
    build, destination = layout(tmp_path)
    # Small deterministic analogue, avoiding a second large allocation.
    monkeypatch.setattr(snapshot, 'PROJECT_GENERATED_MAX_FILE_BYTES', 128)
    monkeypatch.setattr(snapshot, 'PROJECT_GENERATED_MAX_BYTES', 100)
    (build / 'generated/extra.h').write_bytes(b' ' * 80)
    with pytest.raises(ValueError):
        snapshot.capture_project_snapshot(build, destination, snapshot.project_snapshot_request(contexts()))
    assert not destination.exists()
