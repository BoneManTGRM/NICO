from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml
import pytest

from scripts.security_audit_gate import _trufflehog


ROOT = Path(__file__).resolve().parents[1]
MARKER = 'SYNTHETIC_TEST_CREDENTIAL_DO_NOT_USE_0123456789'


def _capture_step() -> str:
    workflow = yaml.safe_load((ROOT / '.github/workflows/security-audit.yml').read_text())
    return next(step['run'] for step in workflow['jobs']['audit-evidence']['steps']
                if step.get('name') == 'Collect trufflehog git-history evidence')


def _run_capture(tmp_path: Path, raw: str | None = None, exit_code: int = 0):
    tool_dir = tmp_path / 'bin'
    tool_dir.mkdir()
    finding = {'DetectorName': 'RailwayApp', 'Verified': False, 'Raw': MARKER,
               'Redacted': MARKER, 'ExtraData': {'secret': MARKER},
               'SourceMetadata': {'Data': {'Git': {'file': 'nico/config.py',
                    'commit': 'a' * 40, 'line': 12, 'email': MARKER}}}}
    tool = tool_dir / 'trufflehog'
    tool.write_text('#!' + sys.executable + '\nimport json,os,pathlib,sys\n'
        "pathlib.Path(os.environ['CAPTURE_ARGV']).write_text(json.dumps(sys.argv))\n"
        + 'print(' + repr(raw if raw is not None else json.dumps(finding)) + ')\n'
        + 'print(' + repr(MARKER) + ',file=sys.stderr)\n'
        + f'raise SystemExit({exit_code})\n')
    tool.chmod(0o700)
    (tool_dir / 'python').symlink_to(sys.executable)
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    sanitizer = ROOT / 'scripts/sanitize_security_audit_trufflehog.py'
    if sanitizer.exists():
        shutil.copyfile(sanitizer, scripts / sanitizer.name)
    runner_temp = tmp_path / 'private-runner'
    runner_temp.mkdir()
    env = {'PATH': str(tool_dir) + os.pathsep + os.defpath,
           'RUNNER_TEMP': str(runner_temp), 'CAPTURE_ARGV': str(tmp_path / 'argv.json')}
    result = subprocess.run(['bash', '-c', _capture_step()], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads((tmp_path / 'argv.json').read_text())


def test_actual_audit_command_disables_live_credential_verification(tmp_path: Path):
    argv = _run_capture(tmp_path)
    assert '--no-verification' in argv


def test_actual_audit_capture_does_not_publish_secret_or_stderr_body(tmp_path: Path):
    _run_capture(tmp_path)
    for name in ['trufflehog.json', 'trufflehog-summary.json', 'trufflehog.stderr.txt']:
        assert MARKER not in (tmp_path / name).read_text(), name
    findings = [json.loads(line) for line in (tmp_path / 'trufflehog.json').read_text().splitlines()]
    assert len(findings) == 1
    assert findings[0]['RawSHA256'] == hashlib.sha256(MARKER.encode()).hexdigest()
    assert findings[0]['SourceMetadata']['Data']['Git']['file'] == 'nico/config.py'
    assert not list((tmp_path / 'private-runner').rglob('*'))


@pytest.mark.parametrize('raw,exit_code,expected_count,invalid', [
    ('', 0, 0, 0),
    ('{"Raw":"synthetic", "Raw":"duplicate", "DetectorName":"AWS", "Verified":false}', 0, 0, 1),
    ('not-json-' + MARKER, 0, 0, 1),
    ('{"Raw":"synthetic", "DetectorName":"AWS", "Verified":false}', 1, 1, 0),
])
def test_partial_and_empty_actual_capture_remain_truthful(tmp_path, raw, exit_code, expected_count, invalid):
    _run_capture(tmp_path, raw=raw, exit_code=exit_code)
    summary = json.loads((tmp_path / 'trufflehog-summary.json').read_text())
    assert summary['finding_count'] == expected_count
    assert summary['invalid_json_lines'] == invalid
    result = _trufflehog(tmp_path)
    assert result['finding_count'] == expected_count
    assert result['status'] == ('completed' if not raw and exit_code == 0 else 'unavailable')
    assert MARKER not in (tmp_path / 'trufflehog.stderr.txt').read_text()


def test_sanitized_nonfixture_candidate_still_blocks(tmp_path):
    _run_capture(tmp_path)
    result = _trufflehog(tmp_path)
    assert result['status'] == 'completed'
    assert result['finding_count'] == result['blocking'] == 1
    assert result['triage'][0]['disposition'] == 'blocking_unverified_non_fixture'


@pytest.mark.parametrize('mutation', [
    'digest', 'count', 'schema', 'summary_missing', 'raw_field', 'nested_raw',
    'live_verification', 'artifact_missing', 'unexpected_exit',
])
def test_sanitized_capture_rejects_corruption_and_legacy_downgrade(tmp_path, mutation):
    _run_capture(tmp_path)
    path = tmp_path / 'trufflehog-summary.json'
    summary = json.loads(path.read_text())
    if mutation == 'summary_missing':
        summary = {'status': 'completed', 'finding_count': 1}
    elif mutation == 'digest':
        summary['sanitized_artifact_sha256'] = '0' * 64
    elif mutation == 'count':
        summary['finding_count'] = 0
    elif mutation == 'schema':
        summary['schema'] = 'unsupported-v0'
    elif mutation == 'live_verification':
        summary['live_credential_verification'] = True
    elif mutation == 'artifact_missing':
        summary['artifact_present'] = False
    elif mutation == 'unexpected_exit':
        summary['exit_code'] = 1
    else:
        artifact = tmp_path / 'trufflehog.json'
        finding = json.loads(artifact.read_text())
        if mutation == 'raw_field':
            finding['Raw'] = MARKER
        else:
            finding['SourceMetadata']['secret'] = MARKER
        artifact.write_text(json.dumps(finding) + '\n')
        summary['sanitized_artifact_sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    path.write_text(json.dumps(summary))
    result = _trufflehog(tmp_path)
    assert result['status'] == 'unavailable'
    assert result['finding_count'] == 1
    assert result['capture_complete'] is False


@pytest.mark.parametrize('verified,path,raw,approved', [
    (False, 'NICO-Ship-Checkpoint.md', '4b5ff41e-ec40-486c-8461-83475ffa90a9', True),
    (True, 'NICO-Ship-Checkpoint.md', '4b5ff41e-ec40-486c-8461-83475ffa90a9', False),
    (False, 'nico/settings.py', '4b5ff41e-ec40-486c-8461-83475ffa90a9', False),
    (False, 'NICO-Ship-Checkpoint.md', 'other-unreviewed-identifier', False),
])
def test_existing_exact_nonsecret_dispositions_survive_sanitization(tmp_path, verified, path, raw, approved):
    finding = {'Raw': raw, 'DetectorName': 'RailwayApp', 'Verified': verified,
               'SourceMetadata': {'Data': {'Git': {'file': path}}}}
    _run_capture(tmp_path, raw=json.dumps(finding))
    result = _trufflehog(tmp_path)
    assert result['status'] == 'completed'
    assert result['finding_count'] == 1
    assert result['blocking'] == (0 if approved else 1)
    assert result['approved_nonsecret_identifiers'] == (1 if approved else 0)


def test_live_audit_workflow_requires_sanitized_capture_even_for_zero_findings():
    workflow = yaml.safe_load((ROOT / '.github/workflows/security-audit.yml').read_text())
    gate_steps = [step['run'] for step in workflow['jobs']['audit-evidence']['steps']
                  if step.get('name') in {'Build fail-closed scanner manifest',
                                          'Require complete clean security evidence'}]
    assert len(gate_steps) == 2
    assert all('--require-sanitized-trufflehog' in command for command in gate_steps)


def test_sanitized_summary_rejects_unlisted_candidate_body(tmp_path):
    _run_capture(tmp_path, raw='')
    path = tmp_path / 'trufflehog-summary.json'
    summary = json.loads(path.read_text())
    summary['Raw'] = MARKER
    path.write_text(json.dumps(summary))
    assert _trufflehog(tmp_path)['status'] == 'unavailable'


def test_current_empty_capture_rejects_legacy_downgrade_but_retains_offline_history(tmp_path):
    _run_capture(tmp_path, raw='')
    assert _trufflehog(tmp_path, require_sanitized=True)['status'] == 'completed'
    (tmp_path / 'trufflehog-summary.json').write_text(json.dumps({'status': 'completed', 'finding_count': 0}))
    assert _trufflehog(tmp_path, require_sanitized=True)['status'] == 'unavailable'
    assert _trufflehog(tmp_path)['status'] == 'completed'


def test_installed_gate_cli_binds_live_capture_contract(tmp_path):
    _run_capture(tmp_path, raw='')
    command = [sys.executable, str(ROOT / 'scripts/security_audit_gate.py'),
               '--root', str(tmp_path), '--require-sanitized-trufflehog']
    for expected in ['completed', 'unavailable']:
        if expected == 'unavailable':
            (tmp_path / 'trufflehog-summary.json').write_text(json.dumps({'status': 'completed', 'finding_count': 0}))
        result = subprocess.run(command, env={'PATH': os.defpath},
                                capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        manifest = json.loads((tmp_path / 'scanner-worker-artifact.json').read_text())
        assert manifest['tools']['trufflehog']['status'] == expected
        assert manifest['trufflehog_capture_contract'] == 'sanitized_v1'
        assert manifest['human_review_required'] is True
        assert manifest['client_delivery_allowed'] is False
