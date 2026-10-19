"""Real v2 oracles; no installed routes or retained-report capacity claim."""
from copy import deepcopy
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
import zipfile

import pytest

from nico import ordinary_report_file_streams_v2 as streams
from nico import ordinary_report_files_v2 as transport
from nico import ordinary_review_bundle_v2 as core
from nico.client_pdf_compose_v2 import compose_review_bundle
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from tests.test_ordinary_report_files_v2 import inputs, rewrite_zip


@pytest.fixture(scope='module', params=['en', 'es-MX'])
def fixture(request):
    identity, exports, components = inputs(request.param)
    # Deliberately noncanonical whitespace: raw bytes and semantic hash differ.
    exports['canonical_json'] = json.dumps(json.loads(exports['canonical_json']), indent=2)
    bundle = compose_review_bundle(identity, **components)
    family = transport.build_report_files(bundle, exports, expected_identity=identity,
        expected_bundle_manifest_sha256=bundle['manifest_sha256'])
    archive = transport.report_files_zip(family, expected_identity=identity, expected_manifest_sha256=family['manifest_sha256'])
    return identity, exports, bundle, family, archive


def paths(tmp_path, exports):
    result = {}
    for kind, name in transport.EXPORT_NAMES.items():
        result[kind] = tmp_path / name
        result[kind].write_text(exports[kind], encoding='utf-8')
    return result


def write(fixture, tmp_path, export_paths=None):
    identity, exports, bundle, _, _ = fixture
    return streams.write_report_files_zip_from_paths(bundle, export_paths or paths(tmp_path, exports), tmp_path / 'family.zip',
        expected_identity=identity, expected_bundle_manifest_sha256=bundle['manifest_sha256'])


def validate(fixture, path):
    identity, _, _, family, _ = fixture
    return streams.validate_report_files_zip_path(path, expected_identity=identity, expected_manifest_sha256=family['manifest_sha256'])


def test_byte_exact_oracle_and_complete_family(fixture, tmp_path):
    identity, exports, _, family, archive = fixture
    receipt = write(fixture, tmp_path)
    assert (tmp_path / 'family.zip').read_bytes() == archive
    assert receipt['manifest'] == family['manifest']
    assert receipt['manifest_sha256'] == family['manifest_sha256']
    assert receipt['archive_sha256'] == core._sha(archive)
    assert receipt['archive_size_bytes'] == len(archive)
    assert receipt['client_delivery_allowed'] is False
    assert receipt['canonical_validation_materializes_json'] is True
    assert receipt['canonical_validation_seconds'] >= 0
    assert validate(fixture, tmp_path / 'family.zip')['manifest'] == family['manifest']
    assert core._sha(exports['canonical_json'].encode()) != identity['canonical_truth_sha256']
    assert canonical_sha256(json.loads(exports['canonical_json'])) == identity['canonical_truth_sha256']
    assert not list(tmp_path.glob('.nico-family-*'))
    loaded = transport.read_report_files_zip(archive, expected_identity=identity, expected_manifest_sha256=family['manifest_sha256'])
    assert loaded == family


@pytest.mark.parametrize('damage', ['missing', 'extra', 'duplicate', 'tamper', 'unsafe', 'reorder', 'first_only', 'symlink', 'encrypted'])
def test_archive_negative_controls(fixture, tmp_path, damage):
    archive = fixture[-1]
    def change(entries):
        if damage == 'missing': entries.pop()
        elif damage == 'extra': entries.append(('extra', b'bad'))
        elif damage == 'duplicate': entries.append(entries[-1])
        elif damage == 'tamper': entries[-1] = (entries[-1][0], b'changed')
        elif damage == 'unsafe': entries[-1] = ('../escape', entries[-1][1])
        elif damage == 'reorder': entries.reverse()
        elif damage == 'first_only': entries[:] = entries[:1]
    if damage in {'symlink', 'encrypted'}:
        data = bytearray(archive)
        central = data.index(b'PK\x01\x02')
        if damage == 'symlink': data[central+38:central+42] = (0o120777 << 16).to_bytes(4, 'little')
        else: data[central+8:central+10] = (1).to_bytes(2, 'little')
        archive = bytes(data)
    else:
        archive = rewrite_zip(archive, change)
    target = tmp_path / 'bad.zip'
    target.write_bytes(archive)
    with pytest.raises(ValueError): validate(fixture, target)


@pytest.mark.parametrize('field,value', [('run_id','stale'), ('repository','other/repo'), ('commit_sha','b'*40),
    ('report_language','fr'), ('canonical_truth_sha256','b'*64)])
def test_expected_identity_negative_controls(fixture, tmp_path, field, value):
    target = tmp_path / 'family.zip'
    target.write_bytes(fixture[-1])
    identity = {**fixture[0], field: value}
    with pytest.raises(ValueError):
        streams.validate_report_files_zip_path(target, expected_identity=identity, expected_manifest_sha256=fixture[3]['manifest_sha256'])


def test_stale_manifest_digest(fixture, tmp_path):
    target = tmp_path / 'family.zip'
    target.write_bytes(fixture[-1])
    with pytest.raises(ValueError, match='manifest_digest'):
        streams.validate_report_files_zip_path(target, expected_identity=fixture[0], expected_manifest_sha256='b'*64)


@pytest.mark.parametrize('damage', ['missing', 'extra', 'canonical_truth', 'approval', 'symlink', 'ancestor_symlink'])
def test_export_input_rejection_is_atomic(fixture, tmp_path, damage):
    export_paths = paths(tmp_path, fixture[1])
    if damage == 'missing': export_paths.pop('markdown_report')
    elif damage == 'extra': export_paths['extra'] = tmp_path / 'report.md'
    elif damage in {'canonical_truth','approval'}:
        canonical = json.loads(fixture[1]['canonical_json'])
        if damage == 'canonical_truth': canonical['assessment']['score'] = 100
        else: canonical['client_delivery_allowed'] = True
        export_paths['canonical_json'].write_text(json.dumps(canonical))
    elif damage == 'symlink':
        target = export_paths['markdown_report']
        real = tmp_path / 'real.md'
        target.rename(real)
        target.symlink_to(real)
    else:
        link = tmp_path / 'linked'
        link.symlink_to(tmp_path, target_is_directory=True)
        export_paths['markdown_report'] = link / 'report.md'
    with pytest.raises((ValueError, OSError)):
        write(fixture, tmp_path, export_paths)
    assert not (tmp_path / 'family.zip').exists()
    assert not list(tmp_path.glob('.nico-family-*'))


@pytest.mark.parametrize('mode', ['existing', 'symlink', 'racing_creator'])
def test_no_overwrite_publication(fixture, tmp_path, monkeypatch, mode):
    target = tmp_path / 'family.zip'
    other = tmp_path / 'other'
    other.write_bytes(b'original')
    if mode == 'existing': target.write_bytes(b'original')
    elif mode == 'symlink': target.symlink_to(other)
    else:
        original_link = streams.os.link
        def race(*args, **kwargs):
            target.write_bytes(b'original')
            return original_link(*args, **kwargs)
        monkeypatch.setattr(streams.os, 'link', race)
    with pytest.raises(FileExistsError): write(fixture, tmp_path)
    assert target.read_bytes() == b'original'
    assert other.read_bytes() == b'original'
    assert not list(tmp_path.glob('.nico-family-*'))


@pytest.mark.parametrize('mode', ['rewrite', 'replace', 'interrupt_write', 'interrupt_validate', 'deadline'])
def test_mid_operation_failure_has_no_published_archive(fixture, tmp_path, monkeypatch, mode):
    export_paths = paths(tmp_path, fixture[1])
    original_read = streams._read
    changed = False
    def read(stream, maximum, started, **kwargs):
        nonlocal changed
        if kwargs.get('sink') is not None and not changed:
            changed = True
            if mode == 'rewrite': export_paths['markdown_report'].write_text('changed')
            elif mode == 'replace':
                replacement = tmp_path / 'replacement'
                replacement.write_bytes(export_paths['markdown_report'].read_bytes())
                replacement.replace(export_paths['markdown_report'])
            elif mode == 'interrupt_write': raise KeyboardInterrupt()
        return original_read(stream, maximum, started, **kwargs)
    monkeypatch.setattr(streams, '_read', read)
    if mode == 'interrupt_validate':
        monkeypatch.setattr(streams, '_validate_open', lambda *a, **k: (_ for _ in ()).throw(OSError('interrupted validation')))
    if mode == 'deadline': monkeypatch.setattr(core, 'MAX_SECONDS', -1)
    with pytest.raises((ValueError, OSError, KeyboardInterrupt)):
        write(fixture, tmp_path, export_paths)
    assert not (tmp_path / 'family.zip').exists()
    assert not list(tmp_path.glob('.nico-family-*'))


@pytest.mark.parametrize('limit', ['MAX_TEXT_BYTES', 'MAX_FAMILY_BYTES'])
def test_limits_remain_enforced(fixture, tmp_path, monkeypatch, limit):
    monkeypatch.setattr(transport, limit, 1)
    with pytest.raises(ValueError): write(fixture, tmp_path)
    assert not (tmp_path / 'family.zip').exists()
    archive = tmp_path / 'existing.zip'
    archive.write_bytes(fixture[-1])
    with pytest.raises(ValueError): validate(fixture, archive)


def test_expanded_size_limit_not_waived_by_compression(fixture, tmp_path):
    archive = rewrite_zip(fixture[-1], lambda entries: entries.append(('bomb', b'x' * (transport.MAX_FAMILY_BYTES + 1))))
    target = tmp_path / 'expanded.zip'
    target.write_bytes(archive)
    with pytest.raises(ValueError): validate(fixture, target)


def test_reads_are_bounded_and_text_not_retained_in_memory(fixture, tmp_path, monkeypatch):
    original = streams._read
    calls = []
    class Reader:
        def __init__(self, source): self.source = source
        def read(self, size):
            assert 0 < size <= streams.CHUNK_BYTES
            return self.source.read(size)
    def checked(stream, maximum, started, **kwargs):
        calls.append((getattr(stream, 'name', ''), kwargs.get('retain', False)))
        return original(Reader(stream), maximum, started, **kwargs)
    monkeypatch.setattr(streams, '_read', checked)
    write(fixture, tmp_path)
    validate(fixture, tmp_path / 'family.zip')
    assert calls
    assert all(not retain for name, retain in calls if str(name).endswith(('report.md', 'report.html', 'findings.csv', 'evidence.csv')))


def test_archive_path_symlink_rejected(fixture, tmp_path):
    actual = tmp_path / 'actual.zip'
    actual.write_bytes(fixture[-1])
    alias = tmp_path / 'alias.zip'
    alias.symlink_to(actual)
    with pytest.raises(OSError): validate(fixture, alias)


def test_process_kill_before_publish_never_exposes_final_archive(fixture, tmp_path):
    exports = paths(tmp_path, fixture[1])
    control = tmp_path / 'control.json'
    control.write_text(json.dumps({'identity': fixture[0], 'bundle': fixture[2], 'paths': {k: str(v) for k,v in exports.items()}}))
    code = '''
import json, os, signal, sys
from pathlib import Path
from nico import ordinary_report_file_streams_v2 as s
v=json.loads(Path(sys.argv[1]).read_text())
s._validate_open=lambda *a,**k: os.kill(os.getpid(), signal.SIGKILL)
s.write_report_files_zip_from_paths(v['bundle'],v['paths'],Path(sys.argv[2]),expected_identity=v['identity'],expected_bundle_manifest_sha256=v['bundle']['manifest_sha256'])
'''
    result = subprocess.run([sys.executable, '-c', code, str(control), str(tmp_path / 'family.zip')], capture_output=True, timeout=20)
    assert result.returncode == -signal.SIGKILL, result.stderr
    assert not (tmp_path / 'family.zip').exists()
    # A hard kill can leave only a private unfinished temp; never a ready file.
    for temporary in tmp_path.glob('.nico-family-*'):
        assert temporary.stat().st_mode & 0o777 == 0o600
        temporary.unlink()


def test_offline_harness_reports_limits_and_cost_without_activation(fixture, tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/qualify_ordinary_report_file_streams_v2.py'
    identity = tmp_path / 'identity.json'
    identity.write_text(json.dumps(fixture[0]))
    bundle = tmp_path / 'bundle.json'
    bundle.write_text(json.dumps(fixture[2]))
    paths(tmp_path, fixture[1])
    args = [sys.executable, str(script), 'write', '--bundle-json', str(bundle), '--identity-json', str(identity),
            '--expected-bundle-manifest-sha256', fixture[2]['manifest_sha256'], '--exports-directory', str(tmp_path),
            '--destination', str(tmp_path / 'family.zip')]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    observed = json.loads(result.stdout)
    assert observed['status'] == 'complete'
    assert observed['canonical_parse_is_materialized'] is True
    assert observed['worker_hard_limits_established'] is False
    assert observed['python_tracemalloc_peak_bytes'] > 0
    assert (tmp_path / 'family.zip').read_bytes() == fixture[-1]
    # Inventory diagnostics can observe over-limit retained members, not admit them.
    oversized = tmp_path / 'retained.zip'
    with zipfile.ZipFile(oversized, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('canonical.json', b'x' * (transport.MAX_FAMILY_BYTES + 1))
    manifest = tmp_path / 'detached.json'
    manifest.write_bytes(b'{}')
    result = subprocess.run([sys.executable, str(script), 'inventory', str(oversized),
        '--expected-archive-sha256', core._sha(oversized.read_bytes()), '--detached-manifest', str(manifest),
        '--expected-detached-manifest-sha256', core._sha(b'{}')], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr + result.stdout
    observation = json.loads(result.stdout)['result']
    assert observation['exceeds_current_family_limit'] is True
    assert observation['production_admission_established'] is False
    assert observation['detached_manifest_member_semantics_verified'] is False


def test_combined_text_limit_is_enforced_before_member_read(fixture, tmp_path, monkeypatch):
    entries = [e for e in fixture[3]['manifest']['artifacts'] if e['artifact_type'] in transport.EXPORT_NAMES]
    limit = max(e['size_bytes'] for e in entries)
    assert sum(e['size_bytes'] for e in entries) > limit
    target = tmp_path / 'family.zip'
    target.write_bytes(fixture[-1])
    monkeypatch.setattr(transport, 'MAX_TEXT_BYTES', limit)
    with pytest.raises(ValueError, match='byte_limit'): validate(fixture, target)


def test_destination_ancestor_symlink_rejected(fixture, tmp_path):
    export_paths = paths(tmp_path, fixture[1])
    alias = tmp_path / 'linked'
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(OSError):
        streams.write_report_files_zip_from_paths(fixture[2], export_paths, alias / 'family.zip',
            expected_identity=fixture[0], expected_bundle_manifest_sha256=fixture[2]['manifest_sha256'])
    assert not (tmp_path / 'family.zip').exists()


def test_input_read_interruption_does_not_publish(fixture, tmp_path, monkeypatch):
    monkeypatch.setattr(streams, '_read', lambda *a, **k: (_ for _ in ()).throw(OSError('read interrupted')))
    with pytest.raises(OSError, match='read interrupted'): write(fixture, tmp_path)
    assert not (tmp_path / 'family.zip').exists()
    assert not list(tmp_path.glob('.nico-family-*'))


def test_multichunk_exports_keep_exact_zip_bytes(fixture, tmp_path):
    identity, original, bundle, _, _ = fixture
    exports = {**original, 'markdown_report': 'Retained complete evidence line.\n' * 9000,
               'html_report': '<p>Retained complete evidence line.</p>\n' * 9000}
    assert len(exports['markdown_report']) > streams.CHUNK_BYTES * 2
    family = transport.build_report_files(bundle, exports, expected_identity=identity,
        expected_bundle_manifest_sha256=bundle['manifest_sha256'])
    expected = transport.report_files_zip(family, expected_identity=identity, expected_manifest_sha256=family['manifest_sha256'])
    updated = (identity, exports, bundle, family, expected)
    write(updated, tmp_path)
    assert (tmp_path / 'family.zip').read_bytes() == expected
    assert validate(updated, tmp_path / 'family.zip')['manifest_sha256'] == family['manifest_sha256']


def test_parent_traversal_is_not_normalized_past_symlink(fixture, tmp_path):
    export_paths = paths(tmp_path, fixture[1])
    alias = tmp_path / 'alias'
    alias.symlink_to(tmp_path, target_is_directory=True)
    export_paths['markdown_report'] = alias / '..' / 'report.md'
    with pytest.raises(ValueError, match='parent_path'):
        write(fixture, tmp_path, export_paths)
    assert not (tmp_path / 'family.zip').exists()
