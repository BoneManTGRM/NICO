from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('offline_shadow_evaluation', SCRIPTS / 'offline_shadow_evaluation.py')
shadow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shadow)
sys.modules['offline_shadow_evaluation'] = shadow
spec = importlib.util.spec_from_file_location('retained_shadow_adapter', SCRIPTS / 'retained_shadow_adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
F = Path(__file__).parent / 'fixtures' / 'shadow_adapter'


def inputs():
    raw = (F / 'expected.json').read_bytes()
    return json.loads(raw), json.loads((F / 'selection.json').read_bytes()), {
        c: (F / (c + '.json')).read_bytes() for c in ('mixed', 'zero')}, shadow.digest(raw)


def test_manual_observations_denominators_and_nonmutation():
    e, s, records, h = inputs()
    before = deepcopy((e, s, records))
    observed, comparison, details = adapter.project(e, s, records, h)
    assert (e, s, records) == before
    assert observed == json.loads((F / 'manual-observed.json').read_bytes())
    assert comparison == shadow.compare(e, observed, h)
    assert comparison['metrics']['candidate_coverage']['numerator'] == 2
    assert comparison['metrics']['candidate_coverage']['denominator'] == 5
    assert comparison['metrics']['material_omission']['numerator'] == 4
    assert comparison['metrics']['material_omission']['denominator'] == 5
    assert comparison['counts']['missing_observation'] == 3
    assert comparison['counts']['missing_cases'] == 1
    assert comparison['counts']['unresolved_expected_candidates'] == 1
    assert comparison['counts']['observed_true_zero_cases'] == 0
    assert details[0]['missing_verdict_candidate_ids'] == ['missing-verdict']
    assert details[0]['absent_expected_candidate_ids'] == ['absent']


@pytest.mark.parametrize('change', [
    lambda r: r.update(artifact_schema='unknown'),
    lambda r: r.update(exact_commit_sha='2'*40),
    lambda r: r.pop('assessment_subject'),
    lambda r: r['assessment_subject'].update(repository='foreign/repo'),
    lambda r: r['technical_triage'].update(artifact_schema='v1'),
    lambda r: r.pop('findings'),
    lambda r: r.update(findings={}),
    lambda r: r['findings'].append(None),
    lambda r: r['findings'].append(deepcopy(r['findings'][0])),
    lambda r: r['findings'][0].update(candidate_id='foreign'),
    lambda r: r['findings'][0].pop('candidate_id'),
    lambda r: r['findings'][0].update(technical_triage_verdict='CONFIRMED'),
    lambda r: r['findings'][0].update(technical_triage_verdict=[]),
    lambda r: r['findings'][0].update(technical_triage_verdict=''),
    lambda r: r['findings'][0].update(exact_commit_sha='2'*40),
])
def test_invalid_retained_contract(change):
    e, s, records, h = inputs()
    register = json.loads(records['mixed'])
    change(register)
    records['mixed'] = adapter.encode(register)
    s['cases'][0]['register_sha256'] = shadow.digest(records['mixed'])
    with pytest.raises(shadow.Invalid):
        adapter.project(e, s, records, h)


@pytest.mark.parametrize('change', [
    lambda s: s.update(schema='unknown'),
    lambda s: s.update(expected_sha256='0'*64),
    lambda s: s.update(aggregate=100),
    lambda s: s['cases'].append(deepcopy(s['cases'][0])),
    lambda s: s['cases'][0].update(case_id='foreign'),
    lambda s: s['cases'][0]['scope'].update(source_id='foreign'),
    lambda s: s['cases'][0]['scope'].update(repository='foreign'),
    lambda s: s['cases'][0]['scope'].update(revision='2'*40),
    lambda s: s['cases'][0].update(register_sha256='0'*64),
    lambda s: s['cases'].pop(),
])
def test_invalid_selection(change):
    e, s, records, h = inputs()
    change(s)
    with pytest.raises(shadow.Invalid):
        adapter.project(e, s, records, h)


def test_no_trusted_aggregate_or_fallback_to_disposition():
    e, s, records, h = inputs()
    r = json.loads(records['mixed'])
    r.update(totals={'raw':0}, candidate_record_count=0)
    r['findings'][1].update(technical_triage_verdict=None, disposition='approved', human_approved=True)
    records['mixed'] = adapter.encode(r)
    s['cases'][0]['register_sha256'] = shadow.digest(records['mixed'])
    o, result, details = adapter.project(e, s, records, h)
    assert len(o['cases'][0]['findings']) == 2
    assert result['counts']['missing_observation'] == 3
    assert details[0]['retained_records'] == 3


def test_missing_all_cases_is_measured_as_missing_not_empty_pass():
    e, s, records, h = inputs()
    s['cases'] = []
    o, r, d = adapter.project(e, s, {}, h)
    assert r['counts']['missing_cases'] == 3
    assert r['metrics']['candidate_coverage']['numerator'] == 0
    assert r['metrics']['candidate_coverage']['denominator'] == 5
    assert 'incomplete_observations' in r['block_or_unknown_reasons']


def execute(tmp_path, expected=F/'expected.json', selection=F/'selection.json', records=None, out='out'):
    return adapter.run(expected, selection, records if records is not None else [
        ('mixed', F/'mixed.json'), ('zero', F/'zero.json')], tmp_path/out)


def test_byte_retention_repeatability_no_overwrite(tmp_path):
    before = {p.name:p.read_bytes() for p in F.iterdir()}
    result = execute(tmp_path)
    assert result['status'] == 'projected'
    assert result['records_handled'] == 3
    assert result['verdicts_transcribed'] == 2
    execute(tmp_path, out='again')
    assert {p.name:p.read_bytes() for p in (tmp_path/'out').iterdir()} == {
        p.name:p.read_bytes() for p in (tmp_path/'again').iterdir()}
    assert (tmp_path/'out/record-00.input.json').read_bytes() == before['mixed.json']
    checksums = json.loads((tmp_path/'out/checksums.json').read_bytes())
    assert all(shadow.digest((tmp_path/'out'/name).read_bytes()) == h for name,h in checksums.items())
    with pytest.raises(FileExistsError): execute(tmp_path)
    assert before == {p.name:p.read_bytes() for p in F.iterdir()}


@pytest.mark.parametrize('raw', [b'{', b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b'['*2000])
def test_malformed_bytes_retained_no_observation_output(tmp_path, raw):
    p=tmp_path/'bad.json'; p.write_bytes(raw)
    selection=json.loads((F/'selection.json').read_bytes())
    selection['cases'][0]['register_sha256']=shadow.digest(raw)
    sp=tmp_path/'selection.json';sp.write_bytes(adapter.encode(selection))
    r=execute(tmp_path, selection=sp, records=[('mixed', p), ('zero', F/'zero.json')])
    assert r['status']=='invalid' and len(r['expected_cases'])==3
    assert (tmp_path/'out/record-00.input.json').read_bytes()==raw
    assert not (tmp_path/'out/observed.json').exists()


def test_missing_file_and_oversized_file(tmp_path):
    r=execute(tmp_path, records=[('mixed', tmp_path/'absent')])
    assert r['status']=='invalid' and r['records_handled'] is None
    assert r['errors']==['record-00:input_unreadable']
    p=tmp_path/'large';p.write_bytes(b' '* (shadow.MAX_BYTES+1))
    r=execute(tmp_path, records=[('mixed',p)],out='large-out')
    assert r['errors']==['record-00:input_size_limit']


def test_symlinks_parents_fifo_and_existing_output(tmp_path):
    import os
    (tmp_path/'link').symlink_to(F, target_is_directory=True)
    r=execute(tmp_path,records=[('mixed',tmp_path/'link/mixed.json')])
    assert r['status']=='invalid'
    (tmp_path/'file-link').symlink_to(F/'mixed.json')
    assert execute(tmp_path,records=[('mixed',tmp_path/'file-link')],out='file-out')['status']=='invalid'
    os.mkfifo(tmp_path/'fifo')
    assert execute(tmp_path,records=[('mixed',tmp_path/'fifo')],out='fifo-out')['status']=='invalid'
    (tmp_path/'out-link').symlink_to(tmp_path/'out',target_is_directory=True)
    with pytest.raises(FileExistsError): execute(tmp_path,out='out-link')
    with pytest.raises(OSError): execute(tmp_path,out='out-link/new')
    assert not (tmp_path/'out/new').exists()


def test_duplicate_cli_selection_and_bound(tmp_path):
    with pytest.raises(shadow.Invalid): execute(tmp_path,records=[('mixed',F/'mixed.json')]*2)
    with pytest.raises(shadow.Invalid): execute(tmp_path,records=[(str(i),F/'mixed.json') for i in range(33)])


def test_standalone_cli_without_application_startup(tmp_path):
    code = subprocess.run([sys.executable, '-S', str(SCRIPTS/'retained_shadow_adapter.py'),
        '--expected',str(F/'expected.json'),'--selection',str(F/'selection.json'),
        '--record','mixed',str(F/'mixed.json'),'--record','zero',str(F/'zero.json'),
        '--output',str(tmp_path/'cli')],capture_output=True,text=True)
    assert code.returncode==0, code.stderr
    assert 'shadow only' in code.stdout
    assert json.loads((tmp_path/'cli/observed.json').read_bytes())==json.loads((F/'manual-observed.json').read_bytes())


def test_duplicate_source_and_empty_expected_rejected():
    e,s,records,h=inputs()
    e['cases'][1]['scope']=deepcopy(e['cases'][0]['scope'])
    s['cases'][1]['scope']=deepcopy(s['cases'][0]['scope'])
    with pytest.raises(shadow.Invalid, match='duplicate_source_identity'):
        adapter.project(e,s,records,h)
    e['cases']=[]
    with pytest.raises(shadow.Invalid, match='empty_corpus'):
        adapter.project(e,s,records,h)


def test_true_zero_only_has_null_candidate_denominator():
    e,s,records,h=inputs()
    e['cases']=[e['cases'][1]];s['cases']=[s['cases'][1]]
    o,r,d=adapter.project(e,s,{'zero':records['zero']},h)
    assert r['metrics']['candidate_coverage']['value'] is None
    assert r['metrics']['candidate_coverage']['unknown_reason']=='zero_denominator'
    assert r['metrics']['true_zero_coverage']['numerator']==0


def test_private_file_modes_and_parent_traversal(tmp_path):
    import stat
    execute(tmp_path)
    assert stat.S_IMODE((tmp_path/'out').stat().st_mode)==0o700
    assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in (tmp_path/'out').iterdir())
    with pytest.raises(shadow.Invalid, match='unsafe_path'):
        adapter.read(tmp_path/'..'/'any.json')
