"""Owned archive fixtures exercise the actual source adapter; no target code runs."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import time

import pytest

from nico.assessment_worker_source import acquire_public_github_inputs
from tests.test_assessment_cpp_full_project import plan

REVISION = 'a' * 40
TREE = 'b' * 40
PREFIX = 'control-' + REVISION
ARCHIVE_URL = 'https://codeload.github.com/owned/control/tar.gz/' + REVISION


def oid(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw, usedforsecurity=False).hexdigest()


def fixture(count=40):
    files = {path: ('owned inert ' + path + '\n').encode()
             for path in ['CMakeLists.txt', 'main.cpp', 'sum.cpp', 'sum.hpp']}
    files.update({'include/h%04d.hpp' % i: ('#define OWNED_%d %d\n' % (i, i)).encode()
                  for i in range(count - len(files))})
    return files


def make_archive(files, change=None):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.PAX_FORMAT) as output:
        root = tarfile.TarInfo(PREFIX); root.type = tarfile.DIRTYPE
        output.addfile(root)
        for path, raw in sorted(files.items()):
            info = tarfile.TarInfo(PREFIX + '/' + path)
            info.mode = 0o755 if path == 'main.cpp' else 0o644
            info.size = len(raw)
            rows = [(info, raw)]
            if change is not None:
                rows = change(path, info, raw)
            for member, content in rows:
                output.addfile(member, io.BytesIO(content) if member.isreg() else None)
    return gzip.compress(buffer.getvalue(), mtime=0)


def job_and_download(files, *, archive=None, selected=None, tree_change=None):
    selected = files if selected is None else selected
    contract = plan()
    contract['targets'] = {p: hashlib.sha256(raw).hexdigest() for p, raw in selected.items()}
    job = {'identity': {'repository_id': 'https://github.com/owned/control', 'revision': REVISION},
           'contract': contract, 'deadline_epoch': time.time() + 60,
           'source_access': {'mode': 'anonymous_public', 'credential_used': False}}
    entries = [{'path': p, 'type': 'blob', 'mode': '100755' if p == 'main.cpp' else '100644',
                'sha': oid(raw), 'size': len(raw)} for p, raw in files.items()]
    entries += [{'path': 'include', 'type': 'tree', 'mode': '040000', 'sha': 'c' * 40}]
    if tree_change:
        tree_change(entries)
    compressed = make_archive(files) if archive is None else archive
    calls = []
    def download(url, destination, *, limit, checkpoint, deadline):
        checkpoint(); calls.append(url)
        if '/git/commits/' in url:
            raw = json.dumps({'sha': REVISION, 'tree': {'sha': TREE}}).encode()
        elif '/git/trees/' in url:
            raw = json.dumps({'sha': TREE, 'truncated': False, 'tree': entries}).encode()
        else:
            assert url == ARCHIVE_URL, 'large population still uses one request per blob: ' + url
            raw = compressed
        assert len(raw) <= limit
        destination.write_bytes(raw)
    return job, download, calls


def acquire(tmp_path, **kwargs):
    tmp_path.chmod(0o700)
    files = kwargs.pop('files', fixture())
    job, download, calls = job_and_download(files, **kwargs)
    root, evidence = acquire_public_github_inputs(job, tmp_path, lambda: None, download=download)
    return files, root, evidence, calls


def test_large_population_uses_one_archive_and_preserves_all_original_bytes(tmp_path):
    files, root, evidence, calls = acquire(tmp_path)
    assert len(calls) == 3 and calls[-1] == ARCHIVE_URL
    assert {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()} == files
    assert evidence['required_count'] == evidence['materialized_count'] == len(files)
    assert evidence['source_bytes'] == sum(map(len, files.values()))
    assert evidence['commit_sha'] == REVISION and evidence['tree_sha'] == TREE
    assert evidence['analyzed_count'] is None and evidence['authorized'] is False
    assert evidence['assessed_code_executed'] is False
    assert (root / 'main.cpp').stat().st_mode & 0o777 == 0o555
    assert (root / 'sum.cpp').stat().st_mode & 0o777 == 0o444
    assert not list(tmp_path.glob('.nico-source-*'))


def test_archive_transport_receipt_retains_budgets_hash_and_actual_populations(tmp_path):
    files = fixture(); raw = make_archive(files)
    _, _, evidence, _ = acquire(tmp_path, files=files, archive=raw)
    transport = evidence['transport']
    assert transport['kind'] == 'github_exact_commit_tar'
    assert transport['archive_sha256'] == hashlib.sha256(raw).hexdigest()
    assert transport['compressed_bytes'] == len(raw)
    assert transport['expanded_bytes'] == len(gzip.decompress(raw))
    assert transport['archive_files'] == len(files)
    assert transport['selected_files'] == len(files)
    assert transport['network_requests'] == 3


def test_unselected_regular_blobs_are_verified_but_never_materialized(tmp_path):
    selected = fixture(); files = dict(selected, **{'README.md': b'not selected\n'})
    _, root, evidence, calls = acquire(tmp_path, files=files, selected=selected)
    assert not (root / 'README.md').exists()
    assert evidence['materialized_count'] == len(selected)
    assert evidence['transport']['archive_files'] == len(files)
    assert calls[-1] == ARCHIVE_URL


@pytest.mark.parametrize('kind', ['path', 'prefix', 'absolute', 'duplicate', 'missing', 'extra',
                                  'digest', 'size', 'symlink', 'hardlink', 'fifo'])
def test_bad_archive_is_never_promoted_or_retried_as_individual_blobs(tmp_path, kind):
    files = fixture()
    def change(path, info, raw):
        if path != 'main.cpp':
            return [(info, raw)]
        if kind == 'path': info.name = PREFIX + '/../outside.cpp'
        elif kind == 'prefix': info.name = 'other-' + REVISION + '/main.cpp'
        elif kind == 'absolute': info.name = '/tmp/owned-archive-test'
        elif kind == 'duplicate': return [(info, raw), (info, raw)]
        elif kind == 'missing': return []
        elif kind == 'extra': info.name = PREFIX + '/unknown.cpp'
        elif kind == 'digest': raw = b'x' * len(raw)
        elif kind == 'size': raw += b'x'; info.size = len(raw)
        else:
            info.type = {'symlink': tarfile.SYMTYPE, 'hardlink': tarfile.LNKTYPE,
                         'fifo': tarfile.FIFOTYPE}[kind]
            info.linkname = '../outside.cpp'; info.size = 0
        return [(info, raw)]
    job, download, calls = job_and_download(files, archive=make_archive(files, change))
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError, match='worker_source_'):
        acquire_public_github_inputs(job, tmp_path, lambda: None, download=download)
    assert calls[-1] == ARCHIVE_URL and len(calls) == 3
    assert not (tmp_path / 'source').exists()
    assert not list(tmp_path.glob('.nico-source-*'))


@pytest.mark.parametrize('kind', ['bad_gzip', 'truncated', 'trailing_data', 'second_tar'])
def test_corrupt_or_concatenated_archive_is_rejected_before_promotion(tmp_path, kind):
    files = fixture(); raw = make_archive(files)
    if kind == 'bad_gzip': raw = b'not gzip'
    elif kind == 'truncated': raw = raw[:-8]
    elif kind == 'trailing_data': raw = gzip.compress(gzip.decompress(raw) + b'nonzero extra data')
    else: raw += make_archive(files)
    job, download, _ = job_and_download(files, archive=raw)
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError, match='worker_source_'):
        acquire_public_github_inputs(job, tmp_path, lambda: None, download=download)
    assert not (tmp_path / 'source').exists()
    assert not list(tmp_path.glob('.nico-source-*'))


def test_lease_loss_during_archive_validation_removes_staged_bytes(tmp_path):
    job, download, calls = job_and_download(fixture())
    tmp_path.chmod(0o700)
    ticks = 0
    def checkpoint():
        nonlocal ticks
        if calls and calls[-1] == ARCHIVE_URL:
            ticks += 1
            if ticks == 4: raise ValueError('worker_local_lease_expired')
    with pytest.raises(ValueError, match='worker_local_lease_expired'):
        acquire_public_github_inputs(job, tmp_path, checkpoint, download=download)
    assert not (tmp_path / 'source').exists()
    assert not list(tmp_path.glob('.nico-source-*'))


def test_expansion_budget_applies_to_tar_padding_as_well_as_selected_files(tmp_path, monkeypatch):
    import nico.assessment_worker_source as source
    # A small deterministic budget proves enforcement without a real large bomb.
    monkeypatch.setattr(source, 'MAX_ARCHIVE_EXPANDED_BYTES', 4096, raising=False)
    files = fixture()
    job, download, _ = job_and_download(files)
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError, match='worker_source_archive_expansion_budget'):
        acquire_public_github_inputs(job, tmp_path, lambda: None, download=download)
    assert not (tmp_path / 'source').exists()


def test_frozen_sha256_is_checked_even_when_git_blob_and_archive_are_consistent(tmp_path):
    job, download, _ = job_and_download(fixture())
    job['contract']['targets']['main.cpp'] = 'f' * 64
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError, match='worker_source_digest_mismatch'):
        acquire_public_github_inputs(job, tmp_path, lambda: None, download=download)
    assert not (tmp_path / 'source').exists()


def test_long_pax_paths_preserve_source_names(tmp_path):
    files = fixture()
    files['include/' + 'h' * 180 + '.hpp'] = b'owned long filename\n'
    _, root, _, _ = acquire(tmp_path, files=files)
    assert (root / ('include/' + 'h' * 180 + '.hpp')).read_bytes() == b'owned long filename\n'


@pytest.mark.parametrize('count,large_unselected', [(4, False), (40, True)])
def test_small_or_archive_oversized_trees_keep_the_existing_exact_blob_path(tmp_path, count, large_unselected):
    from urllib.parse import unquote
    from nico.assessment_worker_source import MAX_ARCHIVE_BYTES
    files = fixture(count)
    def tree_change(entries):
        if large_unselected:
            entries.append({'path': 'not-selected.bin', 'type': 'blob', 'mode': '100644',
                            'sha': 'd' * 40, 'size': MAX_ARCHIVE_BYTES + 1})
    job, metadata, calls = job_and_download(files, tree_change=tree_change)
    def download(url, destination, **kwargs):
        if url.startswith('https://api.github.com/'):
            return metadata(url, destination, **kwargs)
        assert url.startswith('https://raw.githubusercontent.com/owned/control/' + REVISION + '/')
        calls.append(url)
        path = unquote(url.split('/' + REVISION + '/', 1)[1])
        destination.write_bytes(files[path])
    tmp_path.chmod(0o700)
    root, evidence = acquire_public_github_inputs(job, tmp_path, lambda: None, download=download)
    assert len(calls) == len(files) + 2 and ARCHIVE_URL not in calls
    assert 'transport' not in evidence
    assert evidence['schema'] == 'nico.github_https_input_materialization.v1'
    assert (root / 'main.cpp').read_bytes() == files['main.cpp']


@pytest.mark.parametrize('url', [
    'https://codeload.github.com/owned/control/tar.gz/main',
    'https://codeload.github.com/owned/control/tar.gz/' + REVISION[:8],
    ARCHIVE_URL + '?token=synthetic', ARCHIVE_URL + '#fragment',
    ARCHIVE_URL.replace('https://', 'http://'),
    ARCHIVE_URL.replace('codeload.github.com', 'codeload.github.com.evil.invalid'),
    ARCHIVE_URL.replace('codeload.github.com', 'codeload.github.com:443'),
    ARCHIVE_URL.replace('codeload.github.com', 'user@codeload.github.com'),
    ARCHIVE_URL.replace('/tar.gz/', '/zip/'),
])
def test_archive_download_host_and_immutable_ref_cannot_be_substituted(tmp_path, monkeypatch, url):
    from nico import assessment_worker_source as source
    monkeypatch.setattr(source.multiprocessing, 'get_context', lambda *a: pytest.fail('process reached'))
    with pytest.raises(ValueError, match='worker_source_request_invalid'):
        source.download_public(url, tmp_path / 'archive', limit=source.MAX_ARCHIVE_BYTES,
                               checkpoint=lambda: None, deadline=time.monotonic() + 1)


def test_archive_limit_does_not_expand_ordinary_blob_downloads(tmp_path, monkeypatch):
    from nico import assessment_worker_source as source
    monkeypatch.setattr(source.multiprocessing, 'get_context', lambda *a: pytest.fail('process reached'))
    with pytest.raises(ValueError, match='worker_source_request_invalid'):
        source.download_public('https://raw.githubusercontent.com/owned/control/' + REVISION + '/main.cpp',
                               tmp_path / 'blob', limit=source.MAX_BYTES + 1,
                               checkpoint=lambda: None, deadline=time.monotonic() + 1)


@pytest.mark.parametrize('status,encoding', [(200, 'identity'), (302, 'identity'), (200, 'gzip')])
def test_archive_transport_never_uses_credentials_redirects_or_implicit_expansion(tmp_path, monkeypatch, status, encoding):
    from nico import assessment_worker_source as source
    calls = []
    class Response:
        status_code = status
        headers = {'Content-Encoding': encoding}
        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield b'owned bounded bytes'
        def close(self): pass
    class Session:
        trust_env = True
        def get(self, url, **kwargs):
            assert self.trust_env is False
            calls.append(kwargs)
            return Response()
        def close(self): pass
    monkeypatch.setattr(source.requests, 'Session', Session)
    output = tmp_path / 'archive'
    source._download_child(ARCHIVE_URL, output, 1024)
    assert calls[0]['headers'] == {'Accept': 'application/octet-stream', 'Accept-Encoding': 'identity'}
    assert calls[0]['allow_redirects'] is False and calls[0]['stream'] is True
    assert output.exists() is (status == 200 and encoding == 'identity')
