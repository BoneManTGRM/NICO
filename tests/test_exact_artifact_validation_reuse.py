"""Integrity parity and shared-dictionary mutation regression controls."""
from collections import Counter, UserDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from threading import Barrier

import pytest
from nico import comprehensive_exact_artifact_hash_binding_v1 as subject


def baseline():
    scope = vars(subject).copy()
    path = Path(__file__).parent/'fixtures/exact_artifact_validator_4886d4bf.txt'
    # Historical validator body, with current conversion helpers: an outcome
    # oracle, not a claim to replay the complete historical runtime.
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
        expected = outcome(old, item)
        assert item == original, label
        assert outcome(subject._validate_exact_artifact_hashes, item) == expected, label
        assert item == original, label
        checked+=1
    assert checked>150
    assert package==before


@pytest.mark.parametrize('field,accepted', [
    ('pdf_page_count', True), ('core_report_page_count', True),
    ('pdf_base64', False), ('canonical_json', False), ('artifact_manifest', False),
])
def test_optional_presentation_metadata_is_distinct_from_required_artifact_bytes(package, field, accepted):
    # Optional here means only this validator's contract, not API/delivery readiness.
    item = deepcopy(package)
    item.pop(field)
    before = deepcopy(item)
    expected = outcome(baseline(), item)
    assert (expected[0] == 'return') is accepted
    assert outcome(subject._validate_exact_artifact_hashes, item) == expected
    assert item == before


def test_artifact_extraction_is_single_read_and_invocation_local(package, monkeypatch):
    reads = Counter()
    original = subject._artifact_content
    def observe(result, kind):
        reads[kind] += 1
        return original(result, kind)
    monkeypatch.setattr(subject, '_artifact_content', observe)
    for _ in range(2):
        reads.clear()
        subject._validate_exact_artifact_hashes(package)
        assert reads == Counter({kind: 1 for kind in subject._REQUIRED_DETACHED_ARTIFACT_TYPES})


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


@pytest.mark.parametrize('field,kind', [
    ('pdf_base64', 'comprehensive_pdf'), ('canonical_json', 'canonical_json'),
])
def test_same_dictionary_aba_rejects_mismatched_retained_bytes(package, monkeypatch, field, kind):
    """Extraction returns B and its actual identity; later A must not reuse B's proof."""
    original = subject._artifact_content
    item = deepcopy(package)
    valid_b = item[field]
    invalid_a = (subject.base64.b64encode(subject.base64.b64decode(valid_b) + b'\n').decode('ascii')
                 if field == 'pdf_base64' else valid_b + ' ')
    item[field] = invalid_a
    gate = Barrier(2)
    observations = []

    def extract(result, artifact_type):
        if artifact_type != kind:
            return original(result, artifact_type)
        gate.wait(timeout=2)  # Mutation begins at the actual extraction boundary.
        gate.wait(timeout=2)
        content, captured_source = original(result, artifact_type)
        observations.append((content, captured_source))
        gate.wait(timeout=2)
        gate.wait(timeout=2)
        return content, captured_source

    def mutate():
        gate.wait(timeout=2)
        item[field] = valid_b
        gate.wait(timeout=2)
        gate.wait(timeout=2)
        item[field] = invalid_a
        gate.wait(timeout=2)

    monkeypatch.setattr(subject, '_artifact_content', extract)
    with ThreadPoolExecutor(max_workers=1) as pool:
        mutation = pool.submit(mutate)
        try:
            actual = outcome(subject._validate_exact_artifact_hashes, item)
            mutation.result(timeout=3)
        finally:
            gate.abort()
    assert len(observations) == 1
    assert observations[0][1] is valid_b
    assert observations[0][0] == (subject.base64.b64decode(valid_b) if field == 'pdf_base64' else valid_b.encode())
    assert item[field] is invalid_a
    monkeypatch.setattr(subject, '_artifact_content', original)
    expected = outcome(baseline(), item)
    assert expected[0] == 'ValueError'
    assert actual[0] == 'ValueError'
    assert ('canonical' in actual[1].lower() or 'draft artifact identity' in actual[1].lower())
