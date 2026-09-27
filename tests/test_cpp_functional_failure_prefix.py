"""Owned transport failures at the functional stage; no assessed code executes."""
from copy import deepcopy
import base64
import hashlib
import json
import pytest

from nico.assessment_cpp_runtime_execution import execute_runtime_plan, validate_runtime_evidence
from tests.test_cpp_runtime_execution import Observe, plan, csv_bytes

OPTIONS={'BUILD_TESTS':'ON'}

class FunctionalFault(Observe):
    def __init__(self,mode):
        super().__init__(); self.mode=mode
    def __call__(self,key,argv,**kwargs):
        response=super().__call__(key,argv,**kwargs)
        if key=='runtime-functional-setup' and self.mode=='setup':
            response.update(exit_code=1,output=b'owned setup failure')
        if key=='runtime-functional' and self.mode=='timeout':
            response.update(exit_code=124,timed_out=True,output=b'owned timeout')
        if key=='runtime-functional' and self.mode=='failed':
            response.update(exit_code=1)
        if key=='runtime-functional-results':
            if self.mode in {'timeout','read'}:
                response.update(exit_code=1,output=b'owned missing CSV')
            elif self.mode in {'failed','skipped'}:
                raw=csv_bytes([['feature_a.py','Failed' if self.mode=='failed' else 'Skipped','1'],
                               ['mempool_a.py','Passed','1'],['ALL','Failed' if self.mode=='failed' else 'Passed','1']])
                response['output']=json.dumps({'data':base64.b64encode(raw).decode(),'truncated':False}).encode()
        return response


def _run(mode):
    transport=FunctionalFault(mode)
    native=execute_runtime_plan(transport,'owned-container',plan(),OPTIONS)
    return native,transport


def test_failed_functional_setup_does_not_run_dependents():
    native,transport=_run('setup')
    assert list(transport.calls)==['runtime-functional-setup']
    verified=validate_runtime_evidence(native,plan(),project_options=OPTIONS)
    assert verified['complete'] is False
    assert verified['failure_operation']=='runtime-functional-setup'
    assert verified['functional']['state']=='not_executed'
    assert verified['functional']['executed']==[]
    assert verified['sanitizers_not_executed']==['address','undefined']


@pytest.mark.parametrize('mode',['timeout','read','failed','skipped'])
def test_functional_failure_is_retained_and_reconstructible(mode):
    native,transport=_run(mode)
    assert native['functional'] is not None
    assert list(transport.calls)==['runtime-functional-setup','runtime-functional','runtime-functional-results']
    verified=validate_runtime_evidence(native,plan(),project_options=OPTIONS)
    assert verified['complete'] is False
    assert verified['sanitizers']==[]
    assert verified['sanitizers_not_executed']==['address','undefined']
    assert verified['fuzz']['state']=='not_executed'
    assert verified['functional']['required']==plan()['functional']['selected_tests']
    if mode in {'timeout','read'}:
        assert verified['functional']['passed'] is None
        assert verified['functional']['executed'] is None
    elif mode=='failed':
        assert verified['functional']['failed']==['feature_a.py']
        assert verified['functional']['executed']==plan()['functional']['selected_tests']
    else:
        assert verified['functional']['skipped']==['feature_a.py']
        assert verified['functional']['executed']==['mempool_a.py']
    assert verified['failure_operation']==('runtime-functional-results' if mode=='read' else 'runtime-functional')


def _render(functional,language):
    from nico.assessment_cpp_full_project_report import enrich_scanner_stage
    digest='a'*64; revision='b'*40
    record={'commit_sha':revision,'raw_artifact_retention_complete':True,
        'raw_artifact_sha256':digest,'current_run':True,'exact_commit_match':True,
        'execution_observed_for_this_report':True,
        'worker_provenance':{'profile':'cpp-configure-first-v2','receipt_sha256':digest,
            'identity':{'run_id':'owned','revision':revision}},
        'cppcheck_source_coverage':{'header_context_verified':True},
        'cpp_build_evidence':{'profile':'cpp-configure-first-v2','compiled':True,
            'runtime_scope':{'complete':False,'functional':functional,'sanitizers':[],
                'sanitizers_not_executed':['address','undefined'],
                'fuzz':{'state':'not_executed','target':'owned','required_replay_count':2}}}}
    rendered=enrich_scanner_stage({'report_language':language,
        'identity':{'run_id':'owned','commit_sha':revision},'scanner_execution_records':[record]},
        {'summary':'','evidence':[],'unavailable':[]})
    return ' '.join([rendered['summary'],*rendered['evidence'],*rendered['unavailable']])


def test_unknown_functional_result_is_not_zero_in_either_locale():
    functional={'required':['owned_a','owned_b'],'passed':None,'executed':None,'state':'timed_out'}
    for language,term in [('en','passed=unknown/2'),('es-MX','aprobadas=desconocido/2')]:
        text=_render(functional,language)
        assert term in text
        assert 'None' not in text


@pytest.mark.parametrize('mutation', ['command','user','workdir','environment','output_hash','bool_exit',
    'negative_duration','missing_read','false_complete','wrong_error','future_sanitizer','future_fuzz',
    'future_reclamation','future_diagnostic','wrong_plan'])
def test_unknown_functional_prefix_cannot_accept_tampered_evidence(mutation):
    native,_=_run('timeout')
    wrong=deepcopy(native)
    row=wrong['functional']['operation']
    if mutation=='command': row['argv'][0]='other'
    elif mutation=='user': row['user']='0:0'
    elif mutation=='workdir': row['workdir']='/wrong'
    elif mutation=='environment': row['environment']={}
    elif mutation=='output_hash': row['output_sha256']='0'*64
    elif mutation=='bool_exit': row['exit_code']=True
    elif mutation=='negative_duration': row['duration_ms']=-1
    elif mutation=='missing_read': wrong['functional']['results_read']=None
    elif mutation=='false_complete': wrong['complete']=True
    elif mutation=='wrong_error': wrong['error']='worker_runtime_sanitizer_failed'
    elif mutation=='future_sanitizer': wrong['sanitizers']=[{'kind':'address'}]
    elif mutation=='future_fuzz': wrong['fuzz']={}
    elif mutation=='future_reclamation': wrong['reclamations']=[{}]
    elif mutation=='future_diagnostic': wrong['failure_diagnostics']=[{}]
    else: wrong['plan_sha256']='0'*64
    with pytest.raises(ValueError,match='worker_runtime_evidence_invalid'):
        validate_runtime_evidence(wrong,plan(),project_options=OPTIONS)


def test_all_passed_functional_results_cannot_hide_required_future_stages():
    native=execute_runtime_plan(Observe(),'owned-container',plan(),OPTIONS)
    native.update(complete=False,error='worker_runtime_functional_failed',sanitizers=[],fuzz=None,reclamations=[])
    with pytest.raises(ValueError,match='worker_runtime_evidence_invalid'):
        validate_runtime_evidence(native,plan(),project_options=OPTIONS)


@pytest.mark.parametrize('mode',['setup','timeout','read','failed','skipped'])
def test_verified_prefix_does_not_mutate_source_and_has_exact_native_digest(mode):
    native,_=_run(mode);original=deepcopy(native)
    first=validate_runtime_evidence(native,plan(),project_options=OPTIONS)
    second=validate_runtime_evidence(native,plan(),project_options=OPTIONS)
    from nico.assessment_worker_receipts import canonical_bytes
    assert first==second
    assert first['native_evidence_sha256']==hashlib.sha256(canonical_bytes(native)).hexdigest()
    assert original==native


@pytest.mark.parametrize('locale,word',[('en','not executed; required=2'),('es-MX','no ejecutadas; requeridas=2')])
def test_setup_failure_is_not_rendered_as_executed(locale,word):
    native,_=_run('setup')
    verified=validate_runtime_evidence(native,plan(),project_options=OPTIONS)
    assert word in _render(verified['functional'],locale)
