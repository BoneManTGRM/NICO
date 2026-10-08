"""Physical staging is request-bound; library models supply no header credit."""
import base64
from copy import deepcopy
import hashlib
import pytest
from nico import assessment_cpp_static_environment as env
from nico import assessment_cpp_project_static as static
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_static_environment import fixture, evidence
from tests.test_cpp_static_environment_integration import native_v2


def physical(tmp_path):
    database, targets, snapshot, compiler, raw = fixture(tmp_path)
    request = env.environment_request(compiler, raw, 'sha256:'+'a'*64, physical_header_inputs=True)
    native = evidence(request)
    model = env.validate_environment(_canonical(native), request)
    return database, targets, snapshot, compiler, raw, request, native, model


def test_exact_public_header_is_projected_without_changing_compiler_or_limits(tmp_path):
    database, targets, snapshot, compiler, raw, request, native, model = physical(tmp_path)
    legacy_request=env.environment_request(compiler,raw,'sha256:'+'a'*64)
    legacy=env.validate_environment(_canonical(evidence(legacy_request)),legacy_request)
    assert legacy['headers']['/usr/include/stdint.h']['projection'] is None
    assert request['contexts']==legacy_request['contexts']
    assert request['limits']==legacy_request['limits']==env.ENV_LIMITS
    for path, member in model['headers'].items():
        assert member['projection']==env.ROOT+'/headers'+path
        assert member['model'] is None and member['modeled_name'] is None
        assert member['sha256']==native['headers'][path]['sha256']
    assert env.bind_environment(model,compiler,raw)==model
    sreq=static.project_static_request(database,targets,snapshot,raw,environment=model)
    assert sreq['limits']=={'wall_seconds':540,'case_seconds':90,'parallel':2}
    proof=static.validate_project_static(native_v2(sreq,missing='stdint.h'),sreq)
    assert proof['analyzed_contexts']==[] and proof['modeled_inputs']==[]
    assert not proof['complete'] and not proof['analyzer_header_coverage_verified']
    assert any(x['rule_id']=='missingIncludeSystem' for x in proof['limitations'])


@pytest.mark.parametrize('fault',['omit-mode','false-mode','wrong-request','substitute-bytes','omit-header','timeout'])
def test_physical_receipt_rejects_missing_mismatched_or_incomplete_evidence(tmp_path,fault):
    *_,request,native,model=physical(tmp_path)
    if fault=='omit-mode':native.pop('physical_header_inputs')
    elif fault=='false-mode':native['physical_header_inputs']=False
    elif fault=='wrong-request':native['request_sha256']='0'*64
    elif fault=='substitute-bytes':next(iter(native['headers'].values()))['base64']=base64.b64encode(b'wrong bytes').decode()
    elif fault=='omit-header':native['headers'].clear()
    else:next(iter(native['queries'].values()))['predefines']['timed_out']=True
    with pytest.raises(ValueError):env.validate_environment(_canonical(native),request)


@pytest.mark.parametrize('fault',['downgrade','unproject','redirect','reclassify'])
def test_physical_plan_rejects_rehashed_false_projection(tmp_path,fault):
    _,_,_,compiler,raw,_,_,model=physical(tmp_path)
    if fault=='downgrade':model.pop('physical_header_inputs')
    else:
        member=next(iter(model['headers'].values()))
        if fault=='unproject':member['projection']=None
        elif fault=='redirect':member['projection']='/usr/include/stdint.h'
        else:member.update(model='std',modeled_name='stdint.h')
        model['header_population_sha256']=hashlib.sha256(_canonical(model['headers'])).hexdigest()
    with pytest.raises(ValueError):env.bind_environment(model,compiler,raw)


def test_isolated_program_binds_physical_parallelism_without_increasing_any_budget():
    namespace={'__name__':'owned_embedded'}
    exec(static.PROGRAM.rsplit('\nrun_project_static()',1)[0],namespace)
    request={'compiler_environment':{'physical_header_inputs':True}}
    assert namespace['_request_limits'](request)==static.PHYSICAL_LIMITS
    assert static.PHYSICAL_LIMITS=={**static.LIMITS,'parallel':2}
    assert static.STAGE_BUDGET['shared_execution_seconds']==1020
