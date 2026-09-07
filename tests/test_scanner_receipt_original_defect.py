"""Same requirements-derived regression runs on the unchanged a075 pipeline."""
from pathlib import Path
from nico.scanner_evidence_pipeline_v1 import _run, _tool_payload, _raw_blob
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerLimits, WorkerWorkspace


def test_executed_arguments_after_preview_boundary_are_retained(tmp_path, monkeypatch):
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1._scanner_version', lambda *args: '1.0.0')
    command = ('semgrep', *[f'--arg-{n}' for n in range(12)])
    def runner(args, **kwargs):
        return WorkerCommandResult(args=(*args, '--exclude', 'tests'), returncode=0, stdout='{}', stderr='')
    path = tmp_path / 'scanner-raw/semgrep.json'
    result = _run(runner, command, cwd=workspace.repo_dir, limits=WorkerLimits(10, 1000), stdout_path=path)
    payload = _tool_payload(ScannerToolSpec('semgrep', ('semgrep',), 'static'), result, findings=[], capture_complete=True, reason='', raw_blob=_raw_blob('semgrep', path, 'json'), execution_source='test', workspace=workspace)
    receipt = payload.get('scanner_execution_receipt')
    assert isinstance(receipt, dict), 'Abbreviated command_intent omits executed exclusions and has no complete receipt'
    assert receipt['argv'] == [*command, '--exclude', 'tests']
    assert receipt['explicit_exclusion_arguments'] == ['tests']


def test_configuration_bytes_observed_before_execution_are_bound_to_receipt(tmp_path):
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir()
    config = tmp_path / 'effective-config.yml'
    config.write_text('rules: []')
    def runner(args, **kwargs):
        config.write_text('rules: changed')
        return WorkerCommandResult(args=args, returncode=0, stdout='{}', stderr='')
    result = _run(runner, ('semgrep', '--config', str(config)), cwd=workspace.repo_dir, limits=WorkerLimits(10, 1000), stdout_path=tmp_path / 'scanner-raw/semgrep.json')
    receipt = getattr(result, 'scanner_execution_receipt', None)
    assert isinstance(receipt, dict), 'No retained pre/post configuration identity distinguishes changed effective input'
    assert receipt['input_identities_before'][0]['sha256'] != receipt['input_identities_after'][0]['sha256']
    assert receipt['input_identity_status'] == 'changed_unavailable_or_not_observed'
