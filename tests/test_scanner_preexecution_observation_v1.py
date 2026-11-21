"""Unavailable decision metadata must not claim an observed analyzer invocation."""
from pathlib import Path

import pytest

from nico.scanner_evidence_pipeline_v1 import _run_typescript
from nico.scanner_execution_receipt_v1 import receipt_summary
from nico.scanner_tool_runners import ProjectCommandPreparation, ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace


@pytest.mark.parametrize('failure', ['policy_disabled', 'preparation_missing', 'compiler_missing'])
def test_preexecution_typescript_unavailable_does_not_claim_an_invocation(tmp_path: Path, monkeypatch, failure: str) -> None:
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    preparation = None
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'false' if failure == 'policy_disabled' else 'true')
    if failure == 'compiler_missing':
        (workspace.repo_dir / 'tsconfig.json').write_text('{}', encoding='utf-8')
        preparation = ProjectCommandPreparation('completed', workspace.repo_dir, True)
    calls = []
    def forbidden_runner(*args, **kwargs):
        calls.append(args)
        raise AssertionError('A preexecution refusal must not invoke the analyzer runner.')
    result = _run_typescript(ScannerToolSpec('typescript', ('tsc',), 'static'), workspace, forbidden_runner, preparation)
    assert calls == []
    assert result['status'] == 'unavailable'
    assert result['current_run'] is True
    assert result['execution_observed_for_this_report'] is False
    assert result['verified_for_this_report'] is False
    assert result['raw_artifact_capture_complete'] is False
    assert 'returncode' not in result and 'scanner_execution_receipt' not in result


def test_actual_failed_target_invocation_retains_observation_and_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'true')
    workspace = WorkerWorkspace(root=tmp_path)
    project = workspace.repo_dir
    (project / 'node_modules' / '.bin').mkdir(parents=True)
    (project / 'tsconfig.json').write_text('{}', encoding='utf-8')
    (project / 'node_modules' / '.bin' / 'tsc').write_text('', encoding='utf-8')
    native_stdout = 'index.ts(1,7): error TS2322: Type string is not assignable to type number.\n'
    calls = []
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        calls.append(tuple(args))
        stdout_path.write_text(native_stdout, encoding='utf-8')
        return WorkerCommandResult(args=tuple(args), returncode=2, stdout=native_stdout, stderr='',
                                   stdout_path=str(stdout_path), stdout_bytes=len(native_stdout))
    result = _run_typescript(ScannerToolSpec('typescript', ('tsc',), 'static'), workspace, runner,
                             ProjectCommandPreparation('completed', project, True))
    assert len(calls) == 1
    assert result['returncode'] == 2
    assert result['findings_count'] == 1
    assert result['findings'][0]['code'] == 'TS2322'
    assert result['execution_observed_for_this_report'] is True
    assert result['current_run'] is True
    assert result['output_capture_complete'] is True
    assert result['raw_artifact_capture_complete'] is True
    assert result['scanner_execution_receipt']['exit_code'] == 2
    assert receipt_summary(result['scanner_execution_receipt'])['status'] == 'retained_receipt_integrity_verified'
