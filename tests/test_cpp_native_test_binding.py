"""Native test-binary binding; synthetic observations are not execution proof."""
from copy import deepcopy
import base64
import hashlib
import json
import pytest

from nico.assessment_cpp_native_tests import test_plan as bound_plan, validate_evidence, inspect_dynamic_paths


def discovery(command=None, properties=None, group="address"):
    return json.dumps({'kind': 'ctestInfo', 'version': {'major': 1, 'minor': 0}, 'tests': [
        {'name': name, 'command': command or ['/work/' + group + '/control', name],
         'properties': properties if properties is not None else [
             {'name': 'WORKING_DIRECTORY', 'value': '/work/' + group}]}
        for name in ['unit', 'integration']]}).encode()


def config():
    return {'unit_tests': ['unit'], 'integration_tests': ['integration']}


def test_selected_commands_are_bound_to_the_discovered_configuration():
    plan = bound_plan(discovery(), config(), 'address')
    assert [r['name'] for r in plan] == ['integration', 'unit']
    assert plan[0]['argv'] == ['/work/address/control', 'integration']


@pytest.mark.parametrize('command', [['/bin/sh', '-c', 'true'], ['/work/undefined/control'],
    ['/work/address/../control'], ['/work/address/control', '/mutable/data'],
    ['/work/address/control', 'x\x00'], [], 'not-a-command'])
def test_unsupported_commands_are_not_silently_rewritten(command):
    raw = json.loads(discovery()); raw['tests'][0]['command'] = command
    with pytest.raises(ValueError): bound_plan(json.dumps(raw).encode(), config(), 'address')


@pytest.mark.parametrize('properties', [[{'name':'ENVIRONMENT','value':['MODE=other']}],
    [{'name':'WORKING_DIRECTORY','value':'/other'}], [{'name':'DISABLED','value':True}],
    [{'name':'WILL_FAIL','value':True}], [{'name':'TIMEOUT','value':0}]])
def test_test_semantics_cannot_be_dropped(properties):
    with pytest.raises(ValueError): bound_plan(discovery(properties=properties), config(), 'address')


def test_mutable_loader_search_paths_cannot_receive_instrumentation_credit():
    assert inspect_dynamic_paths(b' 0 (NEEDED) Shared library: [libasan.so.8]\n')
    assert not inspect_dynamic_paths(b' 0 (RUNPATH) Library runpath: [/work/address]\n')
    assert not inspect_dynamic_paths(b' 0 (RPATH) Library rpath: [$ORIGIN]\n')
    assert not inspect_dynamic_paths(b' 0 (NEEDED) Shared library: [/work/libfake.so]\n')


class Commands:
    """Only deterministic tool output for schema/dispatch tests; no Docker call."""
    def __init__(self, group="address"):
        self.group = group
        self.calls = []
        self.fail_test = None
        self.bad_probe = False
        self.nm_empty = False
        self.after_change = False
        self.verifies = 0

    def __call__(self, args, *, data=None, **kwargs):
        from nico.assessment_cpp_native_tests import SNAPSHOT_PROGRAM, VERIFY_PROGRAM, PROBE_PROGRAM
        self.calls.append((args, kwargs))
        group = self.group
        metadata = {'snapshot':'/work/native-tests/' + group + '/b0','sha256':'a'*64,'bytes':1024,'uid':0,'mode':0o555}
        out, code = b'', 0
        if SNAPSHOT_PROGRAM in args:
            assert '--user=0:0' in args and '--interactive' in args
            assert json.loads(data) == {'configuration':group,'binaries':['/work/' + group + '/control']}
            out = json.dumps({'/work/' + group + '/control':metadata}).encode()
        elif VERIFY_PROGRAM in args:
            self.verifies += 1
            if self.after_change and self.verifies % 2 == 0: metadata['sha256'] = 'b'*64
            out = json.dumps(metadata).encode()
        elif PROBE_PROGRAM in args:
            user = next(a for a in args if a.startswith('--user=')).split('=')[1]
            uid = int(user.split(':')[0])
            out = json.dumps({'uid':uid, 'gid':uid, 'write_denied':not self.bad_probe,
                'binary_sha256':'a'*64, 'no_new_privileges':True,'capabilities':0,
                'credential_environment_absent':True}).encode()
        elif '/usr/bin/nm' in args:
            assert '--user=1001:1001' in args
            out = b'' if self.nm_empty else (b'                 U __asan_init\n                 U __asan_report_load4\n' if group == 'address' else b'                 U __ubsan_handle_add_overflow_abort\n')
        elif '/usr/bin/readelf' in args:
            out = b' 0 (NEEDED) Shared library: [libasan.so.8]\n'
        else:
            assert '/work/native-tests/' + group + '/b0' in args
            from nico.assessment_cpp_native_tests import runtime_user
            assert '--user=' + runtime_user(group, 0) in args or '--user=' + runtime_user(group, 1) in args
            assert '--workdir=/work/native-tests/' + group in args
            if args[-1] == self.fail_test: code = 7
            out = b'owned test observation\n'
        return {'exit_code':code,'timed_out':False,'output_truncated':False,'output':out}


def proof(commands=None, group="address"):
    from nico.assessment_cpp_native_tests import run_bound_tests
    commands = commands or Commands(group)
    return run_bound_tests(commands, 'owned-container', group, discovery(group=group), config())


def test_controller_binds_inspected_binary_to_distinct_runtime_identities():
    commands = Commands(); result = validate_evidence(proof(commands), discovery(), config(), 'address')
    assert result['binary_instrumentation_verified'] is True
    assert result['tests_passed'] is True
    assert result['binary_bound_tests'] == ['integration', 'unit']
    assert result['runtime_users'] == ['1002:1002', '1003:1003']
    assert all(not any(a.startswith('--privileged') for a in argv) for argv, _ in commands.calls)


def test_known_failing_native_exit_remains_failed_but_instrumented():
    commands = Commands(); commands.fail_test = 'unit'
    native = proof(commands)
    result = validate_evidence(native, discovery(), config(), 'address')
    assert result['binary_instrumentation_verified'] is True
    assert result['tests_passed'] is False
    assert result['passed_tests'] == ['integration']
    assert native['tests'][1]['execution']['exit_code'] == 7


@pytest.mark.parametrize('field', ['bad_probe', 'nm_empty', 'after_change'])
def test_bad_binary_boundary_or_instrumentation_is_never_promoted(field):
    commands = Commands(); setattr(commands, field, True)
    result = validate_evidence(proof(commands), discovery(), config(), 'address')
    assert result['binary_instrumentation_verified'] is False
    assert result['tests_passed'] is False


@pytest.mark.parametrize('mutation', ['hash','uid','invocation','base64','duplicates','identity','mode'])
def test_forged_or_malformed_nested_observations_are_rejected(mutation):
    native = proof()
    if mutation == 'hash': native['tests'][0]['execution']['output_sha256'] = 'b'*64
    elif mutation == 'uid': native['tests'][0]['execution']['user'] = '1001:1001'
    elif mutation == 'invocation': native['tests'][0]['execution']['invocation'] = ['/tmp/other']
    elif mutation == 'base64': native['inspections'][0]['nm']['output'] = 'invalid'
    elif mutation == 'duplicates': native['tests'].append(native['tests'][0])
    elif mutation == 'identity': native['discovery_sha256'] = 'b'*64
    else: native['snapshots']['/work/address/control']['mode'] = 0o777
    with pytest.raises(ValueError): validate_evidence(native, discovery(), config(), 'address')


def test_opt_in_contract_preserves_older_native_stage_populations():
    from nico.assessment_cpp_full_project import configuration, execution_steps
    from nico.assessment_worker_receipts import validate_contract
    from tests.test_assessment_cpp_full_project import plan
    original = plan(); before = execution_steps(original)
    updated = deepcopy(original)
    updated['configuration'] = configuration(units=['main.cpp','sum.cpp'],unit_tests=['unit'],
        integration_tests=['integration'],compiler_evidence=True,native_test_evidence=True)
    assert validate_contract(updated) == updated
    stages = execution_steps(updated)
    assert len(stages) == len(before) + 5  # 3 direct-compiler and 2 bound-runtime controllers.
    assert execution_steps(original) == before
    assert stages[-1]['invocation'][0].startswith('nico-controller:')
    invalid = deepcopy(updated); invalid['configuration']['native_test_evidence'] = True
    with pytest.raises(ValueError): validate_contract(invalid)


def v3_fixture():
    from tests.test_cpp_compiler_evidence import v2_fixture
    from tests.test_assessment_cpp_full_project import encoded
    from nico.assessment_cpp_full_project import execution_steps
    p, n = v2_fixture()
    p['configuration'].update(schema='nico.cpp-cmake-configuration.v3', native_test_evidence='bound-binary-replay-v1')
    for group in ('address', 'undefined'):
        next(r for r in n['steps'] if r['id'] == group + '-discover')['output'] = encoded(discovery(group=group))
    old = {r['id']:r for r in n['steps']}
    for spec in execution_steps(p):
        if spec['id'] in old: continue
        group = spec['native_test_configuration']
        n['steps'].append({'id':spec['id'], 'invocation':spec['invocation'], 'attempted':True,
            'exit_code':0, 'timed_out':False, 'output_truncated':False, 'duration_ms':10,
            'output':encoded(json.dumps(proof(group=group)).encode()), 'artifacts':{}})
    return p, n


def test_new_proof_reaches_existing_receipt_without_rewriting_old_ctest_claims():
    from nico.assessment_worker_receipts import validate_receipt
    from scripts.worker_protocol_fixture import identity
    from tests.test_assessment_cpp_full_project import wrap
    p, n = v3_fixture(); receipt = wrap(n, p)
    _, record, _ = validate_receipt(identity(p), p, receipt['lease_id'], receipt['worker_id'], receipt)
    build = record['cpp_build_evidence']
    assert build['implemented_command_scope_complete'] is True
    assert build['sanitizers']['address']['instrumentation_verified'] is False
    assert build['sanitizers']['address']['isolated_binary_replay_verified'] is True
    assert build['native_test_binary_evidence']['undefined']['runtime_users'] == ['1066:1066','1067:1067']
    assert build['fuzz_executed'] is False and build['full_project_qualified'] is False
    assert record['client_delivery_allowed'] is False


@pytest.mark.parametrize('language', ['en','es-MX'])
def test_bound_binary_results_use_existing_public_exporter(tmp_path, language):
    from scripts.qualify_cpp_full_project_integration import render_result
    from nico.assessment_worker_receipts import validate_receipt
    from nico.assessment_worker_jobs import _digest
    from scripts.worker_protocol_fixture import identity
    from tests.test_assessment_cpp_full_project import wrap
    p, n = v3_fixture(); receipt = wrap(n, p)
    _, record, _ = validate_receipt(identity(p), p, receipt['lease_id'], receipt['worker_id'], receipt)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(receipt))
    rendered = render_result({'canonical_record':record}, tmp_path, language)
    assert rendered['automated_draft'] is True
    text = (tmp_path/('owned-project-'+language+'.md')).read_text()
    assert ('Isolated binary replays' if language=='en' else 'Repeticiones aisladas de binarios') in text
    assert ('Original CTest execution-time binary identity' if language=='en' else 'La identidad del binario durante las ejecuciones originales de CTest') in text
    assert ('controller result=0' if language=='en' else 'resultado del controlador=0') in text


def test_unsupported_native_test_preserves_a_limited_receipt_not_false_success():
    from nico.assessment_cpp_native_tests import run_bound_tests
    raw = discovery(command=['/bin/sh','-c','true'])
    value = run_bound_tests(Commands(), 'owned-container','address',raw,config())
    result = validate_evidence(value, raw, config(), 'address')
    assert result['executed_tests'] == [] and result['tests_passed'] is False
    assert result['error'] == 'worker_native_test_command_unsupported'


@pytest.mark.parametrize('seconds', [1, 20, 31, True, float('inf')])
def test_declared_timeouts_are_not_silently_changed(seconds):
    raw = json.loads(discovery())
    raw['tests'][0]['properties'] = [{'name':'TIMEOUT','value':seconds}]
    with pytest.raises(ValueError): bound_plan(json.dumps(raw).encode(), config(), 'address')


def test_sanitizer_name_substrings_do_not_prove_instrumentation():
    from nico.assessment_cpp_native_tests import sanitizer_symbols
    assert not sanitizer_symbols(b' U unrelated__asan_init\n', 'address')
    assert not sanitizer_symbols(b' U __asan_init\n', 'address')
    assert sanitizer_symbols(b' U __asan_init\n U __asan_report_load4\n', 'address')
    assert sanitizer_symbols(b' U __ubsan_handle_add_overflow_abort\n', 'undefined')
    assert not sanitizer_symbols(b' U fake__ubsan_handle_add_overflow\n', 'undefined')


def test_nested_execution_outcomes_are_retained_in_canonical_evidence():
    commands = Commands(); commands.fail_test = 'unit'
    result = validate_evidence(proof(commands), discovery(), config(), 'address')
    failed = next(row for row in result['native_outcomes'] if row['name'] == 'unit')
    assert failed['exit_code'] == 7 and failed['timed_out'] is False
    assert failed['binary_bound'] is True


@pytest.mark.parametrize('interrupted', [False, True])
def test_actual_profile_routes_bound_test_controller_and_always_cleans_up(tmp_path, interrupted):
    from nico.assessment_cpp_native_tests import SETUP_PROGRAM, SNAPSHOT_PROGRAM, PROBE_PROGRAM, VERIFY_PROGRAM
    from nico.assessment_cpp_compiler_evidence import PROGRAM
    from nico.assessment_cpp_full_project_execution import run_full_project
    from nico.assessment_cpp_full_project import validate_native
    from tests.test_assessment_cpp_full_project import FakeDocker
    p, n = v3_fixture()
    for path in p['targets']: (tmp_path / path).write_bytes(path.encode())
    commands = {group: Commands(group) for group in ('address','undefined')}
    class NativeDocker(FakeDocker):
        def __call__(self, args, **kwargs):
            if SETUP_PROGRAM in args:
                self.calls.append((args,kwargs))
                assert '--user=0:0' in args
                return {'output':b'runtime_snapshot_destination_ready\n','exit_code':0,'timed_out':False,'output_truncated':False}
            if PROGRAM in args:
                self.calls.append((args,kwargs))
                request=json.loads(kwargs['input_bytes'])
                row=next(r for r in n['steps'] if r['id']==request['configuration']+'-compiler-evidence')
                return {'output':base64.b64decode(row['output']),'exit_code':0,'timed_out':False,'output_truncated':False}
            bound = any(program in args for program in (SNAPSHOT_PROGRAM,PROBE_PROGRAM,VERIFY_PROGRAM)) or any(arg.startswith('/work/native-tests/') for arg in args)
            if bound:
                self.calls.append((args,kwargs))
                group = json.loads(kwargs['input_bytes'])['configuration'] if SNAPSHOT_PROGRAM in args else ('undefined' if any('/undefined/' in a for a in args) else 'address')
                result=commands[group](args,data=kwargs.get('input_bytes'))
                if interrupted and args[-1] == 'integration':
                    result.update(exit_code=124,timed_out=True)
                return result
            return super().__call__(args,**kwargs)
    fake=NativeDocker(p,n)
    result=run_full_project(p,tmp_path,checkpoint=lambda:None,timeout_seconds=60,command=fake)
    assert result['native']['cleanup_verified'] is True
    assert fake.calls[-1][0][:3]==['docker','rm','--force']
    runtime_rows=[r for r in result['native']['steps'] if r['id'].endswith('-native-test-evidence')]
    assert runtime_rows[0]['attempted'] is True
    build=validate_native(result['native'],p)['build']
    if interrupted:
        assert runtime_rows[1]['attempted'] is False
        assert build['implemented_command_scope_complete'] is False
    else:
        assert runtime_rows[1]['attempted'] is True
        assert build['native_test_binary_evidence']['address']['tests_passed'] is True
        assert build['native_test_binary_evidence']['undefined']['tests_passed'] is True


def test_nested_redaction_and_numeric_boolean_probes_cannot_gain_credit(monkeypatch):
    from nico import scanner_tool_runners
    p=proof()
    row=p['tests'][0]['execution']
    raw=b'synthetic-sensitive-marker'
    row['output']=base64.b64encode(raw).decode();row['output_sha256']=hashlib.sha256(raw).hexdigest()
    old=scanner_tool_runners.redact_text
    monkeypatch.setattr(scanner_tool_runners,'redact_text',lambda value: old(value).replace('synthetic-sensitive-marker','[redacted]'))
    with pytest.raises(ValueError,match='redaction_required'):validate_evidence(p,discovery(),config(),'address')
    p=proof();row=p['tests'][0]['probe'];raw=json.loads(base64.b64decode(row['output']))
    raw['write_denied']=1;data=json.dumps(raw).encode()
    row['output']=base64.b64encode(data).decode();row['output_sha256']=hashlib.sha256(data).hexdigest()
    assert validate_evidence(p,discovery(),config(),'address')['binary_instrumentation_verified'] is False


def test_failed_inspection_does_not_report_planned_identities_as_execution():
    commands=Commands();commands.nm_empty=True
    result=validate_evidence(proof(commands),discovery(),config(),'address')
    assert result['runtime_users']==[] and result['executed_tests']==[]
    assert result['configured_runtime_users']==['1002:1002','1003:1003']
