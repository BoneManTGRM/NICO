"""Original-byte planning evidence; no assessed code or remote source runs."""
import base64
from copy import deepcopy
import hashlib
import io
import json
import subprocess
from urllib.parse import unquote
import zipfile

import pytest

from nico import snapshot_repository_evidence as snapshot
from nico import full_source_archive_profile_v1 as archive
from test_snapshot_repository_evidence import FakeSnapshotClient, _context, _snapshot
from test_source_architecture_profile_evidence import Store

RAW = b'// original byte: \xff\nint value() { return 7; }\n'


def blob(raw):
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw, usedforsecurity=False).hexdigest()


class RawClient(FakeSnapshotClient):
    def __init__(self, *, wrong_blob=False, **kwargs):
        super().__init__(**kwargs)
        self.files = {'source.cpp': RAW}
        self.wrong_blob = wrong_blob

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        suffix = url.split('/repos/BoneManTGRM/NICO', 1)[-1]
        if suffix.startswith('/git/trees/'):
            return {'sha': self.tree_sha, 'truncated': self.tree_truncated, 'tree': [
                {'type': 'blob', 'mode': '100644', 'path': path, 'size': len(raw),
                 'sha': 'c' * 40 if self.wrong_blob else blob(raw)}
                for path, raw in self.files.items()]}, None
        if suffix == '/contents':
            return [{'name': path} for path in self.files], None
        if suffix.startswith('/contents/'):
            raw = self.files[unquote(suffix.removeprefix('/contents/'))]
            return {'type': 'file', 'size': len(raw), 'content': base64.b64encode(raw).decode()}, None
        return super().get_json(url, params)


def collect(monkeypatch, client):
    profile = snapshot._profile
    while hasattr(profile, '__wrapped__'):
        profile = profile.__wrapped__
    monkeypatch.setattr(snapshot, '_profile', profile)
    context = _context()
    captured = _snapshot(context)
    store = Store()
    repository, _ = snapshot.collect_snapshot_repository_evidence(context, captured, client=client, store=store)
    return repository['execution_input_manifest'], repository, store


def test_collector_persists_original_bytes_not_reencoded_report_text(monkeypatch):
    manifest, repository, store = collect(monkeypatch, RawClient())
    row = manifest['members']['source.cpp']
    assert row == {'blob_sha': blob(RAW), 'sha256': hashlib.sha256(RAW).hexdigest(), 'bytes': len(RAW)}
    assert row['sha256'] != hashlib.sha256(RAW.decode('utf-8', errors='replace').encode()).hexdigest()
    assert manifest['snapshot_commit_sha'] == 'a' * 40 and manifest['snapshot_tree_sha'] == 'b' * 40
    assert manifest['selected_population_verified'] is True
    assert manifest['assessment_contract_selected'] is False
    assert manifest['selected_paths'] == ['source.cpp'] and manifest['unverified_paths'] == []
    retained = store.data[('evidence_items', repository['evidence_id'])]
    assert retained['filename'] == 'snapshot-repository-evidence.json'
    assert retained['evidence']['execution_input_manifest'] == manifest
    assert repository['file_evidence']['files_profiled'] == 1
    unsigned = deepcopy(manifest); digest = unsigned.pop('manifest_sha256')
    assert hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == digest


def test_blob_substitution_cannot_produce_execution_identity(monkeypatch):
    manifest, _, _ = collect(monkeypatch, RawClient(wrong_blob=True))
    assert manifest['members'] == {}
    assert manifest['unverified_paths'] == ['source.cpp']
    assert manifest['selected_population_verified'] is False


def test_truncated_inventory_is_not_promoted_by_successful_file_reads(monkeypatch):
    manifest, _, _ = collect(monkeypatch, RawClient(tree_truncated=True))
    assert manifest['inventory_complete'] is False and manifest['selected_population_verified'] is False


@pytest.mark.parametrize('change', ['missing_raw', 'missing_tree', 'wrong_tree', 'missing_file', 'extended_text'])
def test_incomplete_or_report_only_profile_cannot_supply_execution_contract(change):
    from nico.snapshot_execution_inputs import execution_input_manifest
    profile = {'files': {'source.cpp': RAW.decode('utf-8', errors='replace')},
        'raw_input_records': {'source.cpp': {'blob_sha': blob(RAW), 'sha256': hashlib.sha256(RAW).hexdigest(), 'bytes': len(RAW)}},
        'raw_input_selected_paths': ['source.cpp'], 'tree_paths': ['source.cpp'],
        'tree_sha': 'b' * 40, 'tree_collection_succeeded': True, 'tree_truncated': False}
    if change == 'missing_raw': profile.pop('raw_input_records')
    elif change == 'missing_tree': profile.pop('tree_sha')
    elif change == 'wrong_tree': profile['tree_sha'] = 'c' * 40
    elif change == 'missing_file': profile['raw_input_selected_paths'].append('missing.h')
    else: profile['files']['additional.cpp'] = 'int other;'
    manifest = execution_input_manifest(profile, {'commit_sha': 'a' * 40, 'tree_sha': 'b' * 40})
    assert manifest['selected_population_verified'] is False
    assert manifest['assessment_contract_selected'] is False


def test_archive_capture_keeps_original_hashes_but_requires_matching_tree(monkeypatch):
    source = io.BytesIO()
    with zipfile.ZipFile(source, 'w') as z:
        z.writestr('root/source.cpp', RAW)
    files, metadata = archive._archive_sources(source.getvalue())
    assert metadata['source_raw_input_records']['source.cpp']['sha256'] == hashlib.sha256(RAW).hexdigest()
    base = snapshot._profile
    while hasattr(base, '__wrapped__'): base = base.__wrapped__
    monkeypatch.setattr(snapshot, '_profile', base)
    archive.install_full_source_archive_profile_v1()
    monkeypatch.setattr(archive, '_download_archive', lambda *a: source.getvalue())
    from nico.snapshot_execution_inputs import execution_input_manifest
    for wrong in (False, True):
        profile = snapshot._profile(RawClient(wrong_blob=wrong), 'BoneManTGRM/NICO',
                                    {'commit_sha': 'a' * 40, 'tree_sha': 'b' * 40})
        manifest = execution_input_manifest(profile, {'commit_sha': 'a' * 40, 'tree_sha': 'b' * 40})
        assert manifest['selected_population_verified'] is (not wrong)
        assert bool(manifest['members']) is (not wrong)
        assert profile['files'] == files  # report decoding remains a separate representation


def test_real_owned_git_profile_preserves_raw_identity(monkeypatch, tmp_path):
    origin = tmp_path / 'owned'; origin.mkdir()
    def git(*args):
        return subprocess.run(['git', *args], cwd=origin, check=True, capture_output=True, text=True).stdout.strip()
    git('init'); (origin / 'source.cpp').write_bytes(RAW); git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'owned bytes')
    sha, tree = git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')
    monkeypatch.setattr(snapshot.snapshot_capture, '_configure_public_origin',
        lambda path, url: subprocess.run(['git', 'remote', 'add', 'origin', str(origin)], cwd=path, check=True))
    monkeypatch.setattr(snapshot.snapshot_capture, '_git_fetch_exact_sha',
        lambda path, revision, env, runner: subprocess.run(['git', 'fetch', '--depth=1', 'origin', revision],
                                                          cwd=path, capture_output=True, text=True))
    profile, error = snapshot._public_git_profile('owned/control', sha, tree)
    assert not error
    from nico.snapshot_execution_inputs import execution_input_manifest
    manifest = execution_input_manifest(profile, {'commit_sha': sha, 'tree_sha': tree})
    assert manifest['selected_population_verified'] is True
    assert manifest['members']['source.cpp']['sha256'] == hashlib.sha256(RAW).hexdigest()
