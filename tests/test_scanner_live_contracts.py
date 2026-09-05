from __future__ import annotations
import os
import subprocess
from pathlib import Path
import pytest
from nico.scanner_package_inventory_v1 import inspect_package_sources
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


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


@pytest.mark.parametrize('declared,exit_code,expected', [(False,128,'not_applicable'),(True,128,'failed'),(False,127,'failed')])
def test_osv_observed_no_packages_never_becomes_clean(monkeypatch, tmp_path, declared, exit_code, expected):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import TOOL_SPECS
    workspace = WorkerWorkspace(tmp_path); workspace.repo_dir.mkdir()
    (workspace.repo_dir / ('package.json' if declared else 'README.md')).write_text('{}')
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
