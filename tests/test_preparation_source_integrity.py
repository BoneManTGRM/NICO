"""Dependency preparation may add installed dependencies, never change assessed source."""
import subprocess

import pytest

from nico import scanner_evidence_pipeline_v1 as pipeline
from nico import v2_snapshot_scanner_authority as authority
from nico.scanner_tool_runners import TOOL_SPECS, ProjectCommandPreparation
from nico.worker_execution import WorkerWorkspace


@pytest.mark.parametrize('path', ['snapshot', 'hosted'])
@pytest.mark.parametrize('changed', [False, True])
def test_preparation_cannot_credit_changed_assessed_inputs(tmp_path, monkeypatch, path, changed):
    workspace = WorkerWorkspace(tmp_path)
    workspace.repo_dir.mkdir()
    source = workspace.repo_dir / 'package.json'
    source.write_text('{"name":"authorized-test"}')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(workspace.repo_dir), *args], text=True).strip()
    git('init', '-q'); git('add', '.')
    git('-c', 'user.name=OpenAI Codex test', '-c', 'user.email=codex-test@example.invalid', 'commit', '-qm', 'Labeled preparation integrity fixture')
    commit = git('rev-parse', 'HEAD')
    def prepare(workspace, **kwargs):
        installed = workspace.repo_dir / 'node_modules'
        installed.mkdir(exist_ok=True)
        (installed / 'generated.js').write_text('dependency installation output')
        if changed:
            source.write_text('{"name":"different-observed-input"}')
        return ProjectCommandPreparation('completed', workspace.repo_dir, True, '')
    # Isolate a completed scanner result: the real final worker boundary must
    # reject it if preparation changed source, independently of scanner parsing.
    def completed(spec, *args):
        return {'tool': spec.name, 'status': 'completed', 'completed': True,
                'verified_for_this_report': True, 'findings': []}
    spec = next(spec for spec in TOOL_SPECS if spec.name == 'eslint')
    module = authority if path == 'snapshot' else pipeline
    monkeypatch.setattr(module, 'prepare_project_commands', prepare)
    monkeypatch.setattr(module, '_run_problem_tool', completed)
    if path == 'snapshot':
        monkeypatch.setattr(authority, 'reconcile_scanner_payload', lambda name, payload, *args: payload)
        result = authority.canonical_snapshot_tool_runner(spec, workspace)
    else:
        result = pipeline.run_canonical_scanner_tools(workspace, (spec,))['tools']['eslint']
    assert git('rev-parse', 'HEAD') == commit  # HEAD labels alone do not detect this defect.
    assert result['status'] == ('failed' if changed else 'completed')
    if changed:
        assert result['completed'] is False and result['verified_for_this_report'] is False
        assert result['source_checkout_verified'] is False
