"""Characterize full gate records using only synthetic on-disk capture bytes."""
import hashlib
import json

import pytest

from scripts.security_audit_gate import _trufflehog


SUMMARY = {
    'schema': 'nico.security-audit.trufflehog.capture.v1',
    'scanner': 'trufflehog', 'status': 'completed', 'finding_count': 1,
    'artifact_present': True, 'history_depth': 'full', 'exit_code': 0,
    'invalid_json_lines': 0, 'live_credential_verification': False,
    'raw_capture_sha256': 'a' * 64, 'sanitized_artifact_sha256': '',
    'raw_candidate_bodies_retained': False,
}
FINDING = {
    'SanitizationSchema': 'nico.security-audit.trufflehog.finding.v1',
    'DetectorName': 'SyntheticDetector', 'DetectorType': 999, 'Verified': False,
    'RawSHA256': 'b' * 64,
    'SourceMetadata': {'Data': {'Git': {'file': 'nico/synthetic.py', 'commit': 'c' * 40, 'line': 12}}},
}

# Each mutation has a stable name for baseline/current differential replay.
CASES = [('valid', None, None), ('exit183', None, None), ('verified', None, None),
         ('fixture', None, None), ('empty', None, None), ('optional_fields', None, None),
         ('partial', None, None), ('partial_bad_completed_fields', None, None)]
CASES += [('summary', key, value) for key, values in {
    'finding_count': [True, '1', 1.0, None, 0],
    'invalid_json_lines': [False, '0', -1, None, 1],
    'exit_code': [False, '0', None, 1],
    'artifact_present': [1, False], 'live_credential_verification': [0, True],
    'raw_candidate_bodies_retained': [0, True], 'history_depth': ['shallow'],
    'raw_capture_sha256': [None, 'A' * 64, 'a' * 63],
    'sanitized_artifact_sha256': ['d' * 64], 'schema': ['unknown'],
    'scanner': ['other'], 'unexpected': ['SYNTHETIC_BODY'],
}.items() for value in values]
CASES += [('missing_summary', key, None) for key in SUMMARY]
CASES += [('finding', key, value) for key, values in {
    'DetectorName': [None, 1], 'DetectorType': [True, '999'], 'Verified': [0, 'false', None],
    'RawSHA256': [None, 'B' * 64, 'b' * 63], 'Raw': ['SYNTHETIC_BODY'],
    'SourceMetadata': [None, [], {}, {'Data': {}}, {'Data': None}, {'Data': {'Git': []}},
                       {'Data': {'Git': {}, 'extra': 'SYNTHETIC_BODY'}}],
}.items() for value in values]
CASES += [('missing_finding', key, None) for key in FINDING if key != 'DetectorType']
CASES += [('git', key, value) for key, value in [
    ('file', 1), ('commit', None), ('line', True), ('line', '12'), ('extra', 'SYNTHETIC_BODY')]]
CASES += [(name, None, None) for name in (
    'strict_both_missing', 'legacy_both_missing', 'strict_both_invalid', 'legacy_both_invalid',
    'strict_summary_missing', 'legacy_summary_missing', 'row_claim_summary_missing',
    'summary_claim_invalid_row', 'strict_legacy_empty', 'legacy_empty',
)]


def prepare_case(root, case):
    """Write fixed inputs and return the exact expected public gate record."""
    kind, key, value = case
    summary = dict(SUMMARY)
    row = json.loads(json.dumps(FINDING))
    count, reason, disposition = 1, None, 'blocking_unverified_non_fixture'
    strict = not kind.startswith('legacy_')
    if kind == 'exit183': summary['exit_code'] = 183
    elif kind == 'verified':
        row['Verified'] = True
        disposition = 'blocking_verified_secret'
    elif kind == 'fixture':
        row['SourceMetadata']['Data']['Git']['file'] = 'tests/synthetic.py'
        disposition = 'approved_unverified_test_placeholder'
    elif kind == 'optional_fields':
        row.pop('DetectorType')
        row['SourceMetadata']['Data']['Git'] = {}
    elif kind in {'partial', 'partial_bad_completed_fields'}:
        summary['status'] = 'failed'
        reason = 'unexpected_json_shape'
        if kind == 'partial_bad_completed_fields':
            summary.update(exit_code=1, invalid_json_lines=2, artifact_present=False, raw_capture_sha256=None)
    elif kind == 'summary': reason = 'invalid_sanitized_capture'
    elif kind == 'missing_summary':
        summary.pop(key)
        reason = 'invalid_sanitized_capture'
    elif kind == 'finding':
        row[key] = value
        reason = 'invalid_sanitized_capture'
    elif kind == 'missing_finding':
        row.pop(key)
        reason = 'invalid_sanitized_capture'
    elif kind == 'git':
        row['SourceMetadata']['Data']['Git'][key] = value
        reason = 'invalid_sanitized_capture'
    raw = (json.dumps(row, sort_keys=True) + '\n').encode()
    if kind in {'empty', 'strict_legacy_empty', 'legacy_empty'}:
        raw, count = b'', 0
        summary['finding_count'] = 0
    if kind.startswith('legacy_') or kind in {'strict_both_invalid', 'strict_legacy_empty', 'legacy_summary_missing'}:
        summary = {'status': 'completed', 'finding_count': count}
        if count:
            row.pop('SanitizationSchema', None)
            raw = (json.dumps(row, sort_keys=True) + '\n').encode()
    summary['sanitized_artifact_sha256'] = hashlib.sha256(raw).hexdigest()
    if kind.startswith('legacy_') or kind in {'strict_both_invalid', 'strict_legacy_empty'}:
        summary.pop('sanitized_artifact_sha256')
    if kind == 'summary': summary[key] = value
    if kind == 'missing_summary': summary.pop(key, None)
    artifact = root / 'trufflehog.json'
    summary_path = root / 'trufflehog-summary.json'
    artifact.write_bytes(raw)
    summary_path.write_text(json.dumps(summary, sort_keys=True))
    if kind.endswith('both_missing'):
        artifact.unlink()
        summary_path.unlink()
        count = 0
        reason = 'artifact_missing' if not strict else 'invalid_sanitized_capture'
    elif kind.endswith('both_invalid'):
        artifact.write_bytes(b'{invalid json\n')
        summary_path.write_bytes(b'{invalid summary')
        count = 0
        reason = 'invalid_json_line:1' if not strict else 'invalid_sanitized_capture'
    elif kind.endswith('summary_missing'):
        summary_path.unlink()
        strict = kind == 'strict_summary_missing'
        reason = 'artifact_missing_or_empty' if kind == 'legacy_summary_missing' else 'invalid_sanitized_capture'
    elif kind == 'summary_claim_invalid_row':
        strict = False
        artifact.write_bytes(b'[]\n')
        count, reason = 0, 'invalid_sanitized_capture'
    elif kind == 'strict_legacy_empty': reason = 'invalid_sanitized_capture'
    expected = {'status': 'unavailable' if reason else 'completed', 'finding_count': count,
                'artifact': 'trufflehog.json',
                'artifact_hash': hashlib.sha256(artifact.read_bytes()).hexdigest() if artifact.exists() else None}
    if reason:
        expected.update(reason=reason, capture_complete=False)
    else:
        expected.update(blocking=int(bool(count) and kind != 'fixture'), needs_review=0,
                        approved_test_placeholders=int(kind == 'fixture'), approved_nonsecret_identifiers=0,
                        triage=[{'file': row['SourceMetadata']['Data']['Git'].get('file', ''),
                                 'detector': 'SyntheticDetector', 'verified': kind == 'verified',
                                 'disposition': disposition}] if count else [],
                        summary_artifact_hash=hashlib.sha256(summary_path.read_bytes()).hexdigest())
    return strict, expected


@pytest.mark.parametrize('case', CASES, ids=[f'{i}-{case[0]}-{case[1]}' for i, case in enumerate(CASES)])
def test_complete_capture_record_contract(tmp_path, case):
    strict, expected = prepare_case(tmp_path, case)
    assert _trufflehog(tmp_path, require_sanitized=strict) == expected
