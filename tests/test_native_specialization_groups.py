"""Pinned source contracts and bounded owned C++ grouping only; no analyzer."""
from pathlib import Path

import pytest

from scripts.native_stage_counters import specialization_groups as repair


def owned_source(tmp_path, monkeypatch):
    raw = b'prefix\n' + repair.BUILD_ANCHOR + repair.OLD_FILTER + repair.DELETE_ANCHOR
    files = {'lib/templatesimplifier.cpp': raw, 'lib/templatesimplifier.h': b'owned header',
             'lib/token.cpp': b'owned token callbacks'}
    monkeypatch.setattr(repair, 'SOURCE_HASHES', {p: repair.sha(v) for p, v in files.items()})
    source = tmp_path / 'source'
    (source / 'lib').mkdir(parents=True)
    for p, v in files.items():
        (source / p).write_bytes(v)
    return source, files


def test_exact_only_replacements_preserve_source_and_exclusive_output(tmp_path, monkeypatch):
    source, files = owned_source(tmp_path, monkeypatch)
    output = tmp_path / 'overlay'
    receipt = repair.create_overlay(source, output)
    changed = (output / 'lib/templatesimplifier.cpp').read_bytes()
    restored = changed.replace(repair.GROUP_BUILD, b'').replace(repair.NEW_FILTER, repair.OLD_FILTER).replace(repair.GROUP_CLEAR, b'')
    assert restored == files['lib/templatesimplifier.cpp']
    assert all((source / p).read_bytes() == v for p, v in files.items())
    assert receipt['output_sha256'] == repair.sha(changed)
    assert not receipt['build_performed'] and not receipt['analyzer_execution']
    assert not receipt['bitcoin_performance_claimed']
    with pytest.raises(FileExistsError):
        repair.create_overlay(source, output)


@pytest.mark.parametrize('member', list(repair.SOURCE_HASHES))
def test_any_audited_source_change_rejects_before_output(tmp_path, monkeypatch, member):
    source, _ = owned_source(tmp_path, monkeypatch)
    (source / member).write_bytes(b'changed')
    output = tmp_path / 'overlay'
    with pytest.raises(ValueError, match='source_identity'):
        repair.create_overlay(source, output)
    assert not output.exists()


@pytest.mark.parametrize('anchor', [repair.BUILD_ANCHOR, repair.OLD_FILTER, repair.DELETE_ANCHOR])
def test_ambiguous_anchor_rejected_even_with_matching_source_hash(tmp_path, monkeypatch, anchor):
    _, files = owned_source(tmp_path, monkeypatch)
    raw = files['lib/templatesimplifier.cpp'] + anchor
    monkeypatch.setitem(repair.SOURCE_HASHES, 'lib/templatesimplifier.cpp', repair.sha(raw))
    with pytest.raises(ValueError, match='anchor_identity'):
        repair.transform(raw)


def test_symlinks_and_output_inside_source_rejected(tmp_path, monkeypatch):
    source, _ = owned_source(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='output_inside_source'):
        repair.create_overlay(source, source / 'overlay')
    linked = tmp_path / 'linked'
    linked.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):
        repair.create_overlay(linked, tmp_path / 'out')
    target = source / 'lib/token.cpp'
    target.unlink()
    target.symlink_to(source / 'lib/templatesimplifier.h')
    with pytest.raises(OSError):
        repair.create_overlay(source, tmp_path / 'out')


def test_candidate_is_not_wired_into_production_builds():
    script = Path(repair.__file__).name
    for root in ('docker',):
        assert all(script not in p.read_text() for p in Path(root).rglob('*') if p.is_file())
    assert 'TokenAndName' not in repair.GROUP_BUILD.decode()
    assert 'const Token *' in repair.GROUP_BUILD.decode()
    assert 'const auto& declaration' in repair.GROUP_BUILD.decode()
    assert 'const auto& specializations' in repair.NEW_FILTER.decode()
    assert 'specializationsByName.clear();' in repair.GROUP_CLEAR.decode()
