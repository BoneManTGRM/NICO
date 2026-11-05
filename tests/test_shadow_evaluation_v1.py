from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket

import pytest

import importlib.util
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'offline_shadow_evaluation.py'
spec = importlib.util.spec_from_file_location('offline_shadow_evaluation', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BOUNDARIES, Invalid, MAX_BYTES = module.BOUNDARIES, module.Invalid, module.MAX_BYTES
compare, digest, evaluate_files, parse = module.compare, module.digest, module.evaluate_files, module.parse

FIXTURES = Path(__file__).parent / 'fixtures' / 'shadow'


def inputs():
    raw = (FIXTURES / 'expected.json').read_bytes()
    return json.loads(raw), json.loads((FIXTURES / 'observed.json').read_bytes()), digest(raw)


def test_synthetic_metrics_include_omissions_and_keep_decisions_separate():
    e, o, h = inputs()
    before = deepcopy((e, o))
    r = compare(e, o, h)
    assert (e, o) == before
    m = r['metrics']
    assert m['candidate_coverage']['numerator'] == 6
    assert m['candidate_coverage']['denominator'] == 8
    assert m['candidate_label_agreement']['numerator'] == 3
    assert m['resolved_candidate_correctness']['numerator'] == 2
    assert m['resolved_candidate_correctness']['denominator'] == 7
    assert m['material_detection']['numerator'] == 3
    assert m['material_detection']['denominator'] == 6
    assert m['material_confirmation']['numerator'] == 1
    assert m['material_unresolved']['numerator'] == 5
    assert m['material_omission']['numerator'] == 3
    assert m['unsafe_dismissal']['numerator'] == 1
    assert m['incorrect_confirmation']['numerator'] == 1
    assert m['abstention']['numerator'] == 2
    assert r['counts']['missing_cases'] == 1
    assert r['counts']['unresolved_expected_candidates'] == 1
    assert len(r['cases']) == len(e['cases'])
    assert 'unresolved_expected_answers' in r['block_or_unknown_reasons']


@pytest.mark.parametrize('mutation', [
    lambda e,o: o.update(schema='foreign'),
    lambda e,o: e.update(schema='foreign'),
    lambda e,o: o.update(expected_sha256='0'*64),
    lambda e,o: o.update(corpus_version='old'),
    lambda e,o: o.update(corpus_id='foreign'),
    lambda e,o: o.update(aggregates={'agreement':100}),
    lambda e,o: o['cases'].append(deepcopy(o['cases'][0])),
    lambda e,o: e['cases'].append(deepcopy(e['cases'][0])),
    lambda e,o: o['cases'][0].update(case_id='foreign'),
    lambda e,o: o['cases'][0]['scope'].update(repository='foreign'),
    lambda e,o: o['cases'][0]['scope'].update(revision='2'*40),
    lambda e,o: o['cases'][0]['scope'].update(source_id='foreign'),
    lambda e,o: o['cases'][0]['scope'].update(source_schema='old'),
    lambda e,o: o['cases'][0].update(status='success'),
    lambda e,o: o['cases'][0].update(status='unavailable'),
    lambda e,o: o['cases'][0]['findings'].append(deepcopy(o['cases'][0]['findings'][0])),
    lambda e,o: e['cases'][0]['candidates'].append(deepcopy(e['cases'][0]['candidates'][0])),
    lambda e,o: e['cases'][0]['material_findings'].append(deepcopy(e['cases'][0]['material_findings'][0])),
    lambda e,o: o['cases'][0]['findings'][0].update(technical_triage_verdict='approved'),
    lambda e,o: e['cases'][0]['candidates'][0].update(expected_verdict='approved'),
    lambda e,o: o['cases'][0]['findings'][0].update(candidate_id='foreign'),
    lambda e,o: e['cases'][0]['material_findings'][0].update(candidate_ids=['material','material']),
    lambda e,o: e['cases'][0]['material_findings'][0].update(candidate_ids=['benign']),
    lambda e,o: e['cases'][0]['material_findings'][0].update(candidate_ids=[]),
    lambda e,o: e.update(cases=[]),
    lambda e,o: e.update(label_kind='specialist_approval'),
])
def test_invalid_inputs_cannot_produce_metrics(mutation):
    e,o,h = inputs()
    mutation(e,o)
    with pytest.raises(Invalid):
        compare(e,o,h)


def test_true_zero_is_not_missing_or_empty_corpus():
    e,o,h=inputs()
    e['cases']=[e['cases'][1]]
    o['cases']=[o['cases'][1]]
    r=compare(e,o,h)
    assert r['metrics']['true_zero_coverage']['value'] == 1
    assert r['metrics']['candidate_label_agreement']['value'] is None
    assert r['metrics']['material_detection']['unknown_reason'] == 'zero_denominator'
    o['cases']=[]
    r=compare(e,o,h)
    assert r['metrics']['true_zero_coverage']['value'] == 0
    assert r['counts']['missing_cases'] == 1


@pytest.mark.parametrize('status', ['partial','unavailable'])
def test_empty_partial_is_not_zero_success(status):
    e,o,h=inputs()
    o['cases'][1]['status']=status
    assert compare(e,o,h)['metrics']['true_zero_coverage']['numerator'] == 0


def test_unresolved_truth_does_not_credit_confirmation_or_dismissal():
    for label, outcome in [('confirmed','unsupported_confirmation'),('not_actionable','unsafe_dismissal')]:
        e,o,h=inputs()
        o['cases'][0]['findings'][-1]['technical_triage_verdict']=label
        r=compare(e,o,h)
        assert r['metrics'][outcome]['numerator'] >= 1
        assert r['metrics']['resolved_candidate_correctness']['numerator'] == 2


def test_retention_determinism_checksums_and_no_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('network forbidden')
    monkeypatch.setattr(socket, 'socket', forbidden)
    sources=[FIXTURES/'expected.json',FIXTURES/'observed.json']
    before=[p.read_bytes() for p in sources]
    for name in ['one','two']:
        r=evaluate_files(*sources,tmp_path/name)
        assert all(r[k] == v for k,v in BOUNDARIES.items())
        for file,h in json.loads((tmp_path/name/'checksums.json').read_text()).items():
            assert hashlib.sha256((tmp_path/name/file).read_bytes()).hexdigest() == h
        assert (tmp_path/name/'expected.input.json').read_bytes() == before[0]
    assert [p.read_bytes() for p in sources] == before
    assert (tmp_path/'one'/'result.json').read_bytes() == (tmp_path/'two'/'result.json').read_bytes()
    with pytest.raises(FileExistsError):
        evaluate_files(*sources,tmp_path/'one')


@pytest.mark.parametrize('bad', [b'{', b'{"cases":[],"cases":[]}', b'{"x":NaN}', b'[]', b'null', b'"foo"', b'\xff', b'['*2000])
def test_malformed_observations_retained_with_all_expected_cases(tmp_path,bad):
    source=tmp_path/'bad.json'; source.write_bytes(bad)
    r=evaluate_files(FIXTURES/'expected.json',source,tmp_path/'result')
    assert r['measurement_status']=='invalid'
    assert r['metrics'] is None
    assert len(r['cases']) == 3
    assert (tmp_path/'result'/'observed.input.json').read_bytes() == bad


def test_missing_input_preserves_expected_cases(tmp_path):
    r=evaluate_files(FIXTURES/'expected.json',tmp_path/'missing',tmp_path/'result')
    assert r['measurement_status']=='invalid'
    assert len(r['cases']) == 3
    assert r['block_or_unknown_reasons'] == ['observed:input_unreadable']


def test_bounded_nonregular_and_symlink_inputs(tmp_path):
    large=tmp_path/'large'; large.write_bytes(b' '* (MAX_BYTES+1))
    link=tmp_path/'link'; link.symlink_to(FIXTURES/'expected.json')
    for i,path in enumerate([large,link,tmp_path]):
        r=evaluate_files(path,FIXTURES/'observed.json',tmp_path/str(i))
        assert r['measurement_status']=='invalid'
        assert 'expected' not in r['inputs']


def test_json_duplicate_keys_and_nonfinite_rejected():
    for data in [b'{"a":1,"a":2}', b'{"a":Infinity}']:
        with pytest.raises(Invalid):
            parse(data)


def test_cli_isolated_from_runtime_and_site_packages(tmp_path):
    guard = """
import runpy, sys, socket
socket.socket = lambda *a, **k: (_ for _ in ()).throw(AssertionError('network'))
script, *args = sys.argv[1:]
sys.argv = [script, *args]
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as exc:
    assert exc.code == 0
assert not any(k == 'nico' or k.startswith('nico.') for k in sys.modules)
"""
    command = [sys.executable, '-S', '-c', guard, str(SCRIPT),
               '--expected', str(FIXTURES/'expected.json'),
               '--observed', str(FIXTURES/'observed.json'),
               '--output', str(tmp_path/'isolated')]
    run = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stderr
    assert 'human review required; client delivery blocked' in run.stdout
    invalid = subprocess.run([sys.executable, '-S', str(SCRIPT),
        '--expected', str(FIXTURES/'expected.json'), '--observed', str(tmp_path/'missing'),
        '--output', str(tmp_path/'invalid')], capture_output=True, text=True, timeout=10)
    assert invalid.returncode == 2
    assert json.loads((tmp_path/'invalid'/'result.json').read_text())['metrics'] is None
