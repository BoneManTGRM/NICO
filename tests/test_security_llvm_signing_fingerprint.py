"""The exact retained LLVM public signing fingerprint is not an API secret."""
from copy import deepcopy
import json

import pytest

from scripts.security_audit_gate import _gitleaks

COMMIT = '684e5af5074c6e1c0cf4b67fa263b0d79b8beabf'
PATH = 'docker/assessment-llvm17.lock.json'


def observation():
    return {'File': PATH, 'RuleID': 'generic-api-key', 'Secret': 'REDACTED',
            'Match': 'llvm_signing_key_fingerprint": "REDACTED"',
            'Commit': COMMIT, 'StartLine': 5, 'EndLine': 5,
            'StartColumn': 5, 'EndColumn': 77,
            'Fingerprint': COMMIT + ':' + PATH + ':generic-api-key:5'}


def gate(tmp_path, records):
    (tmp_path / 'gitleaks.json').write_text(json.dumps(records))
    (tmp_path / 'gitleaks-summary.json').write_text(json.dumps({'status': 'completed', 'finding_count': len(records)}))
    return _gitleaks(tmp_path)


def test_exact_public_fingerprint_is_retained_with_nonsecret_disposition(tmp_path):
    rows = [observation()]; before = deepcopy(rows)
    result = gate(tmp_path, rows)
    assert result['blocking'] == 0
    assert result['finding_count'] == 1
    assert result['approved_public_signing_fingerprints'] == 1
    assert result['triage'][0]['disposition'] == 'approved_public_signing_fingerprint'
    assert rows == before
    assert json.loads((tmp_path / 'gitleaks.json').read_text()) == rows


@pytest.mark.parametrize('field,value', [
    ('File', 'other.json'), ('Commit', 'a' * 40), ('RuleID', 'private-key'),
    ('Secret', 'unredacted-value'), ('Match', 'token": "REDACTED"'),
    ('StartLine', 6), ('EndLine', 6), ('StartColumn', 6), ('EndColumn', 76),
    ('Fingerprint', 'different'), ('Verified', True), ('Verified', 'false'),
])
def test_only_the_reviewed_immutable_observation_is_dispositioned(tmp_path, field, value):
    changed = observation(); changed[field] = value
    result = gate(tmp_path, [changed])
    assert result['blocking'] == 1
    assert result['triage'][0]['disposition'] == 'blocking'


def test_new_observation_or_malformed_member_still_blocks(tmp_path):
    other = observation(); other['Commit'] = 'b' * 40
    result = gate(tmp_path, [observation(), other, 'malformed'])
    assert result['finding_count'] == 3 and result['blocking'] == 2
