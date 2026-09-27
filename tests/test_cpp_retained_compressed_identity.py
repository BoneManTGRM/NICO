"""Owned SQLite artifact corruption controls; never a production store."""
from copy import deepcopy
import gzip
import hashlib
import sqlite3

import pytest
from nico.assessment_cpp_configure_first_projection import _read_artifact
from nico.assessment_worker_jobs import JobIdentity
from nico.scanner_raw_artifact_storage_v1 import ScannerArtifactStore


@pytest.fixture
def stored(tmp_path):
    database = tmp_path / 'owned.sqlite3'
    store = ScannerArtifactStore(lambda: sqlite3.connect(database), dialect='sqlite')
    store.ensure_schema()
    identity = JobIdentity('customer', 'project', 'run', 'scan', 'owned/control', 'a'*40, 'b'*64, 'c'*40)
    key = 'project-static-evidence'
    raw = b'{"source":"owned-generated-fixture","findings":[]}'
    compressed = gzip.compress(raw, mtime=0)
    binding = {'customer_id':identity.customer_id, 'project_id':identity.project_id,
        'run_id':identity.run_id, 'scan_id':identity.scan_id, 'repository':identity.repository_id,
        'commit_sha':identity.revision, 'scanner_name':'cppcheck:'+key}
    raw_hash = hashlib.sha256(raw).hexdigest()
    artifact_id = store.put(binding, compressed, raw_hash)
    reference = {'artifact_id':artifact_id, 'key':key, 'storage_backend':'postgres',
        'sha256':raw_hash,'gzip_sha256':hashlib.sha256(compressed).hexdigest(),
        'gzip_bytes':len(compressed),'retained_bytes':len(raw)}
    return store, identity, reference, key, raw, compressed


@pytest.mark.parametrize('position',[4,5,6,7,9])
def test_changed_compressed_header_rejects_even_when_raw_bytes_match(stored,position):
    store,identity,reference,key,raw,compressed = stored
    changed=bytearray(compressed); changed[position] ^= 1; changed=bytes(changed)
    assert gzip.decompress(changed) == raw
    assert hashlib.sha256(changed).hexdigest() != reference['gzip_sha256']
    with store.connect() as connection:
        connection.execute('UPDATE scanner_raw_artifacts SET gzip_blob=? WHERE artifact_id=?',
                           (changed,reference['artifact_id']))
        connection.commit()
    # Cached digest columns deliberately stay unchanged in this owned fault.
    assert store.get(reference['artifact_id'],limit=10000)['gzip_sha256']==reference['gzip_sha256']
    with pytest.raises(ValueError,match='worker_configure_first_artifact_digest_invalid'):
        _read_artifact(store,identity,reference,key)


def test_unchanged_compressed_edition_reopens_and_reads_identically(stored):
    store,identity,reference,key,raw,compressed=stored
    reopened=ScannerArtifactStore(store.connect,dialect='sqlite')
    assert _read_artifact(store,identity,reference,key)==raw
    assert _read_artifact(reopened,identity,reference,key)==raw
    assert reopened.get(reference['artifact_id'],limit=10000)['compressed']==compressed


def test_wrong_raw_digest_still_rejects(stored):
    store,identity,reference,key,raw,compressed=stored
    wrong=deepcopy(reference); wrong['sha256']='f'*64
    with pytest.raises(ValueError,match='worker_configure_first_artifact_binding_invalid'):
        _read_artifact(store,identity,wrong,key)


def test_wrong_tenant_still_rejects(stored):
    from dataclasses import replace
    store,identity,reference,key,raw,compressed=stored
    with pytest.raises(ValueError,match='worker_configure_first_artifact_binding_invalid'):
        _read_artifact(store,replace(identity,customer_id='different'),reference,key)


@pytest.mark.parametrize('bad',[b'', 'text', bytearray(b'bytes'), memoryview(b'bytes')])
def test_wrong_compressed_type_or_empty_bytes_reject_before_decoding(stored,bad,monkeypatch):
    import nico.assessment_cpp_configure_first_projection as module
    store,identity,reference,key,raw,compressed=stored
    original=store.get(reference['artifact_id'],limit=10000)
    original['compressed']=bad
    monkeypatch.setattr(store,'get',lambda *args,**kwargs:original)
    monkeypatch.setattr(module.gzip,'GzipFile',lambda *a,**kw:pytest.fail('invalid bytes must not reach decompression'))
    with pytest.raises(ValueError,match='worker_configure_first_artifact_digest_invalid'):
        _read_artifact(store,identity,reference,key)


def test_actual_compressed_byte_limit_precedes_decoding(stored,monkeypatch):
    import nico.assessment_cpp_configure_first_projection as module
    store,identity,reference,key,raw,compressed=stored
    original=store.get(reference['artifact_id'],limit=10000)
    original['compressed']=b'x'*(module.MAX_COMPRESSED+1)
    monkeypatch.setattr(store,'get',lambda *args,**kwargs:original)
    monkeypatch.setattr(module.gzip,'GzipFile',lambda *a,**kw:pytest.fail('oversized bytes must not reach decompression'))
    with pytest.raises(ValueError,match='worker_configure_first_artifact_digest_invalid'):
        _read_artifact(store,identity,reference,key)
