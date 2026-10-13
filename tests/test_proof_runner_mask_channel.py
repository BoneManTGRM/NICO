"""Synthetic-only runner pipe versus retained-output topology regressions."""
import json
import hashlib
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import time

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SECRET = 'synthetic-mask-channel-secret'
CHANNEL_SETUP = ('# Separate runner mask commands from retained proof output.\n'
                 'exec 9>&1\nexport NICO_PROOF_MASK_FD=9\n')


def run_shell(tmp_path, script, **extra):
    """Runner commands go to a pipe, separately from captured ordinary output."""
    read_fd, write_fd = os.pipe()
    env = {**os.environ, 'GITHUB_ACTIONS': 'true', 'PYTHONPATH': str(ROOT),
           'PROOF_PYTHON': sys.executable, **extra}
    env.pop('NICO_PROOF_MASK_FD', None)
    try:
        process = subprocess.Popen(['bash', '-c', script], cwd=tmp_path, env=env,
                                   stdout=write_fd, stderr=subprocess.PIPE, start_new_session=True)
        try:
            _, stderr = process.communicate(timeout=20)
            result = subprocess.CompletedProcess(process.args, process.returncode, stderr=stderr)
        finally:
            # Bound the whole synthetic process group, including a stalled X server.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
    finally:
        os.close(write_fd)
    with os.fdopen(read_fd, 'rb') as pipe:
        os.set_blocking(read_fd, False)
        deadline = time.monotonic() + 5
        chunks = []
        while True:
            remaining = deadline - time.monotonic()
            assert remaining > 0 and select.select([pipe], [], [], remaining)[0], 'runner command pipe did not close'
            chunk = os.read(read_fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        commands = b''.join(chunks)
    return result, commands


@pytest.mark.parametrize('step_id,prefix', [('spanish_proof', 'spanish-comprehensive'),
                                          ('exclusion_proof', 'spanish-comprehensive-exclusion')])
@pytest.mark.parametrize('proof_exit,tee_exit', [(0, 0), (1, 0), (0, 9)])
@pytest.mark.parametrize('wrapper', ['modeled_fd3_close', 'installed_xvfb_run'])
def test_actual_spanish_tee_blocks_keep_mask_commands_out_of_artifacts(tmp_path, step_id, prefix, proof_exit, tee_exit, wrapper, record_property):
    xvfb = shutil.which('xvfb-run')
    if wrapper == 'installed_xvfb_run':
        if not xvfb:
            pytest.skip('xvfb-run is not installed; real wrapper boundary unverified')
        record_property('xvfb_run_path', xvfb)
        record_property('xvfb_run_sha256', hashlib.sha256(Path(xvfb).read_bytes()).hexdigest())
    workflow = yaml.safe_load((ROOT/'.github/workflows/spanish-comprehensive-production-proof.yml').read_text())
    step = next(s for job in workflow['jobs'].values() for s in job.get('steps', []) if s.get('id') == step_id)
    body = step['run']
    assert body.startswith(CHANNEL_SETUP)
    stub = tmp_path/'proof.py'
    stub.write_text('from scripts.github_actions_nico_proof_auth_v1 import _register_proof_secret, redact_proof_secrets\n'
                    'from pathlib import Path\nimport json\n'
                    f'_register_proof_secret({SECRET!r})\n'
                    f'value=json.dumps(redact_proof_secrets({{"error": {SECRET!r}, "status": "failed"}}))\n'
                    'Path("failure.json").write_text(value)\nprint(value)\n'
                    f'raise SystemExit({proof_exit})\n')
    # Keep the workflow's real tee blocks, PIPESTATUS handling and recovery markers.
    # The real-wrapper variant invokes the installed executable unchanged with a
    # synthetic client, not authentication or a browser. The modeled variant is
    # explicitly weaker evidence, but exercises the known FD3-close regression.
    client = ('"$PROOF_XVFB_RUN" -a "$PROOF_PYTHON" "$PROOF_STUB"'
              if wrapper == 'installed_xvfb_run' else '"$PROOF_PYTHON" "$PROOF_STUB" 3>&-')
    plumbing = ('exec > ordinary.stdout 2> ordinary.stderr\n'
                'xvfb-run() { '+client+'; }\n')
    if tee_exit:
        plumbing += f'tee() {{ /usr/bin/tee "$@"; return {tee_exit}; }}\n'
    script = CHANNEL_SETUP + plumbing + body[len(CHANNEL_SETUP):]
    result, commands = run_shell(tmp_path, script, PROOF_XVFB_RUN=xvfb or '', PROOF_STUB=str(stub), RELEASE_SHA='a'*40,
        SOURCE_RUN_ID='123', SOURCE_RUN_ATTEMPT='1', NICO_PRODUCTION_FRONTEND_URL='https://synthetic.invalid',
        NICO_PRODUCTION_SMOKE_REPOSITORY='synthetic/fixture')
    assert result.returncode == (tee_exit or proof_exit)
    assert commands == f'::add-mask::{SECRET}\n'.encode()
    assert SECRET.encode() not in result.stderr
    for file in [tmp_path/'ordinary.stdout', tmp_path/'ordinary.stderr', tmp_path/'failure.json',
                 tmp_path/f'audit-results/{prefix}-source-proof.log']:
        assert SECRET not in file.read_text()
        assert '::add-mask::' not in file.read_text()
    log = (tmp_path/f'audit-results/{prefix}-source-proof.log').read_text()
    assert 'RELEASE_SHA: '+('a'*40) in log
    assert f'Process completed with exit code {proof_exit}' in log
    if not tee_exit:
        assert (tmp_path/f'audit-results/{prefix}-source-proof.exit-code').read_text().strip() == str(proof_exit)


@pytest.mark.parametrize('mode', ['absent', 'closed', 'file'])
def test_unavailable_channel_fails_without_stdout_stderr_or_file_secrets(tmp_path, mode):
    code = ('from scripts.github_actions_nico_proof_auth_v1 import _register_proof_secret\n'
            'import os\n_register_proof_secret(os.environ["SYNTHETIC_SECRET"])\n')
    (tmp_path/'probe.py').write_text(code)
    setup = {'absent': '', 'closed': 'export NICO_PROOF_MASK_FD=9; exec 9>&-\n',
             'file': 'export NICO_PROOF_MASK_FD=9; exec 9>unsafe-channel.log\n'}[mode]
    result, commands = run_shell(tmp_path, setup+'"$PROOF_PYTHON" probe.py >ordinary.stdout 2>ordinary.stderr\n', SYNTHETIC_SECRET=SECRET)
    assert result.returncode != 0
    assert commands == b''
    for file in tmp_path.glob('*.stdout'):
        assert SECRET not in file.read_text()
    stderr = (tmp_path/'ordinary.stderr').read_text()
    assert SECRET not in stderr
    assert 'production_proof_runner_mask_channel_unavailable' in stderr
    if mode == 'file':
        assert (tmp_path/'unsafe-channel.log').read_bytes() == b''


@pytest.mark.parametrize('preserve_fd', [False, True])
def test_subprocess_capture_requires_explicit_runner_descriptor_inheritance(tmp_path, preserve_fd):
    child = 'from scripts.github_actions_nico_proof_auth_v1 import _register_proof_secret; import os; _register_proof_secret(os.environ["SYNTHETIC_SECRET"])'
    wrapper = ('import subprocess,sys,json\n'
               f'r=subprocess.run([sys.executable,"-c",{child!r}],capture_output=True,pass_fds={((9,) if preserve_fd else ())!r})\n'
               'sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);raise SystemExit(r.returncode)\n')
    (tmp_path/'wrapper.py').write_text(wrapper)
    result, commands = run_shell(tmp_path, CHANNEL_SETUP+'"$PROOF_PYTHON" wrapper.py >ordinary.stdout 2>ordinary.stderr\n', SYNTHETIC_SECRET=SECRET)
    assert (result.returncode == 0) is preserve_fd
    assert commands == (f'::add-mask::{SECRET}\n'.encode() if preserve_fd else b'')
    for name in ['ordinary.stdout', 'ordinary.stderr']:
        assert SECRET not in (tmp_path/name).read_text()


@pytest.mark.parametrize('first', ['scripts.github_actions_nico_proof_auth_v1', 'github_actions_nico_proof_auth_v1'])
def test_package_and_bare_imports_share_recovery_artifact_redaction(tmp_path, first):
    code = '''import sys,importlib,types,json
from pathlib import Path
sys.path.insert(0, str(Path.cwd()/'scripts'))
sync=types.ModuleType('playwright.sync_api')
sync.Browser=sync.Page=sync.Locator=object
sync.sync_playwright=lambda:None
sys.modules['playwright']=types.ModuleType('playwright')
sys.modules['playwright.sync_api']=sync
importlib.import_module(sys.argv[1])
from scripts import comprehensive_fresh_browser_matrix_v1 as matrix
import scripts.github_actions_nico_proof_auth_v1 as package
import github_actions_nico_proof_auth_v1 as bare
import mobile_restart_live_acceptance_v1 as recovery
assert package is bare
package._register_proof_secret('synthetic-import-private')
recovery._write(Path(sys.argv[2]), {'cells':[{'error':'Timeout: synthetic-import-private'}]})
assert 'synthetic-import-private' not in Path(sys.argv[2]).read_text()
assert '[REDACTED]' in Path(sys.argv[2]).read_text()
assert matrix.acquire_production_proof_session is bare.acquire_production_proof_session
'''
    result = subprocess.run([sys.executable, '-c', code, first, str(tmp_path/'failure.json')],
        cwd=ROOT, env={**os.environ, 'GITHUB_ACTIONS': 'false'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_every_shipped_authentication_run_sets_channel_before_capture():
    callers = ['spanish_comprehensive_authenticated_live_acceptance_v1',
        'spanish_comprehensive_authenticated_existing_run_recovery_v1', 'mobile_restart_authenticated_live_acceptance_v1',
        'ios_webkit_authenticated_live_acceptance_v1', 'completed_run_authenticated_two_pass_acceptance_v1',
        'comprehensive_fresh_browser_matrix_v1', 'production_blocked_run_diagnostic_v1']
    found = set(); count = 0
    for path in (ROOT/'.github/workflows').glob('*.yml'):
        data = yaml.safe_load(path.read_text())
        for job in (data.get('jobs') or {}).values():
            for step in job.get('steps', []):
                run = step.get('run', '')
                matches = {name for name in callers if any(
                    line.strip().startswith(('python scripts/'+name+'.py', 'xvfb-run -a python scripts/'+name+'.py'))
                    and '--help' not in line for line in run.splitlines())}
                inline = 'session, retained = acquire_production_proof_session(origin)' in run
                if matches or inline:
                    assert run.startswith(CHANNEL_SETUP), (path, step.get('name'))
                    found.update(matches);count += 1
    assert found == set(callers)
    assert count == 10
