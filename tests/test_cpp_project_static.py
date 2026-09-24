"""Context-bound Cppcheck contracts; synthetic receipts are never native proof."""
import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from tests.test_cpp_project_compiler import inputs, digest, result_for
from nico.assessment_cpp_project_compiler import project_compiler_request, _canonical


def api():
    assert importlib.util.find_spec('nico.assessment_cpp_project_static'), 'missing context-complete static analysis'
    from nico import assessment_cpp_project_static
    return assessment_cpp_project_static


def request(tmp_path, extra=()):
    database, targets, snapshot, _ = inputs(tmp_path, extra)
    compiler_request = project_compiler_request(database, targets, snapshot)
    compiler_raw = _canonical(result_for(compiler_request))
    return api().project_static_request(database, targets, snapshot, compiler_raw)


def execution(output=b'', exit_code=0):
    return dict(exit_code=exit_code, timed_out=False, output_truncated=False,
                duration_ms=1, output=base64.b64encode(output).decode(), output_sha256=digest(output))


def native(req, rule=None):
    rows=[]
    for context in req['contexts']:
        path=context['analysis_file']
        severity="information" if rule in {"missingInclude", "missingIncludeSystem", "checkersReport"} else "warning"
        diagnostic=(f'<error id="{rule}" severity="{severity}" msg="Owned diagnostic"><location file="{path}" line="1"/></error>'
                    if rule else '')
        xml=(f'<results version="2"><cppcheck version="2.17.1"/><errors>{diagnostic}</errors></results>').encode()
        rows.append({'context_id':context['context_id'],'invocation':context['analyzer_invocation'],
            'database_sha256':context['analyzer_database_sha256'],
            'execution':execution(('Checking '+path+' ...\n').encode()),
            'xml':base64.b64encode(xml).decode(),'xml_sha256':digest(xml),'error':None})
    return {'schema':'nico.cpp-project-static-evidence.v1', 'request_sha256':digest(_canonical(req)),
            'analyst_uid':1001,'version':execution(b'Cppcheck 2.17.1\n'), 'records':rows, 'duration_ms':10}


def test_plan_preserves_each_context_and_uses_single_entry_databases(tmp_path):
    req=request(tmp_path)
    assert len(req['contexts'])==3
    assert req['contexts'][0]['context_id']!=req['contexts'][1]['context_id']
    for row in req['contexts']:
        db=json.loads(row['analyzer_database'])
        assert len(db)==1 and db[0]['file']==row['analysis_file']
        assert db[0]['arguments']==row['invocation']
        assert row['analyzer_database_sha256']==digest(row['analyzer_database'].encode())
        assert row['analyzer_invocation'][0]=='/usr/local/bin/cppcheck'
        assert '--max-configs=1' in row['analyzer_invocation']
        assert '--check-level=exhaustive' in row['analyzer_invocation']
        assert not any(a.startswith(('--addon','--suppress','--force','--rule')) for a in row['analyzer_invocation'])
        assert any(a.startswith('--project=/work/analysis/static-baseline/u') for a in row['analyzer_invocation'])
    assert req['tool_version']=='2.17.1'
    assert req['limits']=={'wall_seconds':540,'case_seconds':90,'parallel':4}
    assert req['compiler_evidence_sha256']


def test_incomplete_compiler_evidence_prevents_static_plan(tmp_path):
    database,targets,snapshot,_=inputs(tmp_path)
    c=project_compiler_request(database,targets,snapshot); output=result_for(c)
    output['records'][0]['execution']['exit_code']=1
    with pytest.raises(ValueError): api().project_static_request(database,targets,snapshot,_canonical(output))


@pytest.mark.parametrize('option',['-iquote','-include','-imacros'])
def test_unmodeled_preprocessor_operands_are_not_silently_ignored(tmp_path,option):
    with pytest.raises(ValueError): request(tmp_path,[option,'/work/source/original.h'])


def test_completed_native_contexts_are_not_collapsed_or_claimed_production(tmp_path):
    req=request(tmp_path); output=native(req)
    proof=api().validate_project_static(_canonical(output),req)
    assert proof['complete'] is True and len(proof['analyzed_contexts'])==3
    assert proof['required_contexts']==proof['attempted_contexts']==proof['analyzed_contexts']
    assert proof['static_analysis_executed'] is True
    assert proof['production_qualified'] is False and proof['human_review_completed'] is False
    assert proof['findings']==[] and proof['analyzer_header_coverage_verified'] is False


def test_findings_retain_context_namespace_and_source_hash(tmp_path):
    req=request(tmp_path); proof=api().validate_project_static(_canonical(native(req,'uninitvar')),req)
    assert proof['complete'] is True and len(proof['findings'])==3
    assert len({f['id'] for f in proof['findings']})==3
    assert [f['context_id'] for f in proof['findings']]==[c['context_id'] for c in req['contexts']]
    assert {f['origin'] for f in proof['findings']}=={'original','generated'}
    assert all(f['source_sha256'] and f['classification']=='review_required_candidate' for f in proof['findings'])
    assert proof['findings'][-1]['path']=='generated/file.capnp.c++'
    assert not any(f['specialist_review_completed'] for f in proof['findings'])


@pytest.mark.parametrize('fault',['missing','duplicate','argv','db-digest','request','version','uid','bool-exit',
    'xml-digest','malformed','external-entity','unexpected-claim','duration','unbound-location'])
def test_tampered_static_evidence_is_rejected(tmp_path,fault):
    req=request(tmp_path); data=native(req,'uninitvar'); row=data['records'][0]
    if fault=='missing': data['records'].pop()
    if fault=='duplicate': data['records'][1]=deepcopy(row)
    if fault=='argv': row['invocation']=['true']
    if fault=='db-digest': row['database_sha256']='0'*64
    if fault=='request': data['request_sha256']='0'*64
    if fault=='version': data['version']=execution(b'Cppcheck 2.18.0\n')
    if fault=='uid': data['analyst_uid']=0
    if fault=='bool-exit': row['execution']['exit_code']=True
    if fault=='xml-digest': row['xml_sha256']='0'*64
    if fault in ('malformed','external-entity','unbound-location'):
        raw=(b'<broken' if fault=='malformed' else
             b'<!DOCTYPE results [<!ENTITY leak SYSTEM "file:///etc/passwd">]><results>&leak;</results>' if fault=='external-entity' else
             b'<results version="2"><cppcheck version="2.17.1"/><errors><error id="uninitvar" severity="warning" msg="owned"><location file="/work/source/not-bound.cpp" line="1"/></error></errors></results>')
        row['xml']=base64.b64encode(raw).decode(); row['xml_sha256']=digest(raw)
    if fault=='unexpected-claim': data['complete']=True
    if fault=='duration': row['execution']['duration_ms']=99000
    with pytest.raises(ValueError): api().validate_project_static(_canonical(data),req)


@pytest.mark.parametrize('fault',['exit','timeout','truncated','no-progress','missing-include','syntax','unattempted'])
def test_failures_never_receive_completed_coverage_and_other_contexts_survive(tmp_path,fault):
    req=request(tmp_path); data=native(req); row=data['records'][0]
    if fault=='exit': row['execution']['exit_code']=1
    if fault=='timeout': row['execution']['timed_out']=True
    if fault=='truncated': row['execution']['output_truncated']=True
    if fault=='no-progress': row['execution']=execution()
    if fault in ('missing-include','syntax'):
        raw=base64.b64decode(native(req,'missingInclude' if fault=='missing-include' else 'syntaxError')['records'][0]['xml'])
        row['xml']=base64.b64encode(raw).decode();row['xml_sha256']=digest(raw)
    if fault=='unattempted':
        row.update(execution=None,xml='',xml_sha256=None,error='worker_project_static_deadline')
    proof=api().validate_project_static(_canonical(data),req)
    assert proof['complete'] is False and len(proof['analyzed_contexts'])==2
    assert req['contexts'][0]['context_id'] not in proof['analyzed_contexts']


def test_checker_inventory_information_does_not_hide_real_parse_limitations(tmp_path):
    req=request(tmp_path); data=native(req,'checkersReport')
    # Use the pinned tool's real positive inventory, not a fabricated message.
    for row in data['records']:
        xml=base64.b64decode(row['xml']).replace(b'Owned diagnostic',
            b'Active checkers: 167/856 (use --checkers-report=&lt;filename&gt; to see details)')
        row.update(xml=base64.b64encode(xml).decode(), xml_sha256=digest(xml))
    proof=api().validate_project_static(_canonical(data),req)
    assert proof['complete'] is True and len(proof['limitations'])==3


def test_embedded_program_is_self_contained_and_has_no_host_project_imports():
    program=api().PROGRAM
    compile(program,'owned-embedded-static-program','exec')
    assert 'from nico' not in program and 'import nico' not in program
    assert 'shell=False' in program and 'os.getuid() != 1001' in program


def _simple_compiler_native(req):
    records=[]
    for context in req['contexts']:
        deps=('nico_unit: '+context['analysis_file']+'\n').encode()
        records.append({'context_id':context['context_id'],'invocation':context['invocation'],
            'execution':execution(), 'dependency_bytes':base64.b64encode(deps).decode(),
            'dependency_sha256':digest(deps), 'source_dependencies':{context['path']:req['targets'][context['path']]},
            'generated_dependencies':{},'toolchain_dependencies':[], 'error':None})
    return {'schema':'nico.cpp-project-compiler-evidence.v1', 'request_sha256':digest(_canonical(req)),
            'analyst_uid':1001,'records':records,'duration_ms':5}


@pytest.mark.parametrize('fault',[None,'exit','timeout','truncated','missing','digest','analyzer-failure','sink'])
def test_probe_static_stage_is_ordered_bound_and_preserves_prior_success(tmp_path,fault):
    import inspect
    from nico import assessment_cpp_configuration_probe as probe
    from nico import assessment_cpp_project_compiler as compiler
    from nico import assessment_cpp_project_snapshot as snapshot
    from tests.test_cpp_baseline_execution import Native, source, contract
    from tests.test_cpp_project_snapshot import _empty_native_snapshot
    assert 'project_static_analysis' in inspect.signature(probe.probe_project_configuration).parameters, 'missing static probe integration'
    root,targets=source(tmp_path); baseline=Native(targets); kept={}; saved=[]
    from tests.test_cpp_project_static_stage import StaticDocker
    static_docker = StaticDocker(targets)
    baseline_cleaned = False
    def command(argv,**kwargs):
        nonlocal baseline_cleaned
        if baseline_cleaned and api().PROGRAM not in argv:
            baseline.calls.append((argv, kwargs))
            return static_docker(argv, **kwargs)
        if argv[1:3] == ['rm', '--force']:
            baseline_cleaned = True
        if snapshot.PROJECT_SNAPSHOT_PROGRAM in argv:
            baseline.calls.append((argv,kwargs)); raw=_canonical(_empty_native_snapshot(json.loads(kwargs['input_bytes'])))
        elif compiler.PROGRAM in argv:
            baseline.calls.append((argv,kwargs)); raw=_canonical(_simple_compiler_native(json.loads(kwargs['input_bytes'])))
        elif api().PROGRAM in argv:
            baseline.calls.append((argv,kwargs)); data=native(json.loads(kwargs['input_bytes']))
            if fault=='missing': data['records'].pop()
            if fault=='digest': data['request_sha256']='0'*64
            if fault=='analyzer-failure': data['records'][0]['execution']['exit_code']=1
            return dict(exit_code=1 if fault=='exit' else 0,timed_out=fault=='timeout',
                        output_truncated=fault=='truncated',output=_canonical(data))
        else: return baseline(argv,**kwargs)
        return dict(exit_code=0,timed_out=False,output_truncated=False,output=raw)
    def sink(key,raw):
        kept[key]=raw
        if fault=='sink' and key=='project-static-evidence': raise OSError('synthetic storage failure')
        return dict(path='artifacts/'+key+'-'+digest(raw)+'.json',sha256=digest(raw),bytes=len(raw))
    result=probe.probe_project_configuration(root,targets,'sha256:'+'a'*64,project_options={'BUILD_TESTS':'ON'},
        baseline_execution=contract(), capture_generated_context=True,project_compiler_evidence=True,
        project_static_analysis=True,command=command,retain_artifact=sink,retain=lambda r:saved.append(deepcopy(r)))
    assert result['compiled'] and result['tests_passed'] and result['project_compiler']['complete']
    assert result['cleanup_verified'] and not result['full_project_qualified']
    assert 'project-static-evidence' in kept
    if fault:
        assert result['status']=='UNPROVEN'
        assert not result['project_static'] or not result['project_static']['complete']
    else:
        assert result['status']=='BASELINE_EXECUTED'
        assert result['schema']=='nico.cpp-project-configuration-probe.v6'
        assert result['project_static']['complete']
        ids=[r['id'] for r in result['operations']]
        assert ids.index('project-generated-context')<ids.index('project-compiler-evidence')
        assert result['project_static_stage']['complete']
        operation=result['project_static_stage']['operations'][-1]
        assert operation['output'] is None and operation['output_artifact']['sha256']==digest(kept['project-static-evidence'])
        argv,options=next((a,k) for a,k in baseline.calls if api().PROGRAM in a)
        assert '--user=1001:1001' in argv and options['timeout']<=550
    assert saved[-1]==result


def test_static_artifact_has_same_immutable_retention_contract(tmp_path):
    from scripts.qualify_cpp_project_configuration import persist_project_artifact
    raw=b'{"synthetic_static_test":true}'
    ref=persist_project_artifact(tmp_path,'project-static-evidence',raw)
    assert (tmp_path/ref['path']).read_bytes()==raw and ref['sha256']==digest(raw)


def test_existing_workflow_requires_owned_static_diagnostic_before_bitcoin():
    root=Path(__file__).resolve().parents[1]
    workflow=(root/'.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_project_static.py' in workflow
    assert workflow.count('--project-static-analysis')==2
    control=(root/'scripts/qualify_cpp_project_generated_context.py').read_text()
    assert "['analyzed_contexts']" in control and "'uninitvar'" in control


def test_standalone_generated_input_verification_retains_current_snapshot_bound(tmp_path, monkeypatch):
    """The serialized analyst program must carry dependencies of imported helpers."""
    import ast
    from types import SimpleNamespace
    from nico import assessment_cpp_project_snapshot as snapshot
    module = ast.parse(api().PROGRAM)
    assert isinstance(module.body[-1], ast.Expr)
    module.body.pop()  # Exercise the generated program's function, not host imports.
    scope = {}
    exec(compile(module, 'isolated-static-program', 'exec'), scope)
    root = tmp_path / 'generated'; root.mkdir()
    raw = b'owned generated header'; (root / 'config.h').write_bytes(raw)
    monkeypatch.setattr(Path, 'lstat', lambda self: SimpleNamespace(st_uid=1001, st_mode=0o100444))
    scope['_verify_input'](root, 'config.h', digest(raw), len(raw), True)
    assert scope['GENERATED_FILE_LIMIT'] == snapshot.PROJECT_GENERATED_MAX_FILE_BYTES == 32 * 1024 * 1024
    with pytest.raises(ValueError, match='input_mismatch'):
        scope['_verify_input'](root, 'config.h', '0' * 64, len(raw), True)
