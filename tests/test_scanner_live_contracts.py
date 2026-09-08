from __future__ import annotations
import os
import json
import subprocess
from pathlib import Path
import pytest
from nico.scanner_package_inventory_v1 import inspect_package_sources
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


def _osv_native_result(monkeypatch, tmp_path, payload, exit_code=0):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import TOOL_SPECS
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir()
    (workspace.repo_dir / 'requirements.txt').write_text('idna==3.10\n')
    monkeypatch.setattr(pipeline.shutil, 'which', lambda _: '/tools/osv-scanner')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'osv-scanner version: 2.3.8')

    def runner(args, **kwargs):
        return WorkerCommandResult(tuple(args), exit_code, json.dumps(payload), '')

    return pipeline._run_osv(next(s for s in TOOL_SPECS if s.name == 'osv-scanner'), workspace, runner)


@pytest.mark.parametrize('payload', [
    42, [], {}, {'error': 'lookup failed'}, {'results': 'malformed'},
    {'results': None}, {'results': [None]}, {'results': [{}]},
    {'results': [{'source': {'path': 'requirements.txt', 'type': 'lockfile'}, 'packages': {}}]},
    {'results': [{'source': {'path': 'requirements.txt', 'type': 'lockfile'}, 'packages': [None]}]},
    {'results': [{'source': {'path': 'requirements.txt', 'type': 'lockfile'}, 'packages': [
        {'package': {'name': 'idna', 'version': '3.10', 'ecosystem': 'PyPI'}, 'vulnerabilities': [None]}]}]},
    {'results': [], 'error': 'lookup failed'},
])
def test_malformed_osv_native_json_cannot_pass_report_completion(monkeypatch, tmp_path, payload):
    from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS, complete_assessment_evidence
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth

    observed = _osv_native_result(monkeypatch, tmp_path, payload)
    sha, run = 'a' * 40, 'comprun_osv_native_schema'
    records = []
    for name in REQUIRED_TOOLS:
        record = {'tool': name, 'status': 'completed', 'returncode': 0,
                  'returncode_valid': True, 'verified_for_this_report': True,
                  'output_capture_complete': True, 'artifact_hash': 'b' * 64,
                  'raw_artifact_sha256': 'c' * 64}
        if name == 'osv-scanner':
            record.update(observed)
        record.update(commit_sha=sha, current_run=True, execution_observed_for_this_report=True,
                      raw_artifact_retention_complete=True)
        records.append(record)
    compact = compact_scanner_records({'scan_id': 'scan_schema_fixture', 'snapshot_commit_sha': sha,
        'actual_commit_sha': sha, 'snapshot_match': True, 'scanner_results': records}, commit_sha=sha)
    canonical = reconcile_authoritative_scanner_truth({'identity': {'commit_sha': sha, 'run_id': run},
        'requested_scanner_records': compact, 'pdf_available': True})
    gate = complete_assessment_evidence(canonical, expected_commit=sha, expected_run=run)
    assert not gate['passed'], gate
    assert any(f.startswith('osv-scanner:') for f in gate['failures'])
    assert observed['status'] == 'failed'
    assert observed['verified_for_this_report'] is False
    assert observed['output_capture_complete'] is False
    assert 'OSV JSON schema invalid' in observed['reason']


@pytest.mark.parametrize('findings,exit_code', [(False, 0), (True, 1)])
def test_native_osv_valid_package_results_keep_zero_and_findings_distinct(monkeypatch, tmp_path, findings, exit_code):
    package = {'package': {'name': 'idna', 'version': '3.10', 'ecosystem': 'PyPI'}}
    if findings:
        package['vulnerabilities'] = [{'id': 'TEST-OSV-1', 'summary': 'Synthetic regression fixture'}]
    result = _osv_native_result(monkeypatch, tmp_path, {'results': [
        {'source': {'path': 'requirements.txt', 'type': 'lockfile'}, 'packages': [package]}
    ]}, exit_code)
    assert result['status'] == 'completed'
    assert result['findings_count'] == int(findings)
    assert result['verified_for_this_report'] is True


def test_history_selector_does_not_corrupt_nonhistory_subcommands():
    from nico.v2_snapshot_scanner_authority import _head_scoped_runner
    def runner(args, **kwargs):
        return WorkerCommandResult(tuple(args), 0, '', '')
    cases = [
        ('trufflehog', ('trufflehog', '--version'), False),
        ('trufflehog', ('trufflehog', 'filesystem', '.'), False),
        ('trufflehog', ('git', 'rev-parse', 'HEAD'), False),
        ('trufflehog', ('trufflehog', 'git', '--help'), False),
        ('trufflehog', ('trufflehog', 'git', 'file:///tmp/synthetic'), True),
        ('gitleaks', ('gitleaks', 'version'), False),
        ('gitleaks', ('gitleaks', 'dir', '.'), False),
        ('gitleaks', ('gitleaks', 'detect', '--no-git', '.'), False),
        ('gitleaks', ('gitleaks', 'detect', '--source', '.'), True),
    ]
    for tool, command, should_scope in cases:
        result = _head_scoped_runner(tool, runner)(command)
        selector = '--branch' if tool == 'trufflehog' else '--log-opts'
        assert (selector in result.args) == should_scope
        if should_scope:
            assert result.args[-2:] == (selector, 'HEAD')
        else:
            assert result.args == command


@pytest.mark.parametrize('declaration', ['Gemfile', 'Cargo.toml', 'package.json', 'nested/custom.csproj', 'requirements-dev.txt', 'bom.json', 'build.gradle'])
def test_missing_lockfiles_or_unsupported_package_inputs_are_not_inapplicable(tmp_path, declaration):
    path = tmp_path / declaration; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('unsupported or unresolved\n')
    result = inspect_package_sources(tmp_path)
    assert result['inventory_complete'] and result['package_source_paths']
    assert result['no_declared_package_sources'] is False


def test_inventory_is_bounded_and_does_not_follow_symlinks(tmp_path):
    (tmp_path / 'README.md').write_text('no dependencies declared')
    assert inspect_package_sources(tmp_path)['no_declared_package_sources']
    assert not inspect_package_sources(tmp_path, max_entries=0)['no_declared_package_sources']
    (tmp_path / 'uninspected').symlink_to('/does-not-exist')
    assert not inspect_package_sources(tmp_path)['inventory_complete']


def test_osv_inventory_retains_reproducible_source_bound_inputs_before_preparation(tmp_path, monkeypatch):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import TOOL_SPECS, ProjectCommandPreparation
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir()
    (workspace.repo_dir / 'standalone.js').write_text('console.log(1)')
    _git(workspace.repo_dir, 'init', '-q')
    _git(workspace.repo_dir, 'add', '.')
    _git(workspace.repo_dir, '-c', 'user.name=OpenAI Codex test', '-c', 'user.email=codex-test@example.invalid', 'commit', '-qm', 'Labeled OSV ordering fixture')
    commit = _git(workspace.repo_dir, 'rev-parse', 'HEAD')
    def prepare(workspace, **kwargs):
        (workspace.repo_dir / 'package.json').write_text('{}')
        return ProjectCommandPreparation('unavailable', workspace.repo_dir, False, 'labeled preparation')
    monkeypatch.setattr(pipeline, 'prepare_project_commands', prepare)
    monkeypatch.setattr(pipeline.shutil, 'which', lambda _: '/tools/osv-scanner')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *a: 'osv-scanner 2.3.8')
    original = pipeline._run_problem_tool
    monkeypatch.setattr(pipeline, '_run_problem_tool', lambda spec, workspace, runner, prep:
        original(spec, workspace, runner, prep) if spec.name == 'osv-scanner' else pipeline._unavailable(spec, 'labeled control', source='test'))
    def runner(args, **kwargs):
        return WorkerCommandResult(tuple(args), 128, '', 'No package sources found')
    result = pipeline.run_canonical_scanner_tools(workspace, tuple(s for s in TOOL_SPECS if s.name in {'eslint', 'osv-scanner'}), runner=runner)
    record = result['tools']['osv-scanner']
    assert record['status'] == 'not_applicable'
    inventory = record['applicability_evidence']
    assert inventory['commit_sha'] == commit
    assert inventory['scope'] == 'complete_checkout_before_dependency_preparation'
    assert inventory['inspected_paths'] == ['standalone.js']
    from nico.scanner_package_inventory_v1 import justified_no_packages
    assert justified_no_packages(inventory, commit)
    assert not justified_no_packages({**inventory, 'inspected_paths': []}, commit)


@pytest.mark.parametrize('declared,exit_code,expected', [(False,128,'not_applicable'),(True,128,'failed'),(False,127,'failed')])
def test_osv_observed_no_packages_never_becomes_clean(monkeypatch, tmp_path, declared, exit_code, expected):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import TOOL_SPECS
    workspace = WorkerWorkspace(tmp_path); workspace.repo_dir.mkdir()
    (workspace.repo_dir / ('package.json' if declared else 'README.md')).write_text('{}')
    _git(workspace.repo_dir, 'init', '-q')
    _git(workspace.repo_dir, 'add', '.')
    _git(workspace.repo_dir, '-c', 'user.name=OpenAI Codex test', '-c', 'user.email=codex-test@example.invalid', 'commit', '-qm', 'Labeled OSV native fixture')
    monkeypatch.setattr(pipeline.shutil, 'which', lambda _: '/usr/bin/osv-scanner')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'osv-scanner version: 2.3.8')
    def runner(args, **kwargs):
        return WorkerCommandResult(tuple(args), exit_code, '', 'No package sources found, --help for usage information.\n')
    result = pipeline._run_osv(next(s for s in TOOL_SPECS if s.name=='osv-scanner'), workspace, runner)
    assert result['status'] == expected
    assert result['verified_for_this_report'] is False
    if expected == 'not_applicable':
        assert result['completed'] is False and result['applicable'] is False
        assert result['native_json_output'] is False
        assert result['applicability_evidence']['inventory_complete']


def _git(repo, *args):
    result = subprocess.run(['git', *args], cwd=repo, capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0, f'fixture Git step failed: {args[0]}'
    return result.stdout.strip()


def _assert_actual_scanners(root, *, expected_osv):
    # The deployed bootstrap must be imported before selecting the active runner.
    from nico.api.specialist_ship_ready_bootstrap import app
    from nico import scanner_tool_runners
    sha = _git(root/'repo', 'rev-parse', 'HEAD')
    results = {}
    for name in ('trufflehog', 'osv-scanner'):
        spec = next(s for s in scanner_tool_runners.TOOL_SPECS if s.name == name)
        result = scanner_tool_runners.run_scanner_tool(spec, WorkerWorkspace(root))
        results[name] = {k: result.get(k) for k in ('status','returncode','scanner_tool_version','command_intent','raw_artifact_retention_complete','full_history_verified','history_scope','commit_sha','reason','applicability_evidence')}
        assert result['status'] == ('completed' if name == 'trufflehog' else expected_osv), results
        assert result['raw_artifact_retention_complete'] is True
        assert result['commit_sha'] == sha
        if name == 'trufflehog':
            assert result['full_history_verified'] is True
            assert 'filesystem' not in result.get('command_intent','')
            assert '--branch HEAD' in result['command_intent']
        elif expected_osv == 'not_applicable':
            assert result['verified_for_this_report'] is False
            assert result['applicability_evidence']['no_declared_package_sources'] is True
    return results


@pytest.mark.skipif(os.getenv('NICO_LIVE_SCANNER_CONTRACTS') != '1', reason='requires pinned binaries and bounded network fixture')
def test_real_binaries_use_final_bootstrap_on_synthetic_dependency(tmp_path):
    repo=tmp_path/'repo'; repo.mkdir()
    _git(repo,'init','-q'); _git(repo,'config','user.email','synthetic@example.invalid'); _git(repo,'config','user.name','NICO test')
    (repo/'requirements.txt').write_text('idna==3.10\n')
    _git(repo,'add','.');_git(repo,'commit','-qm','Synthetic fixture')
    _assert_actual_scanners(tmp_path, expected_osv='completed')


@pytest.mark.skipif(os.getenv('NICO_LIVE_SCANNER_CONTRACTS') != '1', reason='requires pinned binaries and bounded network fixture')
def test_real_gitlab_checkout_and_scanners_use_complete_immutable_ancestry(tmp_path):
    from nico.hosted_provider_comprehensive_runtime_v1 import checkout_hosted_provider_snapshot
    sha='ddd0f15ae83993f5cb66a927a28673882e99100b'
    repo, actual, notes=checkout_hosted_provider_snapshot('gitlab.com/gitlab-org/gitlab-test',sha,tmp_path,
        {'PATH':os.environ['PATH'],'HOME':str(tmp_path),'LANG':'C.UTF-8'},access_mode='anonymous_public',credential_used=False)
    assert repo is not None and actual == sha and not notes, notes
    assert _git(repo,'rev-parse','--is-shallow-repository') == 'false'
    assert _git(repo,'for-each-ref','--format=%(refname)') == ''
    assert _git(repo,'remote') == ''
    _assert_actual_scanners(tmp_path, expected_osv='not_applicable')
