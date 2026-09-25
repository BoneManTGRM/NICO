import base64
import hashlib
import json

from nico.assessment_cpp_runtime_execution import execute_runtime_plan, validate_runtime_evidence


def plan():
    corpus=[
        {'path':'qa/a','git_blob_sha':'a'*40,'sha256':hashlib.sha256(b'a').hexdigest(),'bytes':1,'base64':base64.b64encode(b'a').decode()},
        {'path':'qa/b','git_blob_sha':'b'*40,'sha256':hashlib.sha256(b'b').hexdigest(),'bytes':1,'base64':base64.b64encode(b'b').decode()},
    ]
    return {'schema':'nico.cpp-runtime-plan.v1','total_seconds':6000,'unit_test_data':None,
        'functional':{'policy':'source-declared-functional-v1','runner':'test/functional/test_runner.py',
            'selected_tests':['feature_a.py','mempool_a.py'],'seconds':900,'parallel':4},
        'sanitizers':{'interface':'SANITIZERS','kinds':['address','undefined'],'build_seconds':1200,
            'test_seconds':600,'test_case_seconds':120,'parallel':4},
        'fuzz':{'policy':'source-declared-libfuzzer-v1','build_target':'fuzz','binary':'bin/fuzz',
            'target':'connect_block','qa_assets_repository':'bitcoin-core/qa-assets','qa_assets_commit':'c'*40,
            'corpus':corpus,'replay_runs':1,'campaign_runs':256,'campaign_seconds':300,'parallel':1}}


class Observe:
    def __init__(self, fault=None):
        self.fault=fault; self.calls={}
    def __call__(self,key,argv,**kwargs):
        self.calls[key]=argv
        output=b''
        exit_code=1 if key==self.fault else 0
        if key=='runtime-functional-results':
            csv=b'test,status,duration(seconds)\r\nfeature_a.py,Passed,1\r\nmempool_a.py,Passed,1\r\nALL,Passed,2\r\n'
            output=json.dumps({'data':base64.b64encode(csv).decode(),'truncated':False}).encode()
        elif key.endswith('-discover'):
            output=json.dumps({'tests':[{'name':'unit_a'}]}).encode()
        elif key.endswith('-junit'):
            xml=b'<testsuite tests="1"><testcase name="unit_a"/></testsuite>'
            output=json.dumps({'data':base64.b64encode(xml).decode(),'truncated':False}).encode()
        elif key=='runtime-fuzz-campaign':
            output=b'#2 INITED cov: 7 ft: 9 corp: 2/4b\n#256 DONE cov: 31 ft: 40 corp: 7/100b\nstat::number_of_executed_units: 256\n'
        elif key=='runtime-fuzz-corpus-stage':
            output=json.dumps([
                {'path':'/work/runtime-corpus/connect_block/s0','sha256':hashlib.sha256(b'a').hexdigest(),'bytes':1},
                {'path':'/work/runtime-corpus/connect_block/s1','sha256':hashlib.sha256(b'b').hexdigest(),'bytes':1},
            ],sort_keys=True).encode()
        return {'exit_code':exit_code,'timed_out':False,'output_truncated':False,'output':output}


def test_runtime_execution_requires_functional_sanitizers_and_bounded_fuzz():
    value=execute_runtime_plan(Observe(),'container',plan(),{'BUILD_TESTS':'ON'})
    assert value['complete'] is True and value['error'] is None
    proof=validate_runtime_evidence(value,plan())
    assert proof['complete'] is True
    assert proof['functional']['passed']==['feature_a.py','mempool_a.py']
    assert [row['kind'] for row in proof['sanitizers']]==['address','undefined']
    assert proof['fuzz']['replay_count']==2 and proof['fuzz']['campaign_completed'] is True
    assert proof['fuzz']['campaign_executions']==256 and proof['fuzz']['campaign_coverage_signal']==31
    assert '-print_final_stats=1' in value['fuzz']['campaign']['argv']


def test_runtime_execution_failure_is_retained_and_cannot_be_complete():
    value=execute_runtime_plan(Observe('runtime-fuzz-campaign'),'container',plan(),{'BUILD_TESTS':'ON'})
    assert value['complete'] is False
    assert value['error']=='worker_runtime_fuzz_failed'
    proof=validate_runtime_evidence(value,plan())
    assert proof['complete'] is False

def test_runtime_evidence_retains_raw_functional_and_sanitizer_result_reads():
    value=execute_runtime_plan(Observe(),'container',plan(),{'BUILD_TESTS':'ON'})
    assert 'results_read' in value['functional']
    assert all('junit_read' in row for row in value['sanitizers'])
    proof=validate_runtime_evidence(value,plan())
    assert proof['complete'] is True


def test_runtime_validator_rejects_tampered_retained_result_read():
    import pytest
    value=execute_runtime_plan(Observe(),'container',plan(),{'BUILD_TESTS':'ON'})
    value['functional']['results_read']['output_sha256']='0'*64
    with pytest.raises(ValueError,match='runtime_evidence_invalid'):
        validate_runtime_evidence(value,plan())
