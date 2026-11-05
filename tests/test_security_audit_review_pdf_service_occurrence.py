"""Exact owner-approved nonsecret provenance; retain all scanner observations."""
import hashlib
import json

import pytest

from scripts.security_audit_gate import _trufflehog, _approved_review_pdf_service_occurrence


APPROVED_COMMITS = (
    'd1c08f7c502aefe922b65948d5e7d998a56342bb',
    'a0163677a6c1a993a9eb26707472653f656e3d53',
)


def finding(commit=APPROVED_COMMITS[0]):
    return {
        'SourceMetadata': {'Data': {'Git': {
            'commit': commit,
            'file': 'docs/evidence/review-pdf-preparation-slice1-20261014/README.md',
            'line': 15,
        }}},
        'DetectorName': 'RailwayApp', 'DetectorType': 999, 'Verified': False,
        'SanitizationSchema': 'nico.security-audit.trufflehog.finding.v1',
        'RawSHA256': '55a16aefae99e52dade482f9cecc291d6b5b5a97a92910132fcaa43f9ec8e6c5',
    }


def evaluate(root, rows, status='completed'):
    raw = ''.join(json.dumps(row)+'\n' for row in rows).encode()
    path = root/'trufflehog.json'
    path.write_bytes(raw)
    (root/'trufflehog-summary.json').write_text(json.dumps({
        'schema': 'nico.security-audit.trufflehog.capture.v1', 'scanner': 'trufflehog',
        'status': status, 'finding_count': len(rows), 'artifact_present': True,
        'history_depth': 'full', 'exit_code': 183, 'invalid_json_lines': 0,
        'live_credential_verification': False, 'raw_capture_sha256': 'a'*64,
        'sanitized_artifact_sha256': hashlib.sha256(raw).hexdigest(),
        'raw_candidate_bodies_retained': False,
    }))
    result = _trufflehog(root)
    assert path.read_bytes() == raw
    assert result['artifact_hash'] == hashlib.sha256(raw).hexdigest()
    assert result == _trufflehog(root)
    return result


@pytest.mark.parametrize('commit', APPROVED_COMMITS)
def test_exact_occurrence_retained(tmp_path, commit):
    result = evaluate(tmp_path, [finding(commit)])
    assert result['finding_count'] == 1 and result['blocking'] == 0
    assert result['approved_nonsecret_identifiers'] == 1
    assert result['triage'][0]['disposition'] == 'approved_nonsecret_service_identifier'


@pytest.mark.parametrize('commit', APPROVED_COMMITS)
@pytest.mark.parametrize('field,value', [
    ('commit', 'd'*40), ('commit', None), ('commit', 1), ('commit', []), ('commit', {}),
    ('file', 'docs/README.md'), ('file', None),
    ('line', 14), ('line', 16), ('line', '15'), ('line', 15.0), ('line', True), ('line', None),
    ('DetectorType', 998), ('DetectorType', '999'), ('DetectorType', 999.0), ('DetectorType', True),
    ('DetectorName', 'Other'), ('DetectorName', None),
    ('Verified', True), ('Verified', None), ('Verified', 0), ('Verified', 'false'),
    ('RawSHA256', '0'*64), ('RawSHA256', finding()['RawSHA256'].upper()), ('RawSHA256', None),
    ('SanitizationSchema', None), ('Raw', 'unapproved synthetic input'),
    ('SourceMetadata', None), ('SourceMetadata', []),
    ('SourceMetadata', {'Data': []}), ('SourceMetadata', {'Data': {'Git': []}}),
])
def test_any_changed_provenance_blocks(tmp_path, commit, field, value):
    row = finding(commit)
    target = row['SourceMetadata']['Data']['Git'] if field in {'commit', 'file', 'line'} else row
    target[field] = value
    result = evaluate(tmp_path, [row])
    assert _approved_review_pdf_service_occurrence(row) is False
    assert result['status'] == 'unavailable' or (
        result['blocking'] == 1 and result['approved_nonsecret_identifiers'] == 0)


@pytest.mark.parametrize('commit', APPROVED_COMMITS)
@pytest.mark.parametrize('field', ['commit', 'file', 'line', 'DetectorName', 'DetectorType', 'Verified', 'RawSHA256', 'SanitizationSchema', 'SourceMetadata'])
def test_missing_provenance_blocks(tmp_path, commit, field):
    row = finding(commit)
    target = row['SourceMetadata']['Data']['Git'] if field in {'commit', 'file', 'line'} else row
    del target[field]
    assert _approved_review_pdf_service_occurrence(row) is False
    result = evaluate(tmp_path, [row])
    assert result['status'] == 'unavailable' or result['blocking'] == 1


def test_approved_hit_does_not_hide_unmatched_or_verified_hits(tmp_path):
    approved, unknown, verified = finding(), finding(), finding()
    unknown['SourceMetadata']['Data']['Git']['line'] = 16
    verified['Verified'] = True
    result = evaluate(tmp_path, [approved, finding(APPROVED_COMMITS[1]), unknown, verified])
    assert result['finding_count'] == 4 and result['blocking'] == 2
    assert result['approved_nonsecret_identifiers'] == 2
    assert [item['disposition'] for item in result['triage']] == [
        'approved_nonsecret_service_identifier', 'approved_nonsecret_service_identifier',
        'blocking_unverified_non_fixture', 'blocking_verified_secret']


@pytest.mark.parametrize('status', ['failed', 'unavailable'])
@pytest.mark.parametrize('commit', APPROVED_COMMITS)
def test_disposition_does_not_override_scanner_failure(tmp_path, status, commit):
    assert evaluate(tmp_path, [finding(commit)], status)['status'] == 'unavailable'


@pytest.mark.parametrize('corruption', ['missing_summary', 'malformed_summary', 'malformed_jsonl', 'wrong_digest', 'wrong_count', 'invalid_lines', 'scanner_exit'])
def test_both_approved_occurrences_require_valid_capture(tmp_path, corruption):
    evaluate(tmp_path, [finding(commit) for commit in APPROVED_COMMITS])
    path = tmp_path/'trufflehog-summary.json'
    summary = json.loads(path.read_text())
    if corruption == 'missing_summary': path.unlink()
    elif corruption == 'malformed_summary': path.write_text('{')
    elif corruption == 'malformed_jsonl': (tmp_path/'trufflehog.json').write_text('{\n')
    else:
        field, value = {
            'wrong_digest': ('sanitized_artifact_sha256', '0'*64),
            'wrong_count': ('finding_count', 1),
            'invalid_lines': ('invalid_json_lines', 1),
            'scanner_exit': ('exit_code', 1),
        }[corruption]
        summary[field] = value
        path.write_text(json.dumps(summary))
    assert _trufflehog(tmp_path)['status'] == 'unavailable'
