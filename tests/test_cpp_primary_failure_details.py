"""Owned primary-diagnostic controls; fixtures are not native qualification."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from nico.assessment_cpp_project_compiler import _canonical
from scripts import cpp_qualification_diagnostic_details as details
from scripts import qualify_cpp_project_configuration as cli
from tests.test_cpp_project_static import api, native, request


def bound_artifact(proof, value):
    raw = _canonical(value)
    sha = hashlib.sha256(raw).hexdigest()
    proof = {**proof, 'native_evidence_sha256': sha, 'artifact': {
        'path': 'artifacts/project-static-evidence-' + sha + '.json',
        'sha256': sha, 'bytes': len(raw)}}
    return proof, raw


def fixture(tmp_path, rule=None):
    req = request(tmp_path)
    value = native(req, rule)
    value['records'][0]['execution'].update(timed_out=True, exit_code=-9, duration_ms=90000)
    value['records'][2].update(execution=None, xml='', xml_sha256=None,
                                error='worker_project_static_deadline')
    value['duration_ms'] = 90001
    proof = api().validate_project_static(_canonical(value), req)
    return bound_artifact(proof, value)


@pytest.mark.parametrize('rule,outcome', [(None, 'analyzed'), ('internalAstError', 'internal_ast_error'),
                                         ('syntaxError', 'syntax_error'), ('missingInclude', 'incomplete')])
def test_primary_identity_timing_and_incompleteness_are_bound(tmp_path, rule, outcome):
    proof, raw = fixture(tmp_path, rule)
    before = deepcopy(proof)
    result = details.primary_static_details(proof, lambda *a: raw)
    assert proof == before and proof['complete'] is False
    assert result['artifact_sha256'] == hashlib.sha256(raw).hexdigest()
    assert (result['executions'], result['missing_execution'], result['omitted']) == (2, 1, 0)
    assert [row['context_index'] for row in result['records']] == [0, 1]
    assert [row['outcome'] for row in result['records']] == ['timed_out', outcome]
    assert [row['duration_ms'] for row in result['records']] == [90000, 1]
    native_rows = json.loads(raw)['records']
    for row in result['records']:
        source = native_rows[row['context_index']]
        assert row['record_sha256'] == hashlib.sha256(_canonical(source)).hexdigest()
        assert row['invocation_sha256'] == hashlib.sha256(_canonical(source['invocation'])).hexdigest()
        assert row['context_id_sha256'] == hashlib.sha256(source['context_id'].encode()).hexdigest()
    assert '/work/' not in json.dumps(result)


@pytest.mark.parametrize('outcome', ['nonzero_exit', 'output_truncated', 'record_error', 'not_executed'])
def test_other_primary_failures_never_gain_analyzed_credit(tmp_path, outcome):
    req = request(tmp_path)
    value = native(req)
    for row in value['records']:
        if outcome == 'nonzero_exit': row['execution']['exit_code'] = 1
        if outcome == 'output_truncated': row['execution']['output_truncated'] = True
        if outcome == 'record_error': row['error'] = 'worker_project_static_failed'
        if outcome == 'not_executed':
            row.update(execution=None, xml='', xml_sha256=None, error='worker_project_static_deadline')
    proof = api().validate_project_static(_canonical(value), req)
    assert proof['analyzed_contexts'] == [] and proof['complete'] is False
    proof, raw = bound_artifact(proof, value)
    result = details.primary_static_details(proof, lambda *a: raw)
    if outcome == 'not_executed':
        assert result['records'] == [] and result['executions'] == 0 and result['missing_execution'] == 3
    else:
        assert [row['outcome'] for row in result['records']] == [outcome] * 3


@pytest.mark.parametrize('fault', ['hash', 'size', 'path', 'population', 'oversize', 'corrupt_json',
                                  'duplicate_json', 'merged', 'duration_bool', 'duration_negative',
                                  'duration_oversize'])
def test_bad_primary_detail_is_unavailable_and_preserves_failure(tmp_path, fault):
    proof, raw = fixture(tmp_path)
    if fault == 'hash': proof['native_evidence_sha256'] = '0' * 64
    if fault == 'size': proof['artifact']['bytes'] += 1
    if fault == 'path': proof['artifact']['path'] = '../SECRET'
    if fault == 'population': proof['required_contexts'].reverse()
    if fault == 'oversize': proof['artifact']['bytes'] = details.MAX_ARTIFACT_BYTES + 1
    if fault == 'merged': proof['clang_fallback'] = {}; proof['analyzed_contexts'] = proof['required_contexts']
    if fault in ('corrupt_json', 'duplicate_json'):
        raw = b'{"records":[],"records":[]}' if fault == 'duplicate_json' else b'SECRET'
        sha = hashlib.sha256(raw).hexdigest()
        proof.update(native_evidence_sha256=sha, artifact={
            'path': 'artifacts/project-static-evidence-' + sha + '.json', 'sha256': sha, 'bytes': len(raw)})
    if fault.startswith('duration_'):
        value = json.loads(raw)
        value['records'][0]['execution']['duration_ms'] = {
            'duration_bool': True, 'duration_negative': -1, 'duration_oversize': 93001}[fault]
        proof, raw = bound_artifact(proof, value)
    result = details.add_failure_details({'qualification_error': 'qualification_collection_invalid'},
                                         {'primary_static': proof}, lambda *a: raw)
    assert result['details']['primary_static'] == {'state': 'unavailable'}
    assert result['qualification_error'] == 'qualification_collection_invalid'
    assert 'SECRET' not in json.dumps(result)


def test_primary_projection_cap_and_secret_canaries(tmp_path):
    # Projection-only hostile controls, not a claim of validated native evidence.
    proof, raw = fixture(tmp_path)
    value = json.loads(raw)
    row = value['records'][0]
    secret = 'SECRET\n::error::/private/token'
    row.update(invocation=[secret], context_id='abcdef0123456789' * 4, error=secret)
    row['execution']['output'] = secret
    value['records'] = [deepcopy(row) for _ in range(20)]
    proof['required_contexts'] = [r['context_id'] for r in value['records']]
    proof, raw = bound_artifact(proof, value)
    result = details.primary_static_details(proof, lambda *a: raw)
    assert result['executions'] == 20 and result['omitted'] == 4
    assert [r['context_index'] for r in result['records']] == list(range(16))
    encoded = json.dumps(result)
    assert all(canary not in encoded for canary in (secret, row['context_id'], 'SECRET', '/private', '::error::'))
    assert len(encoded.encode()) < 10000
    # Omitted executions still receive numeric-bound checks.
    value['records'][-1]['execution']['duration_ms'] = 93001
    proof, raw = bound_artifact(proof, value)
    result = details.add_failure_details({}, {'primary_static': proof}, lambda *a: raw)
    assert result['details']['primary_static'] == {'state': 'unavailable'}


def test_cli_preserves_primary_before_fallback_and_original_failure(tmp_path, monkeypatch, capsys):
    from nico import assessment_cpp_configuration_probe as probe_module
    from nico.assessment_cpp_clang_fallback import merge_static_analysis
    proof, raw = fixture(tmp_path)
    remaining = proof['attempted_contexts'][:1]
    merged = merge_static_analysis(proof, {'required_contexts': remaining,
        'attempted_contexts': remaining, 'analyzed_contexts': remaining, 'complete': True,
        'findings': [], 'limitations': [], 'native_evidence_sha256': '0' * 64, 'tool_version': 'owned'})
    assert len(merged['analyzed_contexts']) == 2 and len(proof['analyzed_contexts']) == 1
    output = tmp_path / 'output'
    artifact = output / proof['artifact']['path']
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(raw)
    manifest = tmp_path / 'manifest.json'
    manifest.write_text('{"project_options":[]}')
    args = SimpleNamespace(output=output, qualification_manifest=manifest,
                           qualification_source='owned-unused', image='owned-unused')
    monkeypatch.setattr(cli, 'freeze_configuration_checkout', lambda *a: {'targets': {}})
    original = ValueError('qualification_collection_invalid')
    def replay(*args, **options):
        for analysis in (None, proof, merged):
            options['retain']({'project_static': analysis, 'compiled': False, 'tests_executed': False})
        raise original
    monkeypatch.setattr(probe_module, 'probe_project_configuration', replay)
    with pytest.raises(ValueError) as caught:
        cli.qualify_configuration_checkout(args)
    assert caught.value is original
    result = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert result['primary_diagnostics']['analyzed'] == 1
    assert result['retained_counts']['static']['analyzed'] == 2
    assert [r['outcome'] for r in result['details']['primary_static']['records']] == ['timed_out', 'analyzed']
    assert not (output / 'collection-acceptance.json').exists()
