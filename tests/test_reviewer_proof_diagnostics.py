from pathlib import Path
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import reviewer_proof_diagnostics as diagnostic
import reviewer_proof_environment as build_env
import reviewer_binding_webkit_proof as proof


@pytest.mark.parametrize('error', [ImportError('secret'), OSError('secret'),
    AssertionError('secret'), RuntimeError('secret'), KeyboardInterrupt(),
    SystemExit(7), subprocess.TimeoutExpired(['secret'], 1),
    subprocess.CalledProcessError(9, ['secret'], output='secret', stderr='secret')])
def test_early_failure_keeps_original_and_only_allowlisted_metadata(tmp_path, error):
    def fail():
        diagnostic.set_stage('server-start')
        raise error
    with pytest.raises(type(error)) as caught:
        diagnostic.run_with_diagnostics(tmp_path, 'proof', fail)
    assert caught.value is error
    raw = (tmp_path / 'reviewer-binding-proof-diagnostic.json').read_bytes()
    value = json.loads(raw)
    assert b'secret' not in raw and len(raw) <= diagnostic.DIAGNOSTIC_BYTES
    assert value['stage'] == 'server-start' and value['outcome'] == 'failed'
    assert value['visual_qualification'] is False
    assert set(value) == {'schema', 'kind', 'stage', 'outcome', 'error_category',
                          'exit_code', 'exit_code_omitted', 'visual_qualification'}


def test_success_preserves_return_without_claiming_visual_qualification(tmp_path):
    assert diagnostic.run_with_diagnostics(tmp_path, 'build', lambda: 42) == 42
    value = json.loads((tmp_path / 'reviewer-binding-build-diagnostic.json').read_text())
    assert value['outcome'] == 'returned' and value['error_category'] is None
    assert value['visual_qualification'] is False


@pytest.mark.parametrize('original', [RuntimeError('original'), SystemExit(11), KeyboardInterrupt()])
def test_diagnostic_failure_cannot_mask_original(tmp_path, monkeypatch, original):
    def unavailable(*args):
        raise OSError('secret diagnostic failure')
    monkeypatch.setattr(diagnostic, 'write_record', unavailable)
    monkeypatch.setattr('builtins.print', unavailable)
    def fail():
        raise original
    with pytest.raises(type(original)) as caught:
        diagnostic.run_with_diagnostics(tmp_path, 'proof', fail)
    assert caught.value is original


def test_diagnostic_failure_on_success_is_not_silenced(tmp_path, monkeypatch):
    def unavailable(*args):
        raise OSError('unavailable')
    monkeypatch.setattr(diagnostic, 'write_record', unavailable)
    with pytest.raises(OSError):
        diagnostic.run_with_diagnostics(tmp_path, 'proof', lambda: None)


def test_oversized_untrusted_fields_are_omitted_not_copied(tmp_path):
    diagnostic.set_stage('secret' * 10000)
    error = subprocess.CalledProcessError(10 ** 10000, ['secret' * 10000])
    diagnostic.write_record(tmp_path, 'build', error)
    raw = (tmp_path / 'reviewer-binding-build-diagnostic.json').read_bytes()
    value = json.loads(raw)
    assert value['stage'] == 'unknown' and value['exit_code'] is None
    assert value['exit_code_omitted'] is True and b'secret' not in raw
    assert len(raw) <= diagnostic.DIAGNOSTIC_BYTES


def test_budget_rejects_instead_of_truncating_json(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostic, 'DIAGNOSTIC_BYTES', 10)
    with pytest.raises(RuntimeError, match='budget'):
        diagnostic.write_record(tmp_path, 'proof', None)
    assert not list(tmp_path.iterdir())


def test_stale_or_symlink_diagnostic_is_not_overwritten(tmp_path):
    target = tmp_path / 'retained'; target.write_text('unchanged')
    (tmp_path / 'reviewer-binding-proof-diagnostic.json').symlink_to(target)
    with pytest.raises(FileExistsError):
        diagnostic.run_with_diagnostics(tmp_path, 'proof', lambda: None)
    assert target.read_text() == 'unchanged'


@pytest.mark.parametrize('step', ['environment', 'npm-install', 'frontend-build'])
def test_real_build_entry_stages_preserve_failure(tmp_path, monkeypatch, step):
    (tmp_path / 'apps/web').mkdir(parents=True)
    if step == 'environment':
        (tmp_path / 'apps/web/.env.local').write_text('secret')
    def fail(command, **kwargs):
        if command[0] == ('npm' if step == 'npm-install' else 'node'):
            raise subprocess.CalledProcessError(5, command)
    monkeypatch.setattr(build_env.subprocess, 'run', fail)
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        diagnostic.run_with_diagnostics(tmp_path, 'build', lambda: build_env.build(tmp_path))
    value = json.loads((tmp_path / 'reviewer-binding-build-diagnostic.json').read_text())
    assert value['stage'] == step and value['outcome'] == 'failed'


def test_total_upload_budget_and_workflow_remain_bounded():
    import yaml
    assert proof.TOTAL_ARTIFACT_BYTES + 2 * diagnostic.DIAGNOSTIC_BYTES == 20 * 1024 * 1024
    workflow = yaml.safe_load((ROOT / '.github/workflows/ios-webkit-paint-proof.yml').read_text())
    job = workflow['jobs']['contract']
    step = next(s for s in job['steps'] if s['name'] == 'Retain synthetic reviewer layout evidence')
    assert step['with']['path'] == '${{ steps.reviewer_artifact.outputs.upload_path }}'
    assert "steps.reviewer_artifact.outcome == 'success'" in step['if']
    staging = next(s for s in job['steps'] if s.get('id') == 'reviewer_artifact')
    assert staging['if'] == "always() && github.event_name == 'pull_request'"
    assert staging['timeout-minutes'] == 1 and 'reviewer_proof_diagnostics.py' in staging['run']
    assert step['with']['retention-days'] == 1 and step['with']['if-no-files-found'] == 'error'
    assert step['timeout-minutes'] == 2 and job['timeout-minutes'] == 25


@pytest.mark.parametrize('failure,stage', [('identity', 'proof-setup'),
    ('import', 'playwright-import'), ('popen', 'server-start')])
def test_real_proof_early_failure_is_recorded_without_browser(tmp_path, monkeypatch, failure, stage):
    import builtins
    from types import ModuleType
    sha = 'a' * 40
    monkeypatch.setattr(sys, 'argv', ['proof', '--expected-sha', 'b' * 40 if failure == 'identity' else sha,
        '--reviewed-head', sha, '--output', str(tmp_path / 'screenshots')])
    monkeypatch.setattr(proof.subprocess, 'check_output',
        lambda command, **kwargs: '' if 'cat-file' in command else sha + '\n')
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if name == 'playwright.sync_api':
            if failure == 'import':
                raise ImportError('synthetic secret')
            module = ModuleType(name)
            def forbidden():
                raise AssertionError('browser must not launch')
            module.sync_playwright = forbidden
            return module
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded_import)
    def unavailable(*args, **kwargs):
        raise OSError('synthetic secret')
    monkeypatch.setattr(proof.subprocess, 'Popen', unavailable)
    with pytest.raises((AssertionError, ImportError, OSError)):
        diagnostic.run_with_diagnostics(tmp_path, 'proof', proof.main)
    value = json.loads((tmp_path / 'reviewer-binding-proof-diagnostic.json').read_text())
    assert value['stage'] == stage and value['outcome'] == 'failed'
    assert not (tmp_path / 'screenshots/publish').exists()


@pytest.mark.parametrize('unsafe', ['oversized', 'symlink', 'directory', 'fifo', 'hardlink'])
def test_stale_unsafe_diagnostic_never_becomes_uploadable(tmp_path, unsafe):
    import os
    path = tmp_path / 'reviewer-binding-build-diagnostic.json'
    target = tmp_path / 'private'; target.write_text('private-secret')
    if unsafe == 'oversized':
        with path.open('wb') as stream:
            stream.truncate(20 * 1024 * 1024 + 1)
    elif unsafe == 'symlink': path.symlink_to(target)
    elif unsafe == 'directory': path.mkdir()
    elif unsafe == 'fifo': os.mkfifo(path)
    elif unsafe == 'hardlink': os.link(target, path)
    original = RuntimeError('original-secret')
    def fail(): raise original
    with pytest.raises(RuntimeError) as caught:
        diagnostic.run_with_diagnostics(tmp_path, 'build', fail)
    assert caught.value is original
    with pytest.raises((ValueError, OSError)):
        diagnostic.stage_upload(tmp_path)
    assert target.read_text() == 'private-secret'
    assert not list(tmp_path.glob('reviewer-binding-validated-*'))


@pytest.mark.parametrize('change', [
    {'extra': 'secret'}, {'stage': 'secret'}, {'error_category': 'secret'},
    {'visual_qualification': True}, {'exit_code': True}, {'exit_code': 256},
    {'exit_code_omitted': 'secret'}, {'schema': 'stale'}, {'kind': 'proof'},
    {'outcome': 'passed'}, {'outcome': 'returned', 'error_category': 'os'},
])
def test_malformed_diagnostic_schema_rejected(tmp_path, change):
    diagnostic.set_stage('environment')
    value = diagnostic.record('build', RuntimeError('secret'))
    value.update(change)
    (tmp_path / 'reviewer-binding-build-diagnostic.json').write_text(json.dumps(value))
    with pytest.raises(ValueError): diagnostic.stage_upload(tmp_path)
    assert not list(tmp_path.glob('reviewer-binding-validated-*'))


@pytest.mark.parametrize('payload', [b'not json', b'[]', b'{"kind":"build","kind":"proof"}', b'\xff'])
def test_invalid_encoding_or_duplicate_json_is_rejected(tmp_path, payload):
    (tmp_path / 'reviewer-binding-build-diagnostic.json').write_bytes(payload)
    with pytest.raises((ValueError, UnicodeError)): diagnostic.stage_upload(tmp_path)
    assert not list(tmp_path.glob('reviewer-binding-validated-*'))


def test_aggregate_upload_cap_includes_diagnostics_and_proof(tmp_path, monkeypatch):
    diagnostic.run_with_diagnostics(tmp_path, 'build', lambda: None)
    diagnostic.run_with_diagnostics(tmp_path, 'proof', lambda: None)
    publish = tmp_path / 'reviewer-binding-webkit-proof/publish'; publish.mkdir(parents=True)
    (publish / 'server.log').write_bytes(b'x' * 100)
    (publish / 'manifest.json').write_bytes(b'{}')
    total = sum(p.stat().st_size for p in tmp_path.glob('*diagnostic.json')) + 102
    monkeypatch.setattr(diagnostic, 'UPLOAD_BYTES', total - 1)
    with pytest.raises(ValueError): diagnostic.stage_upload(tmp_path)
    assert not list(tmp_path.glob('reviewer-binding-validated-*'))
    monkeypatch.setattr(diagnostic, 'UPLOAD_BYTES', total)
    destination = diagnostic.stage_upload(tmp_path)
    assert sum(p.stat().st_size for p in destination.iterdir()) == total
    assert len(list(destination.iterdir())) == 4
    assert all(p.is_file() and not p.is_symlink() for p in destination.iterdir())


@pytest.mark.parametrize('part', ['root', 'publish', 'file'])
def test_proof_symlinks_cannot_enter_upload(tmp_path, part):
    target = tmp_path / 'private'; target.mkdir(); (target / 'server.log').write_text('secret')
    proof_dir = tmp_path / 'reviewer-binding-webkit-proof'
    if part == 'root': proof_dir.symlink_to(target, target_is_directory=True)
    else:
        proof_dir.mkdir()
        if part == 'publish': (proof_dir / 'publish').symlink_to(target, target_is_directory=True)
        else:
            (proof_dir / 'publish').mkdir()
            (proof_dir / 'publish/server.log').symlink_to(target / 'server.log')
    with pytest.raises(OSError): diagnostic.stage_upload(tmp_path)
    assert not list(tmp_path.glob('reviewer-binding-validated-*'))


def test_valid_failure_stages_only_sanitized_diagnostic(tmp_path):
    secret = 'TOKEN=private-secret https://private.invalid'
    def fail(): raise RuntimeError(secret)
    with pytest.raises(RuntimeError): diagnostic.run_with_diagnostics(tmp_path, 'build', fail)
    (tmp_path / 'unrelated-secret').write_text(secret)
    destination = diagnostic.stage_upload(tmp_path)
    files = list(destination.iterdir())
    assert [p.name for p in files] == ['reviewer-binding-build-diagnostic.json']
    assert secret.encode() not in files[0].read_bytes()
    value = json.loads(files[0].read_bytes())
    assert value['outcome'] == 'failed' and value['visual_qualification'] is False


def test_stage_write_failure_leaves_no_upload_directory(tmp_path, monkeypatch):
    diagnostic.run_with_diagnostics(tmp_path, 'build', lambda: None)
    original = Path.open
    def fail(path, *args, **kwargs):
        if path.parent.name.startswith('reviewer-binding-validated-'):
            raise OSError('synthetic write failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', fail)
    with pytest.raises(OSError): diagnostic.stage_upload(tmp_path)
    assert not list(tmp_path.glob('reviewer-binding-validated-*'))
