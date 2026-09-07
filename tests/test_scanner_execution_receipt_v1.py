from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nico.scanner_execution_receipt_v1 import (
    input_snapshot, invocation_receipt, native_coverage_observation,
    provenance_summary, receipt_summary, safe_argv,
)
from nico.scanner_evidence_pipeline_v1 import _raw_blob, _run, _run_npm_audit, _run_osv, _tool_payload
from nico.scanner_tool_runners import ScannerToolSpec, redact_payload
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records


def receipt(args, cwd=None):
    return invocation_receipt(args, cwd=cwd, before=[], after=[], returncode=0, timed_out=False)


def workspace(tmp_path):
    result = WorkerWorkspace(root=tmp_path)
    result.repo_dir.mkdir(parents=True)
    return result


def test_ordered_full_argv_is_postdelegate_and_cwd_is_forwarded(tmp_path):
    ws = workspace(tmp_path)
    cwd = ws.repo_dir / 'apps/web'
    cwd.mkdir(parents=True)
    command = ('trufflehog', 'git', '.', *[f'--flag-{n}' for n in range(12)])
    def runner(args, *, cwd, **kwargs):
        assert cwd == ws.repo_dir / 'apps/web'
        return WorkerCommandResult(args=(*args, '--branch', 'HEAD'), returncode=0, stdout='', stderr='')
    result = _run(runner, command, cwd=cwd, limits=WorkerLimits(10, 1000), stdout_path=ws.root / 'scanner-raw/result')
    observed = result.scanner_execution_receipt
    assert observed['argv'] == [*command, '--branch', 'HEAD']
    assert observed['cwd'] == str(cwd)
    assert observed['cwd_evidence'] == 'forwarded_to_runner'
    assert observed['argument_count'] > 10
    assert receipt_summary(observed)['status'] == 'retained_receipt_integrity_verified'
    assert receipt(command)['receipt_sha256'] != receipt(tuple(reversed(command)))['receipt_sha256']


def test_runner_without_cwd_does_not_claim_observed_directory(tmp_path):
    def runner(args):
        return WorkerCommandResult(args=args, returncode=0, stdout='', stderr='')
    result = _run(runner, ('tool',), cwd=tmp_path, limits=WorkerLimits(10, 1000), stdout_path=tmp_path / 'scanner-raw/result')
    assert result.scanner_execution_receipt['cwd'] is None
    assert result.scanner_execution_receipt['cwd_evidence'] == 'not_observed'


@pytest.mark.parametrize('mutate', [False, True])
def test_root_config_is_inside_workspace_despite_node_cwd_and_changes_are_visible(tmp_path, mutate):
    ws = workspace(tmp_path)
    cwd = ws.repo_dir / 'apps/web'
    cwd.mkdir(parents=True)
    config = ws.root / 'generated-eslint.config.mjs'
    config.write_text('private configuration contents')
    def runner(args, **kwargs):
        if mutate: config.write_text('changed configuration')
        return WorkerCommandResult(args=args, returncode=0, stdout='', stderr='')
    result = _run(runner, ('eslint', '--config', str(config)), cwd=cwd, limits=WorkerLimits(10, 1000), stdout_path=ws.root / 'scanner-raw/result')
    observed = result.scanner_execution_receipt
    before = observed['input_identities_before'][0]
    assert before['status'] == 'hashed'
    assert before['sha256'] == hashlib.sha256(b'private configuration contents').hexdigest()
    assert observed['input_identity_status'] == ('changed_unavailable_or_not_observed' if mutate else 'stable_observed_inputs')
    assert 'private configuration contents' not in json.dumps(observed)
    assert observed['full_configuration_verified'] is False


def test_input_symlink_and_outside_workspace_are_not_read(tmp_path):
    ws = workspace(tmp_path / 'workspace')
    outside = tmp_path / 'private'
    outside.write_text('secret value')
    link = ws.repo_dir / 'config'
    link.symlink_to(outside)
    for config in (link, outside):
        observation = input_snapshot(('semgrep', '--config', str(config)), ws.repo_dir, workspace_root=ws.root)
        assert observation[0]['status'] == 'outside_input_boundary_or_symlink'
        assert 'sha256' not in observation[0]
        assert 'secret value' not in json.dumps(observation)


def test_credentials_are_redacted_and_digest_survives_outer_redaction():
    args = ('tool', '--password', 'sensitive-one', '--token=sensitive-two',
            'API_KEY=sensitive-three', '--header', 'Authorization: Bearer sensitive-four',
            '-c', 'http.extraheader=Authorization: Basic sensitive-five',
            'https://account:sensitive-six@example.org/path?custom=sensitive-seven#sensitive-eight')
    observed = receipt(args)
    persisted = json.loads(json.dumps(redact_payload(observed)))
    serialized = json.dumps(persisted)
    for word in ('one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight'):
        assert f'sensitive-{word}' not in serialized
    assert 'account:' not in serialized
    assert receipt_summary(persisted)['status'] == 'retained_receipt_integrity_verified'
    assert persisted['argv'][-1] == 'https://example.org/path?[REDACTED]#[REDACTED]'


def test_long_receipt_survives_persistence_without_legacy_preview_hash_limit():
    observed = receipt(('tool', *['argument-' + str(n) + '-' + 'x' * 100 for n in range(200)]))
    assert len(json.dumps(observed)) > 8000
    record = json.loads(json.dumps(redact_payload({'scanner_execution_receipt': observed})))
    summary = provenance_summary(record)
    assert summary['execution_receipt']['receipt_sha256'] == observed['receipt_sha256']
    assert summary['execution_receipt']['argv_capture_status'] == 'complete_redacted'
    assert 'argv' not in summary['execution_receipt']
    assert 'argument-199' not in json.dumps(summary)


def test_bounded_capture_is_explicit_and_legacy_receipts_are_not_retrofitted():
    assert safe_argv(('tool', 'x' * 9000))['argv_capture_status'] == 'partial_redacted'
    assert safe_argv(tuple('x' for _ in range(1025)))['captured_argument_count'] == 1024
    summary = provenance_summary({'command_intent': 'tool --config config.yml', 'verified': True})
    assert summary['execution_receipt']['status'] == 'not_recorded'
    assert summary['full_configuration_verified'] is False
    assert summary['coverage']['full_coverage_verified'] is False
    forged = receipt(('tool',))
    forged['argv'].append('unretained')
    assert receipt_summary(forged)['status'] == 'integrity_mismatch'


def blob(tmp_path, native):
    path = tmp_path / 'native.json'
    path.write_text(json.dumps(native))
    return _raw_blob('test', path, 'json')


@pytest.mark.parametrize('tool,native,targets,errors,skipped', [
    ('semgrep', {'paths': {'scanned': ['a.py'], 'skipped': [{'path': 'b.py'}]}, 'errors': [{}]}, 1, 1, 1),
    ('bandit', {'metrics': {'_totals': {}, 'a.py': {}}, 'errors': []}, 1, 0, None),
    ('eslint', [{'filePath': '/repo/a.ts', 'fatalErrorCount': 1}], 1, 1, None),
    ('semgrep', {'paths': {'scanned': []}}, 0, None, None),
    ('eslint', [{'filePath': '/repo/a.ts'}], 1, None, None),
])
def test_native_reported_observations_preserve_unknowns_without_full_coverage(tmp_path, tool, native, targets, errors, skipped):
    observed = native_coverage_observation(tool, blob(tmp_path, native))
    assert observed['status'] == 'reported_native_targets'
    assert observed['reported_target_count'] == targets
    assert observed['native_error_count'] == errors
    assert observed['native_skipped_target_count'] == skipped
    assert observed['full_coverage_verified'] is False
    assert observed['all_repository_targets_analyzed'] is False


@pytest.mark.parametrize('field', ['sha256', 'gzip_sha256'])
def test_native_integrity_mismatch_prevents_derived_coverage(tmp_path, field):
    raw = blob(tmp_path, {'paths': {'scanned': ['a.py']}, 'errors': []})
    raw[field] = '0' * 64
    observed = native_coverage_observation('semgrep', raw)
    assert observed['status'] == 'integrity_mismatch'
    assert observed['reported_target_count'] is None
    assert observed['native_error_count'] is None


def test_tool_payload_and_compact_projection_keep_only_summary(tmp_path, monkeypatch):
    ws = workspace(tmp_path)
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1._scanner_version', lambda *args: 'semgrep 1.170.0')
    observed = receipt(('semgrep', '--config', '/private/config'), ws.repo_dir)
    result = WorkerCommandResult(args=('semgrep', '--config', '/private/config'), returncode=0, stdout='', stderr='', scanner_execution_receipt=observed)
    raw = blob(tmp_path, {'results': [], 'paths': {'scanned': ['private.py']}, 'errors': []})
    payload = _tool_payload(ScannerToolSpec('semgrep', ('semgrep',), 'static'), result, findings=[], capture_complete=True, reason='', raw_blob=raw, execution_source='test', workspace=ws)
    payload.update(commit_sha='a' * 40)
    persisted = json.loads(json.dumps(payload))
    projected = compact_scanner_records({'scan_id': 'test', 'scanner_results': [persisted]}, commit_sha='a' * 40)
    assert len(projected) == 1
    summary = projected[0]['execution_provenance']
    assert summary['execution_receipt']['receipt_sha256'] == observed['receipt_sha256']
    assert summary['execution_receipt']['status'] == 'retained_receipt_integrity_verified'
    assert summary['coverage']['reported_target_count'] == 1
    assert summary['scanner_version'] == '1.170.0'
    assert '/private/config' not in json.dumps(projected)
    assert 'private.py' not in json.dumps(projected)
    assert payload['status'] == 'completed'
    assert summary['full_configuration_verified'] is False


def test_npm_receipts_cover_each_project_with_its_own_cwd_and_inputs(tmp_path, monkeypatch):
    ws = workspace(tmp_path)
    for project in ('apps/a', 'apps/b'):
        folder = ws.repo_dir / project
        folder.mkdir(parents=True)
        (folder / 'package.json').write_text('{}')
        (folder / 'package-lock.json').write_text(json.dumps({'name': project, 'lockfileVersion': 3}))
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1.shutil.which', lambda tool: '/tools/' + tool)
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1._scanner_version', lambda *args: '10.0.0')
    def runner(args, *, stdout_path, **kwargs):
        stdout_path.write_text('{"vulnerabilities": {}}')
        return WorkerCommandResult(args=args, returncode=0, stdout='', stderr='')
    payload = _run_npm_audit(ScannerToolSpec('npm-audit', ('npm',), 'dependency'), ws, runner)
    invocations = payload['scanner_invocation_receipts']
    assert len(invocations) == 2
    assert {row['cwd'] for row in invocations} == {str(ws.repo_dir / p) for p in ('apps/a', 'apps/b')}
    for row in invocations:
        assert len(row['input_identities_before']) == 2
        assert all(item['status'] == 'hashed' for item in row['input_identities_before'])
        assert receipt_summary(row)['status'] == 'retained_receipt_integrity_verified'


def test_osv_fallback_retains_both_attempt_receipts(tmp_path, monkeypatch):
    ws = workspace(tmp_path)
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1.shutil.which', lambda tool: '/tools/' + tool)
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1._scanner_version', lambda *args: '2.3.8')
    calls = []
    def runner(args, *, stdout_path, **kwargs):
        calls.append(args)
        stdout_path.write_text('invalid' if len(calls) == 1 else '{"results": []}')
        return WorkerCommandResult(args=args, returncode=2 if len(calls) == 1 else 0, stdout='', stderr='')
    payload = _run_osv(ScannerToolSpec('osv-scanner', ('osv-scanner',), 'dependency'), ws, runner)
    assert len(payload['scanner_invocation_receipts']) == 2
    assert [row['exit_code'] for row in payload['scanner_invocation_receipts']] == [2, 0]
    assert [row['argv'] for row in payload['scanner_invocation_receipts']] == [list(args) for args in calls]


def test_generated_profile_content_is_bound_to_actual_bytes_not_arbitrary_config(tmp_path):
    from nico.scanner_execution_receipt_v1 import write_generated_config
    generated = tmp_path / 'config.cjs'
    contents = "module.exports = [{rules: {'no-unreachable': 'error'}}];\n"
    write_generated_config(generated, contents)
    observed = input_snapshot(('eslint', '--config', str(generated)), tmp_path)[0]
    assert observed['generated_profile']['redacted_content'] == contents
    assert observed['generated_profile']['original_sha256'] == observed['sha256']
    assert observed['generated_profile']['redacted_content_sha256'] == hashlib.sha256(contents.encode()).hexdigest()
    generated.write_text('arbitrary repository secret contents')
    changed = input_snapshot(('eslint', '--config', str(generated)), tmp_path)[0]
    assert 'generated_profile' not in changed
    arbitrary = tmp_path / 'other.cjs'
    arbitrary.write_text(contents)
    assert 'generated_profile' not in input_snapshot(('eslint', '--config', str(arbitrary)), tmp_path)[0]


def test_generated_semgrep_and_eslint_profiles_are_retained_by_generation_hooks(tmp_path, monkeypatch):
    from nico.scanner_evidence_pipeline_v1 import _semgrep_config, _eslint_config
    ws = workspace(tmp_path)
    parser = ws.repo_dir / 'node_modules/parser/index.js'
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1._node_module_entry', lambda *args: parser)
    for tool, config in [('semgrep', _semgrep_config(ws)), ('eslint', _eslint_config(ws, ws.repo_dir)[0])]:
        observed = input_snapshot((tool, '--config', str(config)), ws.repo_dir, workspace_root=ws.root)[0]
        assert observed['generated_profile']['redacted_content'] == config.read_text()
        assert observed['generated_profile']['original_sha256'] == observed['sha256']
    assert str(parser) in observed['generated_profile']['redacted_content']


def test_invalid_or_missing_native_targets_do_not_claim_empty_scan(tmp_path):
    for tool, native in [('semgrep', {}), ('eslint', [None]), ('bandit', {'results': []})]:
        observed = native_coverage_observation(tool, blob(tmp_path, native))
        assert observed['reported_target_count'] is None
        assert observed['status'] == 'not_reported'


@pytest.mark.parametrize('argument', ['-pSYNTHETIC_PASSWORD', '-uSYNTHETIC_USER_PASSWORD', '-HAuthorization:SYNTHETIC_HEADER', '-chttp.extraheader=SYNTHETIC_HEADER'])
def test_attached_short_credentials_are_redacted(argument):
    observed = receipt(('tool', argument))
    assert 'SYNTHETIC' not in json.dumps(observed)
    assert receipt_summary(redact_payload(observed))['status'] == 'retained_receipt_integrity_verified'


def test_typescript_short_project_flag_is_preserved():
    assert safe_argv(('tsc', '-p', '/repo/tsconfig.json'))['argv'] == ['tsc', '-p', '/repo/tsconfig.json']
    assert safe_argv(('tsc', '-p/repo/tsconfig.json'))['argv'][-1] == '-p/repo/tsconfig.json'


@pytest.mark.parametrize('argument', ['--user=alice:SYNTHETIC_PASSWORD', '--header=X-Custom:SYNTHETIC_VALUE'])
def test_equal_attached_long_credentials_are_redacted(argument):
    observed = receipt(('tool', argument))
    assert 'SYNTHETIC' not in json.dumps(observed)
    assert 'alice:' not in json.dumps(observed)
    assert observed['argv'][1] == argument.split('=')[0] + '=[REDACTED]'
    assert receipt_summary(redact_payload(observed))['status'] == 'retained_receipt_integrity_verified'
