"""Owned diagnostics only: never start Docker, fetch inputs or read an archive."""
from copy import deepcopy
import json

import pytest

from scripts import fresh_cpp_phase_diagnostic as diagnostic
from nico.assessment_cpp_project_static import PROGRAM, _canonical, _digest
from tests.test_cpp_project_static import execution


def owned(tmp_path, monkeypatch):
    from tests.test_cpp_completed_static_collection import fixture
    request, _, raw, _ = fixture(tmp_path, physical=True)
    monkeypatch.setattr(diagnostic, 'EXPECTED_CONTEXTS', len(request['contexts']))
    value = json.loads(raw)
    value['records'][0]['execution'] = execution(
        b'PRIVATE_COMMAND /private/path SECRET\n'
        b'Tokenizer::createTokens: 1.25s\n'
        b'Tokenizer::simplifyTokens1::simplifyTokenList1::simplifyTemplates: 2e-3s\n')
    return request, value


def observed(value):
    return {'exit_code': 0, 'timed_out': False, 'output_truncated': False,
            'output': _canonical(value)}


def command_args():
    return ['docker', 'exec', '--user=1001:1001', '--interactive', 'owned-box',
            'python3', '-I', '-S', '-c', PROGRAM]


def test_source_bound_summary_keeps_findings_unknowns_and_private_text_out(tmp_path, monkeypatch, capsys):
    request, value = owned(tmp_path, monkeypatch)
    before = deepcopy(value)
    summary = diagnostic.summarize(observed(value), request)
    assert summary['state'] == 'collected'
    assert summary['expected_contexts'] == len(request['contexts'])
    assert summary['source_population_sha256'] == _digest(_canonical(request['targets']))
    assert summary['records'][0]['phases']['token_creation'] == {'state':'available','cpu_microseconds':1250000}
    assert summary['records'][0]['phases']['template_simplification']['cpu_microseconds'] == 2000
    assert summary['records'][0]['phases']['ast_creation'] == {'state':'unavailable'}
    assert not summary['full_project_qualified'] and not summary['assessment_completed']
    diagnostic.emit_summary(summary)
    output = capsys.readouterr().out
    assert all(s not in output for s in ('PRIVATE', 'SECRET', '/private/', 'invocation', 'analysis_file'))
    assert len(output.encode()) < diagnostic.CONSOLE_LIMIT
    assert value == before


@pytest.mark.parametrize('timing', ['NaNs', 'infs', '-1s', '541s', '1e99s', '1.12345678901s', 'secret', '1s SECRET'])
def test_malformed_timing_never_becomes_numeric(timing):
    result = diagnostic.phase_measurements(('Tokenizer::createTokens: '+timing+'\n').encode())
    assert result['token_creation'] == {'state':'invalid'}


def test_duplicate_partial_unknown_and_oversized_phases():
    assert diagnostic.phase_measurements(b'unknown: 2s\n')['token_creation'] == {'state':'unavailable'}
    assert diagnostic.phase_measurements(b'x'*65537)['token_creation'] == {'state':'unavailable'}
    assert diagnostic.phase_measurements(b'Tokenizer::createTokens: 1s\nTokenizer::createTokens: 2s\n')['token_creation'] == {'state':'invalid'}


@pytest.mark.parametrize('fault', ['digest', 'population', 'record_shape', 'native_digest', 'json', 'limit'])
def test_invalid_bound_evidence_stays_unknown(tmp_path, monkeypatch, fault):
    request, value = owned(tmp_path, monkeypatch)
    if fault == 'digest': value['request_sha256'] = '0'*64
    if fault == 'population': value['records'].pop()
    if fault == 'record_shape': value['records'][0]['private'] = 'SECRET'
    if fault == 'native_digest': value['records'][0]['execution']['output_sha256'] = '0'*64
    if fault == 'limit': request['limits']['wall_seconds'] += 1
    envelope = observed(value)
    if fault == 'json': envelope['output'] = b'not-json-SECRET'
    summary = diagnostic.summarize(envelope, request)
    assert summary['state'] == 'invalid' and summary['observed_contexts'] is None
    assert summary['records'] == []


@pytest.mark.parametrize('fault', ['timed_out', 'output_truncated', 'exit_code'])
def test_outer_incomplete_result_is_unavailable(tmp_path, monkeypatch, fault):
    request, value = owned(tmp_path, monkeypatch)
    envelope = observed(value)
    envelope[fault] = 1 if fault == 'exit_code' else True
    summary = diagnostic.summarize(envelope, request)
    assert summary['state'] == 'unavailable' and summary['observed_contexts'] is None


def test_timeout_retains_completed_phases_without_hotspot_claim(tmp_path, monkeypatch):
    request, value = owned(tmp_path, monkeypatch)
    row = value['records'][0]
    row['execution'].update(exit_code=124, timed_out=True)
    summary = diagnostic.summarize(observed(value), request)
    assert summary['records'][0]['timed_out'] is True
    assert summary['records'][0]['exit_code'] == 124
    assert not summary['precise_termination_hotspot_known']
    assert summary['records'][0]['phases']['ast_creation']['state'] == 'unavailable'


def test_row_cap(tmp_path, monkeypatch):
    request, value = owned(tmp_path, monkeypatch)
    monkeypatch.setattr(diagnostic, 'MAX_ROWS', 1)
    summary = diagnostic.summarize(observed(value), request)
    assert len(summary['records']) == 1
    assert summary['omitted_executed_records'] == len(value['records'])-1


@pytest.mark.parametrize('value', [{'state':['SECRET']}, {'private':'SECRET'}, {'records':'SECRET'}, None])
def test_console_rejects_unexpected_shape(value, capsys):
    diagnostic.emit_summary(value)
    output = capsys.readouterr().out
    assert 'SECRET' not in output and json.loads(output)['state'] == 'invalid'


def test_console_rejects_false_looking_numeric_claims_and_unbound_collection(capsys):
    value = diagnostic.empty_summary('unavailable')
    value['full_project_qualified'] = 0
    diagnostic.emit_summary(value)
    assert json.loads(capsys.readouterr().out)['state'] == 'invalid'
    diagnostic.emit_summary(diagnostic.empty_summary('collected'))
    assert json.loads(capsys.readouterr().out)['state'] == 'invalid'


def test_modified_program_only_adds_timing_flag_and_keeps_deadline_environment(monkeypatch):
    calls = []
    prefix = "\ndef _run(argv, stem, deadline, environment):\n    calls.append((argv,stem,deadline,environment)); return 'owned'\ndef run_project_static(): pass\n"
    monkeypatch.setattr(diagnostic, 'PROGRAM', prefix+'\nrun_project_static()\n')
    namespace = {'calls':calls}
    exec(diagnostic.diagnostic_program(), namespace)
    argv = ['/usr/local/bin/cppcheck', '--project=owned']
    env = {'PATH':'owned'}
    assert namespace['_run'](argv, 'stem', 123, env) == 'owned'
    assert calls[-1] == ([*argv,'--showtime=file'], 'stem', 123, env)
    assert argv == ['/usr/local/bin/cppcheck', '--project=owned']
    namespace['_run'](['/usr/local/bin/cppcheck', '--version'], 'version', 10, env)
    assert calls[-1][0] == ['/usr/local/bin/cppcheck', '--version']


@pytest.mark.parametrize('failure', [False, True])
def test_diagnostic_unwinds_cleanup_and_never_returns_raw_evidence(tmp_path, monkeypatch, failure):
    request, value = owned(tmp_path, monkeypatch)
    calls, summaries = [], []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[-1] == diagnostic.diagnostic_program():
            if failure: raise ValueError('SECRET')
            return observed(value)
        return 'cleanup'
    wrapped = diagnostic.diagnostic_command(run, summaries.append)
    kwargs = {'input_bytes':_canonical(request), 'timeout':550, 'limit':diagnostic.STREAM_LIMIT,
              'checkpoint':lambda:None, 'native_exit':True}
    with pytest.raises(diagnostic.DiagnosticFinished):
        try:
            wrapped(command_args(), **kwargs)
            pytest.fail('must not return diagnostic bytes to acceptance')
        finally:
            assert wrapped(['docker','rm','--force','owned-box']) == 'cleanup'
    assert calls[0][1] == kwargs
    assert summaries[0]['state'] == ('preparation_or_execution_failed' if failure else 'collected')


def test_emit_failure_still_stops_before_acceptance(tmp_path, monkeypatch):
    request, value = owned(tmp_path, monkeypatch)
    def emit(_): raise OSError('SECRET')
    wrapped = diagnostic.diagnostic_command(lambda *a, **k:observed(value), emit)
    with pytest.raises(diagnostic.DiagnosticFinished):
        wrapped(command_args(), input_bytes=_canonical(request))


def test_default_population_and_program_preserve_production_contract():
    assert diagnostic.EXPECTED_CONTEXTS == 577
    assert diagnostic.PROGRAM == PROGRAM
    changed = diagnostic.diagnostic_program()
    assert changed.startswith(PROGRAM[:-len('\nrun_project_static()\n')])
    assert 'ThreadPoolExecutor' not in changed[len(PROGRAM):]
    assert 'report-progress' not in changed


def test_cli_rejects_reused_output_without_execution(tmp_path, monkeypatch, capsys):
    import scripts.qualify_cpp_project_configuration as qualification
    monkeypatch.setattr(qualification, 'qualify_configuration_checkout', lambda *a, **k:pytest.fail('executed'))
    assert diagnostic.main(['--image','sha256:'+'a'*64,'--qualification-source',str(tmp_path),
        '--unit-test-data',str(tmp_path),'--producer-source-sha','b'*40,'--output',str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)['state'] == 'preparation_or_execution_failed'


def test_cli_has_no_archive_or_resume_intake(capsys):
    with pytest.raises(SystemExit) as exc:
        diagnostic.main(['--archive','restricted.zip'])
    assert exc.value.code == 2


@pytest.mark.parametrize('malformed', [False, True])
def test_real_static_controller_cleans_up_and_skips_validation(tmp_path, monkeypatch, malformed):
    from nico import assessment_cpp_project_static as static
    from tests.test_cpp_project_static_stage import stage_inputs, StaticDocker
    from scripts.qualify_cpp_project_configuration import persist_project_artifact
    bound = tmp_path/'bound'; bound.mkdir()
    request, value = owned(bound, monkeypatch)
    inputs = tmp_path/'inputs'; inputs.mkdir()
    source, targets, database, snapshot, compiler_raw = stage_inputs(inputs)
    # This real legacy stage request is deliberately rejected: fresh diagnostics
    # require the bound physical-header v4 request, never a weaker intake.
    docker = StaticDocker(targets)
    calls, saved, summaries = [], [], []
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[-1] == diagnostic.diagnostic_program():
            return observed(value)
        return docker(argv, **kwargs)
    wrapped = diagnostic.diagnostic_command(run, summaries.append)
    def command(argv, **kwargs):
        if malformed and argv[-1] == PROGRAM:
            kwargs['input_bytes'] = b'broken'
        return wrapped(argv, **kwargs)
    output = tmp_path/'evidence'; output.mkdir()
    with pytest.raises(diagnostic.DiagnosticFinished):
        static.run_project_static_stage(source, targets, 'sha256:'+'a'*64, database,
            snapshot, compiler_raw, command=command, retain=lambda r:saved.append(deepcopy(r)),
            retain_artifact=lambda key,raw:persist_project_artifact(output,key,raw))
    assert any(argv[:3] == ['docker','rm','--force'] for argv in calls)
    assert saved[-1]['cleanup_verified'] is True
    assert saved[-1]['complete'] is False
    assert not saved[-1].get('analysis')
    assert summaries[0]['state'] == 'preparation_or_execution_failed'


@pytest.mark.parametrize('primary_only', [False, True])
def test_real_qualification_preparation_passes_no_runtime_plan_only_in_diagnostic(tmp_path, monkeypatch, primary_only):
    from types import SimpleNamespace
    from scripts import qualify_cpp_project_configuration as qualification
    from nico import assessment_cpp_configuration_probe as probe
    from nico import assessment_cpp_runtime_scope as runtime
    paths = {}
    for key, value in [('qualification_manifest', {'project_options':{}}),
                       ('baseline_execution_contract', {}), ('runtime_scope_contract', {})]:
        paths[key] = tmp_path/key
        paths[key].write_text(json.dumps(value))
    args = SimpleNamespace(**paths, output=tmp_path/'out', qualification_source=tmp_path,
                           image='sha256:'+'a'*64, unit_test_data=None)
    monkeypatch.setattr(qualification, 'freeze_configuration_checkout',
        lambda *a:{'targets':{'CMakeLists.txt':'a'*64}})
    plan = {'unit_test_data':None, 'owned_runtime_plan':True}
    monkeypatch.setattr(runtime, 'capture_runtime_interfaces', lambda *a:{})
    monkeypatch.setattr(runtime, 'derive_runtime_plan_from_interfaces', lambda *a:plan)
    def prepared(*a, **kwargs):
        assert kwargs['runtime_plan'] == (None if primary_only else plan)
        raise diagnostic.DiagnosticFinished()
    monkeypatch.setattr(probe, 'probe_project_configuration', prepared)
    with pytest.raises(diagnostic.DiagnosticFinished):
        qualification.qualify_configuration_checkout(args, command=lambda *a, **k:None,
            diagnostic_primary_only=primary_only)
    assert not (args.output/'collection-acceptance.json').exists()


def test_incomplete_final_timing_line_is_not_a_measurement():
    assert diagnostic.phase_measurements(b'Tokenizer::createTokens: 1s')['token_creation'] == {'state':'invalid'}


def test_fresh_workflow_has_no_archive_intake_and_preserves_owned_provisioning():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[1]
    fresh = yaml.safe_load((root/'.github/workflows/native-timeout-diagnostic.yml').read_text())
    production = yaml.safe_load((root/'.github/workflows/cpp-full-project-integration.yml').read_text())
    job = fresh['jobs']['isolated-diagnostic']
    assert fresh['name'] == 'Isolated Native Timeout Diagnostic'
    assert fresh['permissions'] == {'contents':'read', 'actions':'read'}
    assert fresh['concurrency'] == {'group':'cpp-full-project-integration-refs/pull/1722/merge',
                                  'queue':'max', 'cancel-in-progress':False}
    assert 'github.run_attempt == 1' in job['if']
    assert "head.ref == 'diagnostic/current-primary-38380333159'" in job['if']
    assert job['timeout-minutes'] == 55
    actual = {step.get('name'):step for step in job['steps'] if step.get('name')}
    assert 'if' not in actual['Verify diagnostic contracts']
    assert 'steps.need' not in json.dumps(fresh)
    for step in production['jobs']['owned-project-integration']['steps']:
        if step.get('name') in ('Provision exact tools without assessed source or runtime network',
            'Verify owned physical-header grammar on the same image',
            'Verify standalone worker compatibility on the same full-project image',
            'Exercise owned project through worker lease, receipt and report',
            'Verify immutable generated-source snapshots on owned positive and negative controls',
            'Acquire pinned public qualification source without execution'):
            assert actual[step['name']] == step
    text = json.dumps(fresh)
    assert all(term not in text for term in ('download-artifact','upload-artifact','retained-timeout',
                                              '--archive','gh api','stage_runtime_binding'))
    assert 'scripts.fresh_cpp_phase_diagnostic' in text
    assert 'bb5296576e8f1a9fc11c19d9a25ba02ed4547e24' in text


def test_fresh_workflow_owned_controls_have_complete_ephemeral_database_wiring():
    from pathlib import Path
    import yaml
    root = Path(__file__).resolve().parents[1]
    fresh = yaml.safe_load((root/'.github/workflows/native-timeout-diagnostic.yml').read_text())
    production = yaml.safe_load((root/'.github/workflows/cpp-full-project-integration.yml').read_text())
    job = fresh['jobs']['isolated-diagnostic']
    owned = production['jobs']['owned-project-integration']
    assert job['services'] == owned['services']
    assert job['env'] == owned['env'] == {
        'NICO_TEST_DATABASE_URL': 'postgresql://nico:nico@127.0.0.1:5432/nico'}
    service = job['services']['postgres']
    assert service['image'] == 'postgres:16-alpine'
    assert service['ports'] == ['5432:5432']
    assert service['env'] == {'POSTGRES_USER': 'nico', 'POSTGRES_PASSWORD': 'nico', 'POSTGRES_DB': 'nico'}
    assert service['options'] == ('--health-cmd="pg_isready -U nico -d nico" '
        '--health-interval=5s --health-timeout=5s --health-retries=12')
    assert 'volumes' not in service and 'secrets.' not in json.dumps(job)
    controls = [step for step in job['steps'] if any(command in step.get('run', '') for command in (
        'scripts.qualify_cppcheck_worker_control', 'scripts.qualify_cpp_full_project_integration'))]
    assert len(controls) == 2
    for step in controls:
        assert not step.get('continue-on-error') and 'if' not in step
        assert 'NICO_TEST_DATABASE_URL' not in step.get('env', {})
        assert '||' not in step['run']
