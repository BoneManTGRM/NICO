import json
import time

import pytest

from nico import exact_snapshot_static_triage as triage
from scripts import build_remediation_manifest as manifest


TIMEOUT = {'error_type': 'Fixpoint timeout', 'severity': 'warn',
           'message': 'PRIVATE_DIAGNOSTIC_BODY', 'path': 'PRIVATE_DIAGNOSTIC_PATH'}
FINDING = {'check_id': 'owned.rule', 'path': 'nico/owned.py', 'start': {'line': 1},
           'extra': {'severity': 'ERROR', 'message': 'owned finding',
                     'metadata': {'confidence': 'HIGH'}}}


@pytest.mark.parametrize('exit_code', [0, 1])
@pytest.mark.parametrize('has_findings', [False, True])
@pytest.mark.parametrize('top_errors', [False, True])
def test_nested_timeout_preserves_findings_but_withholds_runtime_and_manifest_credit(
        exit_code, has_findings, top_errors, monkeypatch, tmp_path):
    payload = {'results': [FINDING] if has_findings else [],
               'errors': [TIMEOUT] if top_errors else [],
               'time': {'fixpoint_timeouts': [TIMEOUT, TIMEOUT]}}
    text = json.dumps(payload)
    findings, warning = triage.parse_static_findings('semgrep', text)
    assert len(findings) == int(has_findings)
    assert '2 fixpoint timeout records' in warning
    assert ('1 analyzer diagnostics' in warning) is top_errors
    assert 'unique' not in warning
    assert 'PRIVATE_DIAGNOSTIC' not in warning

    class Process:
        returncode = exit_code
        def communicate(self, timeout=None):
            return text, ''

    monkeypatch.setattr(triage.scanner_worker, 'ENABLE_SCANNER_EXECUTION', True)
    monkeypatch.setattr(triage.shutil, 'which', lambda _: '/owned/tool')
    monkeypatch.setattr(triage.scanner_worker, 'command_for_tool', lambda *args: (['semgrep'], tmp_path, []))
    monkeypatch.setattr(triage.subprocess, 'Popen', lambda *args, **kwargs: Process())
    result = triage._run_structured_static_tool('semgrep', {'binary': 'semgrep'}, tmp_path, {}, time.monotonic() + 30)
    assert result['execution_completed'] is False
    assert result['execution_status'] == 'execution_failed'
    assert result['finding_count'] == int(has_findings)
    assert 'PRIVATE_DIAGNOSTIC' not in repr(result)

    source = tmp_path / 'semgrep.json'; source.write_text(text)
    bandit = tmp_path / 'bandit.json'; bandit.write_text('{"results": [], "errors": []}')
    output = tmp_path / 'manifest.json'
    monkeypatch.setattr('sys.argv', ['manifest', '--semgrep', str(source), '--semgrep-exit', str(exit_code),
                                    '--bandit', str(bandit), '--bandit-exit', '0', '--output', str(output)])
    assert manifest.main() == 0
    report = json.loads(output.read_text())
    assert report['summary']['static_capture_complete'] is False
    assert report['static_capture']['bandit']['completed'] is True
    assert report['static_capture']['semgrep']['completed'] is False
    assert report['summary']['semgrep_material'] == int(has_findings)
    assert warning in report['parse_warnings']
    assert 'PRIVATE_DIAGNOSTIC' not in output.read_text()


@pytest.mark.parametrize('timing', [None, [], 'PRIVATE_DIAGNOSTIC_BODY',
    {'fixpoint_timeouts': None}, {'fixpoint_timeouts': {}},
    {'fixpoint_timeouts': 'PRIVATE_DIAGNOSTIC_BODY'}, {'fixpoint_timeouts': [None]}])
def test_malformed_nested_capture_fails_closed_without_leaking(timing):
    payload = {'results': [FINDING], 'errors': [], 'time': timing}
    findings, warning = triage.parse_static_findings('semgrep', json.dumps(payload))
    assert len(findings) == 1
    assert warning is not None
    assert 'PRIVATE_DIAGNOSTIC' not in warning
    assert manifest.static_capture_summary('0', warning)['completed'] is False


@pytest.mark.parametrize('optional', [{}, {'time': {}}, {'time': {'fixpoint_timeouts': []}}])
def test_absent_or_empty_timeout_collection_remains_complete(optional):
    findings, warning = triage.parse_static_findings('semgrep', json.dumps({'results': [], 'errors': [], **optional}))
    assert (findings, warning) == ([], None)
    assert manifest.static_capture_summary('0', warning)['completed'] is True


def test_semgrep_timing_schema_does_not_change_bandit_contract():
    assert triage.parse_static_findings('bandit', json.dumps({'results': [], 'errors': [], 'time': None})) == ([], None)
