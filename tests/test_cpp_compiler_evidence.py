"""Compiler evidence cannot be inferred from a compilation database."""
import json
import pytest
from nico.assessment_cpp_compiler_evidence import safe_compile_argv, parse_dependencies

SOURCE = '/work/source/main.cpp'
BASE = ['/usr/local/bin/g++', '-I/work/source', '-DVALUE=1', '-g', '-std=c++20',
        '-o', 'CMakeFiles/control.dir/main.cpp.o', '-c', SOURCE]


def test_output_and_dependency_destinations_are_owned_by_the_analyst():
    command = safe_compile_argv(BASE, SOURCE, '/work/analysis/compiler-baseline/u0')
    assert command[-7:] == ['-o', '/work/analysis/compiler-baseline/u0.o', '-MD', '-MF',
        '/work/analysis/compiler-baseline/u0.d', '-MT', 'nico_unit']
    assert '-I/work/source' in command and '-DVALUE=1' in command and '-std=c++20' in command
    assert 'CMakeFiles/control.dir/main.cpp.o' not in command


@pytest.mark.parametrize('extra', [
    ['-fplugin=/work/source/plugin.so'], ['-specs=/work/source/specs'], ['-B/work/source'],
    ['-wrapper', '/work/source/wrapper'], ['@/work/source/response'], ['-Wa,--help'],
    ['-Xassembler','--help'], ['-save-temps'], ['-include','/proc/self/environ'],
    ['-I/work/build'], ['-I/work/source/../build'], ['-x','assembler'], ['-E'], ['--help'],
    ['-DVALUE=1\nother'], ['-c', '/work/source/other.cpp'], ['-o', '/work/source/out'],
])
def test_unsafe_or_mutable_context_cannot_run_as_the_analyst(extra):
    with pytest.raises(ValueError): safe_compile_argv(BASE + extra, SOURCE, '/work/analysis/compiler-baseline/u0')


def test_dependency_file_records_actual_original_header_visits():
    raw = b'nico_unit: /work/source/main.cpp \\\n /work/source/sum.hpp /usr/include/stdc-predef.h\n'
    assert parse_dependencies(raw) == ['/work/source/main.cpp', '/work/source/sum.hpp', '/usr/include/stdc-predef.h']


@pytest.mark.parametrize('raw', [b'', b'other: /work/source/a.cpp', b'nico_unit: ../bad',
    b'nico_unit: /work/source/a.cpp\nother: /work/source/b.cpp', b'nico_unit: /work/source/a.cpp\x00'])
def test_ambiguous_dependency_files_are_not_coverage(raw):
    with pytest.raises(ValueError): parse_dependencies(raw)


def v2_fixture():
    from copy import deepcopy
    import base64, hashlib
    from tests.test_assessment_cpp_full_project import plan, native, encoded
    from nico.assessment_cpp_full_project import execution_steps
    p = plan()
    p['configuration'].update(schema='nico.cpp-cmake-configuration.v2', compiler_evidence='isolated-recompile-v1')
    n = native(p)
    def execution(raw):
        return {'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'duration_ms': 1,
                'output': encoded(raw), 'output_sha256': hashlib.sha256(raw).hexdigest()}
    for group in ('baseline', 'address', 'undefined'):
        configure = next(r for r in n['steps'] if r['id'] == group + '-configure')
        db = json.loads(base64.b64decode(configure['artifacts']['compilation_database']))
        for row in db: row['arguments'] += ['-o', 'target.o']
        db_raw = json.dumps(db).encode()
        configure['artifacts']['compilation_database'] = encoded(db_raw)
        if group == 'baseline':
            next(r for r in n['steps'] if r['id'] == 'static-analysis')['artifacts']['compilation_database'] = encoded(db_raw)
        proof = {'schema': 'nico.cpp-direct-compiler.v1', 'configuration': group,
            'database_sha256': hashlib.sha256(db_raw).hexdigest(), 'analyst_uid': 1001,
            'records': [], 'test_binary_instrumentation_verified': False}
        for index, row in enumerate(db):
            unit = row['file'].removeprefix('/work/source/')
            deps = ('nico_unit: ' + row['file'] + ' /work/source/sum.hpp\n').encode()
            proof['records'].append({'unit': unit, 'source_sha256': p['targets'][unit],
                'invocation': safe_compile_argv(row['arguments'], row['file'], '/work/analysis/compiler-' + group + '/u' + str(index)),
                'compiler': execution(b''), 'object_sha256': 'f' * 64, 'object_bytes': 128,
                'dependency_bytes': encoded(deps), 'dependency_sha256': hashlib.sha256(deps).hexdigest(),
                'source_dependencies': {unit: p['targets'][unit], 'sum.hpp': p['targets']['sum.hpp']},
                'nm': execution(b'                 U ' + (b'__asan_init' if group == 'address' else b'__ubsan_handle_add_overflow' if group == 'undefined' else b'printf') + b'\n'), 'error': None})
        stage = next(r for r in n['steps'] if r['id'] == group + '-compiler-evidence')
        stage['output'] = encoded(json.dumps(proof).encode()); stage['duration_ms'] = 10
    return p, n


def test_v2_records_direct_compiler_and_original_header_populations():
    from nico.assessment_cpp_full_project import validate_native
    p, n = v2_fixture(); result = validate_native(n, p)
    assert result['complete'] is True
    assert result['build']['compiled_translation_units'] == ['main.cpp', 'sum.cpp']
    assert result['build']['compiler_evidence']['baseline']['header_inclusions'] == {'sum.hpp': ['main.cpp', 'sum.cpp']}
    assert result['coverage']['header_context_verified'] is True
    assert result['build']['implemented_command_scope_complete'] is True
    assert result['build']['sanitizers']['address']['instrumentation_verified'] is False
    assert result['build']['compiler_evidence']['address']['object_instrumentation_observed_units'] == ['main.cpp', 'sum.cpp']
    assert result['build']['full_project_qualified'] is False


@pytest.mark.parametrize('mutation', ['database','source','unit','command','uid','object','dependency','header','nm','success_flag'])
def test_substituted_evidence_cannot_grant_compiler_coverage(mutation):
    import base64
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p, n = v2_fixture()
    stage = next(r for r in n['steps'] if r['id'] == 'baseline-compiler-evidence')
    proof = json.loads(base64.b64decode(stage['output'])); record = proof['records'][0]
    if mutation == 'database': proof['database_sha256'] = '0' * 64
    elif mutation == 'source': record['source_sha256'] = '0' * 64
    elif mutation == 'unit': record['unit'] = 'other.cpp'
    elif mutation == 'command': record['invocation'][0] = '/tmp/compiler'
    elif mutation == 'uid': proof['analyst_uid'] = True
    elif mutation == 'object': record['object_bytes'] = True
    elif mutation == 'dependency': record['dependency_sha256'] = '0' * 64
    elif mutation == 'header': record['source_dependencies']['sum.hpp'] = '0' * 64
    elif mutation == 'nm': record['nm']['output_sha256'] = '0' * 64
    else: proof['complete'] = True
    stage['output'] = encoded(json.dumps(proof).encode())
    with pytest.raises(ValueError):
        validate_native(n, p)


def test_version_one_remains_unqualified_without_inventing_new_evidence():
    from tests.test_assessment_cpp_full_project import plan, native
    from nico.assessment_cpp_full_project import validate_native, execution_steps
    p = plan(); result = validate_native(native(p), p)
    assert 'compiler_evidence' not in result['build']
    assert result['build']['compiled_translation_units'] is None
    assert all('compiler_configuration' not in row for row in execution_steps(p))


def test_failed_compiler_is_retained_without_counting_the_unit_completed():
    import base64
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p,n = v2_fixture(); stage = next(r for r in n['steps'] if r['id'] == 'baseline-compiler-evidence')
    proof = json.loads(base64.b64decode(stage['output']))
    proof['records'][0]['compiler']['exit_code'] = 1
    stage['output'] = encoded(json.dumps(proof).encode())
    result = validate_native(n,p)
    assert result['build']['compiled_translation_units'] == ['sum.cpp']
    assert result['build']['compiler_evidence']['baseline']['attempted_translation_units'] == ['main.cpp','sum.cpp']
    assert result['build']['implemented_command_scope_complete'] is False
    assert result['coverage']['header_context_verified'] is False


def test_missing_object_symbols_do_not_certify_instrumentation():
    import base64,hashlib
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p,n=v2_fixture();stage=next(r for r in n['steps'] if r['id']=='address-compiler-evidence')
    proof=json.loads(base64.b64decode(stage['output']))
    for row in proof['records']:
        row['nm']['output']=encoded(b'');row['nm']['output_sha256']=hashlib.sha256(b'').hexdigest()
    stage['output']=encoded(json.dumps(proof).encode())
    result=validate_native(n,p)
    assert result['build']['compiler_evidence']['address']['object_instrumentation_observed_units']==[]
    assert result['build']['compiler_evidence']['address']['test_binary_instrumentation_verified'] is False


def test_analyst_collector_uses_only_its_own_identity_and_bounded_source_request(tmp_path):
    import base64
    from tests.test_assessment_cpp_full_project import FakeDocker
    from nico.assessment_cpp_compiler_evidence import PROGRAM
    from nico.assessment_cpp_full_project_execution import run_full_project
    p,n=v2_fixture()
    # The historical contract fixture hashes the path string, not these compiler test bytes.
    for path in p['targets']:(tmp_path/path).write_bytes(path.encode())
    class CompilerDocker(FakeDocker):
        def __call__(self,args,**kwargs):
            if PROGRAM in args:
                self.calls.append((args,kwargs))
                assert '--user=1001:1001' in args and '--interactive' in args
                request=json.loads(kwargs['input_bytes'])
                assert request['targets']==p['targets'] and request['units']==p['configuration']['translation_units']
                row=next(r for r in n['steps'] if r['id']==request['configuration']+'-compiler-evidence')
                return {'output':base64.b64decode(row['output']),'exit_code':0,'timed_out':False,'output_truncated':False}
            return super().__call__(args,**kwargs)
    fake=CompilerDocker(p,n)
    result=run_full_project(p,tmp_path,checkpoint=lambda:None,timeout_seconds=60,command=fake)
    assert result['native']['error'] is None
    assert len([c for c,k in fake.calls if PROGRAM in c])==3
    assert fake.calls[-1][0][:3]==['docker','rm','--force']


@pytest.mark.parametrize('failed', [False, True])
def test_nested_stream_redaction_is_enforced_even_on_failed_compilation(monkeypatch, failed):
    import base64, hashlib
    from nico import scanner_tool_runners
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import encoded
    p,n=v2_fixture();stage=next(r for r in n['steps'] if r['id']=='baseline-compiler-evidence')
    proof=json.loads(base64.b64decode(stage['output']))
    row=proof['records'][0]['compiler']
    raw=b'fixture-sensitive-marker';row['output']=encoded(raw);row['output_sha256']=hashlib.sha256(raw).hexdigest()
    if failed: row['exit_code']=1
    stage['output']=encoded(json.dumps(proof).encode())
    previous=scanner_tool_runners.redact_text
    monkeypatch.setattr(scanner_tool_runners,'redact_text',lambda value:previous(value).replace('fixture-sensitive-marker','[redacted]'))
    with pytest.raises(ValueError,match='redaction_required'):
        validate_native(n,p)


@pytest.mark.parametrize('language,phrase', [('en', 'Direct compiler verification: 2/2'),
                                           ('es-MX','Compilación directa verificada: 2/2')])
def test_normal_report_exports_retain_direct_compiler_evidence(tmp_path,language,phrase):
    from scripts.qualify_cpp_full_project_integration import render_result
    from tests.test_assessment_cpp_full_project import wrap
    from nico.assessment_worker_receipts import validate_receipt
    from scripts.worker_protocol_fixture import identity
    from nico.assessment_worker_jobs import _digest
    p,n=v2_fixture();receipt=wrap(n,p)
    _,record,_=validate_receipt(identity(p),p,receipt['lease_id'],receipt['worker_id'],receipt)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(receipt))
    render_result({'canonical_record':record},tmp_path,language)
    assert phrase in (tmp_path/('owned-project-'+language+'.md')).read_text()


@pytest.mark.parametrize('value',[1,0,None,'false','true',[]])
def test_compiler_mode_is_not_selected_by_malformed_boolean(value):
    from nico.assessment_cpp_full_project import configuration
    with pytest.raises(ValueError):
        configuration(units=['main.cpp'],unit_tests=['unit'],integration_tests=['integration'],compiler_evidence=value)
