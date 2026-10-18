"""Invocation-local reuse against a frozen independent validator oracle."""
from collections import Counter, UserDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import sys
from pathlib import Path
from threading import Barrier

import pytest
from nico import comprehensive_exact_artifact_hash_binding_v1 as subject


def baseline():
    scope = vars(subject).copy()
    path = Path(__file__).parent/'fixtures/exact_artifact_validator_4886d4bf.txt'
    exec(compile(path.read_text(), str(path), 'exec'), scope)
    return scope['_validate_exact_artifact_hashes']


@pytest.fixture(scope='module')
def package():
    from tests.test_comprehensive_artifact_manifest_approval_v1 import _package
    from nico.comprehensive_artifact_manifest_approval_v1 import attach_artifact_manifest
    return attach_artifact_manifest(_package())


def outcome(validate, value):
    try:
        return ('return', validate(value))
    except Exception as exc:
        return (type(exc).__name__, str(exc))


def mutations(value):
    # Remove every top-level claim and alter every detached/canonical entry,
    # authority field and identity binding. Rebind only the detached text so
    # late comparisons are reached; never manufacture an accepted artifact.
    for field in value:
        item = deepcopy(value); item.pop(field)
        yield 'missing:'+field, item
    for field in ('pdf_base64','canonical_json','evidence_manifest_json','markdown','html',
                  'findings_csv','evidence_csv','candidate_register_json','remediation_backlog_json'):
        for replacement in ('', 'invalid', None, 42):
            item=deepcopy(value);item[field]=replacement
            yield 'body:'+field+repr(replacement),item
    for target in ('artifact_manifest','draft_artifact_identity'):
        for field in value[target]:
            item=deepcopy(value);item[target][field]='invalid'
            if target=='artifact_manifest':
                item['evidence_manifest_json']=json.dumps(item[target])
                item['evidence_manifest_sha256']=hashlib.sha256(item['evidence_manifest_json'].encode()).hexdigest()
            yield target+':'+field,item
    for target in ('identity','assessment','artifact_manifest'):
        for field in value['json'][target]:
            item=deepcopy(value);item['json'][target][field]='invalid'
            yield 'canonical:'+target+':'+field,item
    for field in subject._CANONICAL_DRAFT_AUTHORITY_FIELDS:
        item=deepcopy(value);item['json'][field]='invalid'
        yield 'authority:'+field,item
    for index, entry in enumerate(value['artifact_manifest']['artifacts']):
        for field in entry:
            item=deepcopy(value);item['artifact_manifest']['artifacts'][index][field]='invalid'
            yield 'entry:'+str(index)+':'+field,item


def test_valid_bytes_and_rejection_contract_match_baseline(package):
    old=baseline(); before=deepcopy(package)
    assert outcome(old,package)==outcome(subject._validate_exact_artifact_hashes,package)==('return',None)
    checked=0
    for label,item in mutations(package):
        original=deepcopy(item)
        assert outcome(old,item)==outcome(subject._validate_exact_artifact_hashes,item),label
        assert item==original,label
        checked+=1
    assert checked>150
    assert package==before


def test_one_materialization_and_hash_per_artifact(package, monkeypatch):
    reads=Counter(); hashes=Counter(); decodes=[]
    read=subject._artifact_bytes; sha=subject._sha256; decode=subject.base64.b64decode
    expected=Counter(read(package,entry['artifact_type']) for entry in package['artifact_manifest']['artifacts'])
    expected[package['evidence_manifest_json'].encode()]+=1
    def observe_read(result,kind):
        reads[kind]+=1
        return read(result,kind)
    def observe_hash(content):
        hashes[content]+=1
        return sha(content)
    def observe_decode(*args,**kwargs):
        decodes.append(1)
        return decode(*args,**kwargs)
    monkeypatch.setattr(subject,'_artifact_bytes',observe_read)
    monkeypatch.setattr(subject,'_sha256',observe_hash)
    monkeypatch.setattr(subject.base64,'b64decode',observe_decode)
    # Each new invocation must independently repeat the complete checks.
    for _ in range(2):
        reads.clear();hashes.clear();decodes.clear()
        encodings=Counter()
        def profile(frame, event, operation):
            if event == 'c_call' and getattr(operation, '__name__', '') == 'encode':
                for field in ('canonical_json', 'evidence_manifest_json'):
                    if getattr(operation, '__self__', None) is package[field]:
                        encodings[field]+=1
        previous=sys.getprofile()
        try:
            sys.setprofile(profile)
            subject._validate_exact_artifact_hashes(package)
        finally:
            sys.setprofile(previous)
        assert encodings == {'canonical_json': 1, 'evidence_manifest_json': 1}
        assert reads==Counter({key:1 for key in subject._REQUIRED_DETACHED_ARTIFACT_TYPES})
        assert hashes==expected
        assert len(decodes)==1


def test_later_tampering_and_custom_mapping_keep_original_rejections(package):
    old=baseline()
    subject._validate_exact_artifact_hashes(package)
    for field in ('pdf_base64','canonical_json','markdown','evidence_manifest_json'):
        item=deepcopy(package);item[field]+='tampered'
        expected=outcome(old,item)
        assert expected[0]!='return'
        assert outcome(subject._validate_exact_artifact_hashes,item)==expected
    assert outcome(old,UserDict(package))==outcome(subject._validate_exact_artifact_hashes,UserDict(package))


@pytest.mark.parametrize('field', ['pdf_base64','canonical_json'])
def test_mid_invocation_replacement_is_not_trusted(package, monkeypatch, field):
    old=baseline(); sha=subject._sha256
    def run(validate):
        item=deepcopy(package)
        def change(content):
            if content==item['evidence_manifest_json'].encode():
                item[field]='invalid'
            return sha(content)
        # This seam changes the package after its initial artifact checks.
        globals_=validate.__globals__; original=globals_['_sha256'];globals_['_sha256']=change
        try:return outcome(validate,item)
        finally:globals_['_sha256']=original
    expected=run(old)
    assert expected[0]!='return'
    assert run(subject._validate_exact_artifact_hashes)==expected


def test_concurrent_calls_have_no_shared_observations(package):
    gate=Barrier(8)
    def validate(index):
        item=deepcopy(package)
        if index%2:item['canonical_json']+='tampered'
        expected=outcome(baseline(),item)
        gate.wait(timeout=10)
        return expected,outcome(subject._validate_exact_artifact_hashes,item)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for expected,actual in pool.map(validate,range(8)):
            assert actual==expected
