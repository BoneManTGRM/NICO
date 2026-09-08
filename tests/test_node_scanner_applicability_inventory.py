"""Standalone JavaScript does not imply npm dependencies or TypeScript input."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from nico.scanner_evidence_pipeline_v1 import run_canonical_scanner_tools
from nico.scanner_tool_runners import TOOL_SPECS
from nico.worker_execution import WorkerWorkspace
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical
from nico.complete_assessment_gate_v1 import complete_assessment_evidence
from tests.test_scanner_completion_gate import good, SHA, RUN


def scan(tmp_path, monkeypatch, files):
    workspace = WorkerWorkspace(root=tmp_path)
    workspace.repo_dir.mkdir(parents=True)
    for name, content in files.items():
        path = workspace.repo_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1._git_text', lambda _workspace, *args: SHA if args == ('rev-parse', 'HEAD') else '')
    # This applicability unit fixture supplies a synthetic fixed checkout. Real
    # Git/changed-input rejection is exercised by test_preparation_source_integrity.
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.worker_execution import WorkerCommandResult
    original_command = pipeline.run_command
    monkeypatch.setattr(pipeline, 'run_command', lambda args, **kwargs:
        WorkerCommandResult(tuple(args), 0, '', '') if args[0] == 'git' and 'diff' in args else original_command(args, **kwargs))
    specs = tuple(spec for spec in TOOL_SPECS if spec.name in {'npm-audit', 'typescript'})
    return run_canonical_scanner_tools(workspace, specs)


def canonical(artifact):
    value = good()
    for record in value['requested_scanner_records']:
        if record['scanner_name'] not in artifact['tools']:
            continue
        payload = artifact['tools'][record['scanner_name']]
        record.update(deepcopy(payload))
        record.update(state=payload['status'], completed=False, verified=False,
                      verified_complete=False, run_id=RUN, commit_sha=SHA)
    # Same positive generic ESLint signal that caused the production rejection.
    eslint = next(r for r in value['requested_scanner_records'] if r['scanner_name'] == 'eslint')
    eslint['execution_provenance'] = {'coverage': {'status': 'reported_native_targets', 'reported_target_count': 1}}
    return normalize_scanner_applicability_canonical(value)


def test_standalone_js_has_retained_nonexecution_evidence(tmp_path, monkeypatch):
    artifact = scan(tmp_path, monkeypatch, {'files/js/application.js': 'console.log("fixture");\n'})
    for name in ('npm-audit', 'typescript'):
        tool = artifact['tools'][name]
        assert tool['status'] == 'not_applicable'
        assert tool['execution_observed_for_this_report'] is False
        assert tool['completed'] is False and tool['verified_for_this_report'] is False
        blob = artifact['raw_artifact_blobs'][name]
        raw = gzip.decompress(bytes.fromhex(blob['gzip_hex']))
        assert hashlib.sha256(raw).hexdigest() == blob['sha256']
        assert json.loads(raw)['inventory'] == tool['applicability_evidence']
    value = canonical(artifact)
    result = complete_assessment_evidence(value, expected_commit=SHA, expected_run=RUN)
    assert result['passed'] is True
    assert len(result['completed_tools']) == 7
    assert result['not_applicable_tools'] == ['npm-audit', 'typescript']
    assert result['human_approval_proven'] is False


@pytest.mark.parametrize('files,tool', [
    ({'package.json': '{"dependencies":{"some-package":"1.0.0"}}'}, 'npm-audit'),
    ({'pnpm-lock.yaml': 'lockfileVersion: 9'}, 'npm-audit'),
    ({'src/index.ts': 'export const n: number = 1;'}, 'typescript'),
    ({'src/index.mts': 'export const n: number = 1;'}, 'typescript'),
    ({'tsconfig.build.json': '{}'}, 'typescript'),
    ({'package.json': '{"devDependencies":{"typescript":"6.0.3"}}'}, 'typescript'),
    ({'package.json': '{"scripts":{"build":"tsc --noEmit"}}'}, 'typescript'),
    ({'package.json': '{bad json'}, 'typescript'),
])
def test_missing_required_inputs_remain_unavailable(tmp_path, monkeypatch, files, tool):
    artifact = scan(tmp_path, monkeypatch, files)
    assert artifact['tools'][tool]['status'] == 'unavailable'
    assert artifact['tools'][tool]['verified_for_this_report'] is False


@pytest.mark.parametrize('tamper', ['digest', 'source', 'scope', 'complete', 'contradiction', 'raw'])
def test_bad_inventory_cannot_earn_inapplicability(tmp_path, monkeypatch, tamper):
    artifact = scan(tmp_path, monkeypatch, {'files/js/application.js': 'console.log(1);'})
    value = canonical(artifact)
    record = next(r for r in value['requested_scanner_records'] if r['scanner_name'] == 'npm-audit')
    inv = record['applicability_evidence']
    if tamper == 'digest': inv['inventory_sha256'] = '0' * 64
    if tamper == 'source': inv['commit_sha'] = 'c' * 40
    if tamper == 'scope': inv['scope'] = 'sampled_paths'
    if tamper == 'complete': inv['inventory_complete'] = False
    if tamper == 'contradiction': inv['node_dependency_paths'] = ['package.json']
    if tamper == 'raw': record['raw_artifact_sha256'] = ''
    result = complete_assessment_evidence(value, expected_commit=SHA, expected_run=RUN)
    assert result['passed'] is False


def test_inventory_precedes_dependency_preparation(tmp_path, monkeypatch):
    from nico.scanner_tool_runners import ProjectCommandPreparation

    def prepare(workspace, **_):
        generated = workspace.repo_dir / 'node_modules/typescript'
        generated.mkdir(parents=True)
        (generated / 'package.json').write_text('{"name":"typescript"}')
        (generated / 'types.d.ts').write_text('declare const test: string;')
        return ProjectCommandPreparation('unavailable', workspace.repo_dir, False, 'test preparation')

    monkeypatch.setattr('nico.scanner_evidence_pipeline_v1.prepare_project_commands', prepare)
    artifact = scan(tmp_path, monkeypatch, {'files/js/application.js': 'console.log(1);'})
    assert all(tool['status'] == 'not_applicable' for tool in artifact['tools'].values())
    assert artifact['tools']['typescript']['applicability_evidence']['typescript_input_paths'] == []


def test_symlink_and_bounded_inventory_do_not_prove_absence(tmp_path):
    from nico.node_scanner_applicability_v1 import inspect_node_inputs, justified_inapplicability

    (tmp_path / 'source.js').write_text('console.log(1);')
    (tmp_path / 'more.js').write_text('console.log(2);')
    bounded = inspect_node_inputs(tmp_path, SHA, max_entries=1)
    assert bounded['inventory_complete'] is False
    assert not justified_inapplicability(bounded, 'typescript', SHA)
    (tmp_path / 'external').symlink_to(tmp_path / 'outside', target_is_directory=True)
    symlink = inspect_node_inputs(tmp_path, SHA)
    assert not justified_inapplicability(symlink, 'npm-audit', SHA)


def test_new_reasons_localize_without_approving_unknown_text():
    from nico.node_scanner_applicability_v1 import REASONS
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation_field

    for scanner, reason in REASONS.items():
        text = f'{scanner}: not applicable; {reason}'
        translated = _translate_presentation_field(text, 'evidence')
        assert 'no aplicable' in translated and 'ESLint' in translated
        with pytest.raises(ValueError):
            _translate_presentation_field(text + ' Invented successful scanner execution.', 'evidence')


def test_retained_inventory_survives_compaction_and_record_reordering(tmp_path, monkeypatch):
    from nico.scanner_evidence_pipeline_v1 import materialize_raw_artifacts
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records

    artifact = scan(tmp_path, monkeypatch, {'files/js/application.js': 'console.log(1);'})
    materialize_raw_artifacts(artifact, tmp_path / 'retained', repository='test/inventory',
                              commit_sha=SHA, run_id=RUN)
    value = canonical(artifact)
    compact = compact_scanner_records({
        'scan_id': RUN, 'scanner_results': value['requested_scanner_records'],
    }, commit_sha=SHA)
    for record in compact:
        if record['scanner_name'] in {'npm-audit', 'typescript'}:
            original = next(r for r in value['requested_scanner_records'] if r['scanner_name'] == record['scanner_name'])
            assert record['applicability_evidence'] == original['applicability_evidence']
            assert record['raw_artifact_sha256'] == original['raw_artifact_sha256']
            assert record['raw_artifact_retention_complete'] is True
            assert record['completed'] is False and record['verified_complete'] is False
    baseline = complete_assessment_evidence(value, expected_commit=SHA, expected_run=RUN)
    value['requested_scanner_records'].reverse()
    reordered = complete_assessment_evidence(value, expected_commit=SHA, expected_run=RUN)
    assert baseline['passed'] is True and reordered['passed'] is True
    assert set(baseline['completed_tools']) == set(reordered['completed_tools'])
    assert set(baseline['not_applicable_tools']) == set(reordered['not_applicable_tools'])


def test_corrupt_retained_inventory_cannot_prove_absence(tmp_path, monkeypatch):
    from nico.scanner_evidence_pipeline_v1 import materialize_raw_artifacts

    artifact = scan(tmp_path, monkeypatch, {'files/js/application.js': 'console.log(1);'})
    artifact['raw_artifact_blobs']['npm-audit']['gzip_hex'] = '00'
    materialize_raw_artifacts(artifact, tmp_path / 'retained', repository='test/inventory',
                              commit_sha=SHA, run_id=RUN)
    result = complete_assessment_evidence(canonical(artifact), expected_commit=SHA, expected_run=RUN)
    assert result['passed'] is False
    assert 'npm-audit:node_input_inventory_bytes_unverified' in result['failures']
