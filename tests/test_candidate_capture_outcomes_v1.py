"""Observed per-path boundaries, never guesses from aggregate counters."""
from copy import deepcopy
import hashlib
import pytest
from nico import candidate_workspace_capture_v1 as c
from nico.candidate_investigation_pipeline_v1 import investigate_register, display_investigation
from tests.test_candidate_workspace_capture_v1 import memory
from tests.test_candidate_investigation_pipeline_v1 import SCOPE
from tests.test_candidate_source_observations_v1 import row


def reason(result, path='example.py'):
    return result['path_capture_outcomes']['path_sha256_reasons'].get(hashlib.sha256(path.encode()).hexdigest())


def view(rows, result):
    reg={'findings':rows}
    reg['candidate_investigation']=investigate_register(reg,result,SCOPE,clock=lambda:0)
    return display_investigation(reg,SCOPE)


@pytest.mark.parametrize('kind,expected',[
    ('missing','inventory_missing_or_unsupported'),('file','file_size_limit'),
    ('input','input_size_limit'),('invalid','inventory_entry_invalid'),
    ('integrity','blob_integrity_unavailable'),('output','observation_output_limit'),
    ('read_error','capture_operation_failed'),('deadline','capture_deadline')])
def test_observed_boundary_is_bound_without_disposition_change(monkeypatch,kind,expected):
    rows=[row()]; before=deepcopy(rows)
    inv,read,reads=memory({'example.py':b'assert x\n'})
    now=[0]
    if kind=='missing': inv=lambda *a:{}
    if kind=='file': inv=lambda *a:{'example.py':('a'*40,c.FILE_LIMIT+1)}
    if kind=='input': inv=lambda *a:({'example.py':('a'*40,10)},c.INPUT_LIMIT)
    if kind=='invalid': inv=lambda *a:{'example.py':('a'*40,-1)}
    if kind=='integrity': read=lambda *a:b'bad bytes'
    if kind=='output': monkeypatch.setattr(c,'observe_python_source',lambda *a,**kw:{'status':'parsed','synthetic':'x'*c.OUTPUT_LIMIT})
    if kind=='read_error':
        def read(*args): raise OSError('PRIVATE_SENTINEL')
    if kind=='deadline':
        original=read
        def read(*args):
            data=original(*args);now[0]=5;return data
    result=c.capture_candidates(rows,SCOPE,inv,read,clock=lambda:now[0])
    assert reason(result)==expected
    assert len(c.encoded(result))<=c.OUTPUT_LIMIT
    projected=view(rows,result)
    assert projected['source_availability_counts']=={expected:1}
    assert projected['completed_count']==0 and projected['unresolved_reasons']=={'source_parse_unavailable':1}
    assert rows==before and 'PRIVATE_SENTINEL' not in str(result)
    assert result['source_bytes_read']<=c.INPUT_LIMIT


def test_outcome_limit_is_inside_existing_envelope_and_missing_entry_is_unknown():
    rows=[row(candidate_id=str(i),source_path=f'{i:04}.py') for i in range(1000)]
    result=c.capture_candidates(rows,SCOPE,lambda *a:{},lambda *a:pytest.fail('no read'),clock=lambda:0)
    outcomes=result['path_capture_outcomes']
    assert outcomes['recording_truncated'] is True
    assert len(c.encoded(outcomes))<=c.OUTCOME_LIMIT<=32768
    assert len(c.encoded(result))<=c.OUTPUT_LIMIT
    assert 0<len(outcomes['path_sha256_reasons'])<len(rows)
    assert reason(result,'0999.py') is None
    projected=view(rows,result)
    counts=projected['source_availability_counts']
    assert counts['source_not_retained']>0
    assert sum(counts.values())==1000 and projected['completed_count']==0
    reverse=c.capture_candidates(list(reversed(rows)),SCOPE,lambda *a:{},lambda *a:b'',clock=lambda:0)
    assert reverse['path_capture_outcomes']==outcomes


def test_no_attribution_to_unvisited_candidates_or_inventory_failure(monkeypatch):
    rows=[row(source_path='a.py'),row(candidate_id='B',source_path='b.py')]
    def failed(*args):raise ValueError('PRIVATE')
    result=c.capture_candidates(rows,SCOPE,failed,lambda *a:b'',clock=lambda:0)
    assert not result['path_capture_outcomes']['path_sha256_reasons']
    assert view(rows,result)['source_availability_counts']=={'source_not_retained':2}
    monkeypatch.setattr(c,'CANDIDATE_LIMIT',1)
    result=c.capture_candidates(rows,SCOPE,lambda *a:{},lambda *a:b'',clock=lambda:0)
    assert reason(result,'a.py')=='inventory_missing_or_unsupported'
    assert reason(result,'b.py') is None


@pytest.mark.parametrize('change',['foreign','malformed','unknown','legacy','wrong_path'])
def test_foreign_or_unsupported_outcomes_cannot_supply_reason(change):
    rows=[row()];result=c.capture_candidates(rows,SCOPE,lambda *a:{},lambda *a:b'',clock=lambda:0)
    if change=='foreign':result['scope']={**SCOPE,'run_id':'foreign'}
    elif change=='legacy':result.pop('path_capture_outcomes')
    elif change=='malformed':result['path_capture_outcomes']['path_sha256_reasons']=[]
    elif change=='unknown':result['path_capture_outcomes']['artifact_schema']='unrecognized'
    else:rows[0]['source_path']='other.py'
    projected=view(rows,result)
    assert 'inventory_missing_or_unsupported' not in projected['source_availability_counts']
    assert projected['completed_count']==0


def test_duplicates_use_one_verified_inventory_read_and_no_extra_capture():
    rows=[row(),row(candidate_id='duplicate',source_path='./example.py')]
    inv,read,reads=memory({'example.py':b'assert x\n'})
    result=c.capture_candidates(rows,SCOPE,inv,read,clock=lambda:0)
    assert len(reads)==1 and result['source_bytes_read']==9
    assert not result['path_capture_outcomes']['path_sha256_reasons']
    assert view(rows,result)['completed_count']==2


def test_observed_reasons_are_bilingual_and_do_not_leak_paths():
    from nico.report_preview_labels_v1 import retained_coverage_disclosures
    from nico.candidate_source_reason_detail_v1 import CAPTURE_LABELS
    rows=[row()];result=c.capture_candidates(rows,SCOPE,lambda *a:{},lambda *a:b'',clock=lambda:0)
    register={'findings':rows};register['candidate_investigation']=investigate_register(register,result,SCOPE)
    for spanish in (False,True):
        lines=retained_coverage_disclosures({'identity':SCOPE,'assessment':{'canonical_scanner_finding_register':register}},spanish=spanish)
        assert CAPTURE_LABELS['inventory_missing_or_unsupported'][int(spanish)]+': 1.' in lines
    assert 'example.py' not in str(result['path_capture_outcomes'])


def test_deadline_records_only_current_visited_boundary():
    rows=[row(source_path='a.py'),row(candidate_id='later',source_path='b.py')]
    now=[0]
    def inventory(*args):now[0]=5;return {}
    result=c.capture_candidates(rows,SCOPE,inventory,lambda *a:pytest.fail('no late read'),clock=lambda:now[0])
    assert reason(result,'a.py')=='capture_deadline'
    assert reason(result,'b.py') is None
    assert view(rows,result)['source_availability_counts']=={'capture_deadline':1,'source_not_retained':1}


def test_multibyte_path_diagnostics_are_byte_bounded_and_scope_bound():
    path='código/测试.py'
    result=c.capture_candidates([row(source_path=path)],SCOPE,lambda *a:{},lambda *a:b'',clock=lambda:0)
    assert reason(result,path)=='inventory_missing_or_unsupported'
    assert len(c.encoded(result))<=c.OUTPUT_LIMIT
    assert path not in str(result['path_capture_outcomes'])
    for field in SCOPE:
        foreign=deepcopy(result);foreign['scope'][field]='foreign'
        assert not view([row(source_path=path)],foreign)['source_availability_counts']


def test_non_utf8_candidate_path_cannot_crash_diagnostic_recording():
    rows=[row(source_path='invalid\ud800.py')]
    result=c.capture_candidates(rows,SCOPE,lambda *a:{},lambda *a:pytest.fail('no read'),clock=lambda:0)
    assert not result['path_capture_outcomes']['path_sha256_reasons']
    result['path_capture_outcomes']['path_sha256_reasons'][None]='input_size_limit'
    assert view(rows,result)['source_availability_counts']=={'source_not_retained':1}
