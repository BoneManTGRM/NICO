"""Offline request preparation; synthetic cases never establish live coverage."""
import base64
import gzip
import json
import os
import stat
import subprocess
import sys

import pytest

from nico.candidate_technical_triage_v1 import load_default_technical_triage


def test_retained_population_and_shared_requests():
    from scripts.prepare_retained_triage_evidence_requests import prepare
    original = load_default_technical_triage()
    result = prepare()
    assert result['candidate_count'] == 662
    assert result['verdict_counts'] == {'not_actionable': 624, 'needs_review': 38}
    assert sorted(result['unresolved_reason_counts'].values()) == [2, 36]
    assert len(result['evidence_requests']) == 3
    assert all(len(request['candidate_ids']) == 38 for request in result['evidence_requests'])
    assert sorted(len(group['candidate_ids']) for group in result['next_step_groups']) == [2, 36]
    assert len({row['candidate_id'] for row in result['candidate_references']}) == 662
    assert result['coverage']['candidates_with_recorded_proof_gaps'] == 38
    assert result['coverage']['candidates_without_recorded_proof_gaps'] == 624
    assert result['runtime_validation_performed'] is False
    assert result['human_approval_status'] == 'pending'
    assert result['client_delivery_allowed'] is False
    assert result['reviewer_time_saved_seconds'] is None
    assert result == prepare()
    assert original == load_default_technical_triage()


def synthetic(tmp_path, gaps):
    payload = {'s': 'nico.candidate-technical-triage.v1', 'r': 'synthetic/repo',
               'c': 'a' * 40, 'n': 1, 'h': 'pending', 'd': False,
               'runtime_validation_performed': False,
               'v': {'needs_review': 1}, 'p': {'review_required': 1},
               'q': {'synthetic_missing_evidence': ['needs_review', 'low', 'review_required',
                     'synthetic', 'Unknown', 'Unknown', 'Obtain exact-scope evidence', gaps, '']},
               'x': [['SYNTHETIC-1', 'synthetic_missing_evidence', 1]]}
    path = tmp_path / 'synthetic.b64'
    path.write_bytes(base64.b64encode(gzip.compress(json.dumps(payload).encode())))
    return path


def test_duplicate_gap_counts_candidates_once_and_preserves_input(tmp_path):
    from scripts.prepare_retained_triage_evidence_requests import prepare
    path = synthetic(tmp_path, ['Missing lock', 'Missing lock'])
    before = path.read_bytes()
    result = prepare(path)
    assert len(result['evidence_requests']) == 1
    assert result['evidence_requests'][0]['candidate_ids'] == ['SYNTHETIC-1']
    assert path.read_bytes() == before


def test_empty_gaps_remain_unknown_not_complete(tmp_path):
    from scripts.prepare_retained_triage_evidence_requests import prepare
    result = prepare(synthetic(tmp_path, []))
    assert result['evidence_requests'] == []
    assert result['unresolved_without_recorded_gaps'] == ['SYNTHETIC-1']
    assert result['verdict_counts'] == {'needs_review': 1}


@pytest.mark.parametrize('gaps', [None, 'not a list', [None], ['']])
def test_malformed_gap_evidence_is_rejected(tmp_path, gaps):
    from scripts.prepare_retained_triage_evidence_requests import prepare
    with pytest.raises(ValueError, match='proof_gaps_invalid'):
        prepare(synthetic(tmp_path, gaps))


def test_cli_exclusive_output_and_invalid_input(tmp_path, monkeypatch):
    from scripts.prepare_retained_triage_evidence_requests import main
    path = synthetic(tmp_path, ['Missing lock'])
    output = tmp_path / 'requests.json'
    monkeypatch.setattr('sys.argv', ['prepare', '--triage', str(path), '--output', str(output)])
    main()
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        main()
    assert output.read_bytes() == before
    path.write_text('invalid')
    output.unlink()
    with pytest.raises((ValueError, gzip.BadGzipFile)):
        main()
    assert not output.exists()


def test_cli_keeps_external_evidence_private(tmp_path, monkeypatch, capsys):
    from scripts.prepare_retained_triage_evidence_requests import main
    path = synthetic(tmp_path, ['PRIVATE_EVIDENCE_SENTINEL'])
    output = tmp_path / 'private.json'
    monkeypatch.setattr('sys.argv', ['prepare', '--triage', str(path), '--output', str(output)])
    previous = os.umask(0o022)
    try:
        main()
    finally:
        os.umask(previous)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert 'PRIVATE_EVIDENCE_SENTINEL' in output.read_text()
    stdout = capsys.readouterr().out
    assert 'PRIVATE_EVIDENCE_SENTINEL' not in stdout
    assert 'synthetic_missing_evidence' not in stdout
    assert json.loads(stdout) == {'candidate_count': 1, 'unresolved_candidate_count': 1,
                                'evidence_request_count': 1, 'next_step_group_count': 1}


def test_padded_identifier_rejected_without_echoing_retained_text(tmp_path):
    path = synthetic(tmp_path, [])
    payload = json.loads(gzip.decompress(base64.b64decode(path.read_bytes())))
    entry = payload['q'].pop('synthetic_missing_evidence')
    payload['q']['PRIVATE_REASON_SENTINEL'] = entry
    payload['x'][0][1] = ' PRIVATE_REASON_SENTINEL '
    path.write_bytes(base64.b64encode(gzip.compress(json.dumps(payload).encode())))
    output = tmp_path / 'rejected.json'
    result = subprocess.run([sys.executable, '-m', 'scripts.prepare_retained_triage_evidence_requests',
                             '--triage', str(path), '--output', str(output)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert 'PRIVATE_REASON_SENTINEL' not in result.stdout + result.stderr
    assert not output.exists()
