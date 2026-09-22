"""Controller contract tests. The Docker double never runs target code."""
import hashlib
import ast
import base64
import json
import os
from pathlib import Path
import sys

import pytest

from nico import assessment_worker_container as worker
from scripts.worker_protocol_fixture import contract, receipt


def test_version_and_analysis_use_the_same_trusted_runtime_libraries():
    # The pinned runtime puts libstdc++/libgcc in this non-default loader path.
    # Inspect both native subprocess environments without executing the target
    # or pretending the host provides the qualified Docker boundary.
    tree = ast.parse(worker.PROGRAM)
    assignments = {n.targets[0].id: n.value for n in tree.body
                   if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}
    environments = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == 'subprocess' and node.func.attr in {'run', 'Popen'}:
                value = next((k.value for k in node.keywords if k.arg == 'env'), None)
                assert value is not None, 'every native tool invocation needs the frozen environment'
                if isinstance(value, ast.Name): value = assignments[value.id]
                environments.append(ast.literal_eval(value))
    assert len(environments) == 2
    assert environments[0] == environments[1]
    assert environments[0]['LD_LIBRARY_PATH'] == '/usr/local/lib'


def test_malformed_native_bytes_are_retained_without_successful_decoding():
    bad = b'parser diagnostic: \xff\n'
    result = worker._native_result(b'<broken', b'Checking control.cpp ...\n', bad,
        exit_code=0, timed_out=False, output_truncated=False, duration_ms=1, invocation=worker.invocation())
    assert result['native'] is None
    assert result['native_decoding_failed'] is True
    assert result['execution']['exit_code'] == 0
    assert base64.b64decode(result['raw_streams']['stderr']) == bad
    assert result['streams']['stderr'] == {'sha256': hashlib.sha256(bad).hexdigest(), 'bytes': len(bad)}


def test_valid_native_streams_keep_the_existing_receipt_shape():
    result = worker._native_result(b'<results/>', b'progress\n', b'warning\n',
        exit_code=0, timed_out=False, output_truncated=False, duration_ms=1, invocation=worker.invocation())
    assert result['native_decoding_failed'] is False
    assert result['native'] == {'xml': '<results/>', 'progress': 'progress\nwarning\n', 'exit_code': 0,
        'timed_out': False, 'output_truncated': False, 'duration_ms': 1, 'invocation': worker.invocation()}
    assert base64.b64decode(result['raw_streams']['stdout']) == b'progress\n'


@pytest.fixture
def harness(tmp_path, monkeypatch):
    plan = contract()
    source = tmp_path / 'source'
    (source / 'src').mkdir(parents=True)
    (source / 'src/control.cpp').write_bytes(b'int value() {return 1;}\n')
    events = tmp_path / 'events.jsonl'
    native = receipt()['native']
    result = {'native': native, 'tool_version': plan['tool_version']}
    executable = tmp_path / 'docker'
    executable.write_text(f'''#!{sys.executable}
import json,sys,pathlib,time
events=pathlib.Path({str(events)!r})
args=sys.argv[1:]
with events.open('a') as f: f.write(json.dumps(args)+'\\n')
if args[:2]==['image','inspect']: print(json.dumps([{{'Id':args[2]}}]))
elif args[0]=='create': print('container-id')
elif args[0]=='start':
 data=json.loads(sys.stdin.buffer.read())
 pathlib.Path({str(tmp_path / 'input.json')!r}).write_text(json.dumps(data))
 print({json.dumps(result)!r})
elif args[0]=='rm': print('removed')
else: sys.exit(2)
''')
    executable.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    return plan, source, events, executable


def calls(events):
    return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []


def test_cancellation_after_creation_still_removes_container(harness):
    plan, source, events, _ = harness
    def cancelled():
        if any(c[0] == 'create' for c in calls(events)):
            raise ValueError('lease_lost')
    with pytest.raises(ValueError, match='lease_lost'):
        worker.run_isolated_cppcheck(plan, source, checkpoint=cancelled, timeout_seconds=10)
    assert any(c[:2] == ['rm', '--force'] for c in calls(events))
    assert not any(c[0] == 'start' for c in calls(events))


def test_symlink_root_is_rejected_before_execution(harness, tmp_path):
    plan, source, events, _ = harness
    link = tmp_path / 'alias'; link.symlink_to(source, target_is_directory=True)
    with pytest.raises(ValueError, match='input_type_invalid'):
        worker.run_isolated_cppcheck(plan, link, checkpoint=lambda: None, timeout_seconds=10)
    assert not any(c[0] == 'create' for c in calls(events))


def test_controller_forwards_exact_bytes_and_no_credentials(harness, monkeypatch):
    plan, source, events, _ = harness
    monkeypatch.setenv('NICO_TEST_SECRET', 'synthetic-must-stay-on-controller')
    result = worker.run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert result['native'] == receipt()['native']
    dispatched = json.loads((events.parent / 'input.json').read_text())
    assert dispatched['inputs']['src/control.cpp']['sha256'] == hashlib.sha256((source/'src/control.cpp').read_bytes()).hexdigest()
    create = next(c for c in calls(events) if c[0] == 'create')
    for restriction in ['--network=none', '--read-only', '--user=1000:1000', '--cap-drop=ALL',
                        '--security-opt=no-new-privileges', '--memory=256m', '--pids-limit=32']:
        assert restriction in create
    assert not any(c == '--mount' or c.startswith(('-v', '--volume', '--env', '--privileged')) for c in create)
    assert 'synthetic-must-stay-on-controller' not in events.read_text()
    assert any(c[:2] == ['rm', '--force'] for c in calls(events))


@pytest.mark.parametrize('mutation', ['changed', 'extra', 'link'])
def test_input_substitution_never_reaches_container(harness, mutation):
    plan, source, events, _ = harness
    if mutation == 'changed': (source/'src/control.cpp').write_bytes(b'changed')
    elif mutation == 'extra': (source/'extra.cpp').write_bytes(b'extra')
    else:
        (source/'src/control.cpp').unlink()
        (source/'src/control.cpp').symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        worker.run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert not any(c[0] == 'create' for c in calls(events))


@pytest.mark.parametrize('failure', ['oversized_output', 'deadline', 'cancellation'])
def test_bounded_controller_process_is_reaped_on_failure(tmp_path, failure):
    pidfile = tmp_path / 'pid'
    program = ("import os,pathlib,time,sys; "
               f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); "
               + ("print('x'*200000,flush=True); " if failure == 'oversized_output' else '')
               + "time.sleep(30)")
    def checkpoint():
        if failure == 'cancellation' and pidfile.exists():
            raise ValueError('lease_lost')
    expected = {'oversized_output': 'output_limit', 'deadline': 'timed_out', 'cancellation': 'lease_lost'}[failure]
    with pytest.raises(ValueError, match=expected):
        worker._command([sys.executable, '-c', program], checkpoint=checkpoint,
                        timeout=0.2 if failure == 'deadline' else 2, limit=1024)
    assert pidfile.exists()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_cleanup_failure_cannot_report_success(harness):
    plan, source, events, executable = harness
    executable.write_text(executable.read_text().replace("elif args[0]=='rm': print('removed')", "elif args[0]=='rm': sys.exit(1)"))
    with pytest.raises(ValueError, match='control_failed'):
        worker.run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert any(c[:2] == ['rm', '--force'] for c in calls(events))


def test_input_pipe_rejection_still_removes_container(harness):
    plan, source, events, executable = harness
    executable.write_text(executable.read_text().replace("elif args[0]=='start':", "elif args[0]=='start':\n sys.exit(1)"))
    with pytest.raises(ValueError, match='control_failed|input_rejected'):
        worker.run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert any(c[:2] == ['rm', '--force'] for c in calls(events))
