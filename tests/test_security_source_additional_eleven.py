"""Approved metadata only; no scanner execution, secret values or raw matches."""
from copy import deepcopy
import hashlib
import json

import pytest
from scripts import security_source_dispositions as subject
from scripts import security_audit_gate as gate
from tests.test_security_source_dispositions import synthetic, independent_pair, indices, write_capture

EVIDENCE = subject.MANIFEST.with_name('additional-eleven-evidence-v1.json')


def test_exact_extension_preserves_every_previous_entry():
    current = json.loads(subject.MANIFEST.read_bytes())
    previous = deepcopy(current)
    previous['entries'] = previous['entries'][:23]
    del previous['additional_eleven_evidence_sha256']
    # Canonical digest of the complete pre-extension manifest at 54e31a94.
    # No Git history dependency: this control also runs in source archives.
    assert hashlib.sha256(subject._canonical(previous)).hexdigest() == '88a6fd507d87497538105c877a9021129043067814d1cd1c83bfe17b6e59624b'
    assert len(current['entries']) == 34
    assert hashlib.sha256(EVIDENCE.read_bytes()).hexdigest() == current['additional_eleven_evidence_sha256']


def test_all_eleven_full_shapes_independently_recompute_from_approved_metadata():
    evidence = json.loads(EVIDENCE.read_bytes())
    approved = subject._approved_bindings()
    pairs = []
    for row in evidence['occurrences']:
        fingerprint = f"{row['commit']}:{row['path']}:{row['rule_id']}:{row['start_line']}"
        shape = [row[k] for k in ('commit', 'path', 'rule_id', 'start_line',
                                  'end_line', 'start_column', 'end_column')]
        shape += [fingerprint, row['redacted_match_sha256'], 'REDACTED', 'verified_absent']
        pair = (hashlib.sha256(fingerprint.encode()).hexdigest(),
                hashlib.sha256(json.dumps(shape, sort_keys=True, separators=(',', ':'),
                                          ensure_ascii=False).encode()).hexdigest())
        assert pair == (row['fingerprint_sha256'], row['full_shape_sha256'])
        assert pair in approved
        for position in (0, 1):
            changed = list(pair)
            changed[position] = ('0' if pair[position][0] != '0' else '1') + pair[position][1:]
            assert tuple(changed) not in approved
        pairs.append(pair)
    assert len(set(pairs)) == 11 and len({p[0] for p in pairs}) == 10
    assert pairs[-1][0] == pairs[-2][0] and pairs[-1][1] != pairs[-2][1]
    assert set(pairs) == {(e['fingerprint_sha256'], e['shape_sha256'])
                          for e in json.loads(subject.MANIFEST.read_bytes())['entries'][23:]}
    assert evidence['direct_match_column_reconstruction_unestablished'] == [3, 4, 5, 6, 7, 20]
    assert evidence['independent_preimage_review'] == 'immutable_pin_comparison_not_direct_preimage_read'
    assert evidence['hosted_effective_configuration'] == 'unobserved'
    assert evidence['hidden_value_authentication'] is False


@pytest.fixture
def approved34(tmp_path, monkeypatch):
    data = [synthetic(i) for i in range(34)]
    # A second shared fingerprint, distinguished only by its full occurrence shape.
    data[33] = deepcopy(data[32])
    data[33].update(StartColumn=40, EndColumn=69)
    manifest = json.loads(subject.MANIFEST.read_bytes())
    for entry, finding in zip(manifest['entries'], data):
        entry['fingerprint_sha256'], entry['shape_sha256'] = independent_pair(finding)
    raw = subject._canonical(manifest)
    path = tmp_path / 'manifest.json'
    path.write_bytes(raw)
    monkeypatch.setattr(subject, 'MANIFEST', path)
    monkeypatch.setattr(subject, 'MANIFEST_SHA256', hashlib.sha256(raw).hexdigest())
    assert len(subject._approved_bindings()) == 34
    return data


def test_full_loader_matches34_and_retains_all78_findings(approved34, tmp_path):
    data = approved34 + [synthetic(100+i) for i in range(44)]
    write_capture(tmp_path, data)
    result = gate._gitleaks(tmp_path)
    assert len(result['triage']) == 78
    assert result['approved_public_source_hashes'] == 34
    assert result['blocking'] == 44
    assert [r['disposition'] for r in result['triage']] == ['approved_public_source_hash']*34 + ['blocking']*44


@pytest.mark.parametrize('index', range(23, 34))
@pytest.mark.parametrize('field', sorted(subject.REQUIRED))
def test_every_new_bound_field_mutation_or_omission_stays_blocked(approved34, index, field):
    changed = deepcopy(approved34)
    value = changed[index][field]
    changed[index][field] = value+1 if type(value) is int else value+' changed'
    assert index not in indices(changed)
    changed = deepcopy(approved34)
    del changed[index][field]
    assert not indices(changed)


def test_duplicate_or_new_same_fingerprint_shape_cannot_broaden(approved34):
    assert indices(approved34) == frozenset(range(34))
    assert not indices(approved34 + [deepcopy(approved34[-1])])
    changed = deepcopy(approved34)
    changed[-1].update(StartColumn=80, EndColumn=109)
    assert indices(changed) == frozenset(range(33))
