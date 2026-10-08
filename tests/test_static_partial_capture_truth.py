import json
import time

import pytest

from nico import exact_snapshot_static_triage as triage
from scripts.build_remediation_manifest import static_capture_summary, static_records


@pytest.mark.parametrize('tool', ['bandit', 'semgrep'])
@pytest.mark.parametrize('has_findings', [False, True])
def test_analyzer_diagnostics_preserve_findings_without_completion(tool, has_findings, monkeypatch, tmp_path):
    finding = ({'test_id': 'B602', 'filename': 'nico/control.py', 'line_number': 1,
                'issue_severity': 'HIGH', 'issue_confidence': 'HIGH', 'issue_text': 'owned finding'}
               if tool == 'bandit' else
               {'check_id': 'owned.rule', 'path': 'nico/control.py', 'start': {'line': 1},
                'extra': {'severity': 'ERROR', 'message': 'owned finding', 'metadata': {'confidence': 'HIGH'}}})
    payload = {'results': [finding] if has_findings else [],
               'errors': [{'type': ['PartialParsing', []], 'message': 'PRIVATE_ERROR_BODY',
                           'path': 'PRIVATE_ERROR_PATH'}]}
    text = json.dumps(payload)
    findings, warning = triage.parse_static_findings(tool, text)
    assert len(findings) == int(has_findings)
    assert warning is not None
    assert 'PRIVATE_ERROR' not in warning
    records, manifest_warning = static_records(tool, text)
    assert len(records) == int(has_findings)
    assert manifest_warning == warning

    class Process:
        returncode = 0
        def communicate(self, timeout=None):
            return text, ''

    monkeypatch.setattr(triage.scanner_worker, 'ENABLE_SCANNER_EXECUTION', True)
    monkeypatch.setattr(triage.shutil, 'which', lambda _: '/owned/tool')
    monkeypatch.setattr(triage.scanner_worker, 'command_for_tool', lambda *args: ([tool], tmp_path, []))
    monkeypatch.setattr(triage.subprocess, 'Popen', lambda *args, **kwargs: Process())
    result = triage._run_structured_static_tool(tool, {'binary': tool}, tmp_path, {}, time.monotonic() + 30)
    assert result['execution_completed'] is False
    assert result['execution_status'] == 'execution_failed'
    assert result['finding_count'] == int(has_findings)
    assert 'PRIVATE_ERROR' not in repr(result)


@pytest.mark.parametrize('tool', ['bandit', 'semgrep'])
def test_clean_structured_output_has_no_capture_warning(tool):
    assert triage.parse_static_findings(tool, json.dumps({'results': [], 'errors': []})) == ([], None)


@pytest.mark.parametrize('payload', [{}, [], {'results': None}, {'results': [None]}, {'results': [{}]}, {'results': [], 'errors': None},
                                   {'results': [], 'errors': {}}, {'results': [], 'errors': 'PRIVATE_ERROR_BODY'}])
@pytest.mark.parametrize('tool', ['bandit', 'semgrep'])
def test_malformed_capture_cannot_become_clean(tool, payload):
    findings, warning = triage.parse_static_findings(tool, json.dumps(payload))
    assert findings == []
    assert warning is not None
    assert 'PRIVATE_ERROR_BODY' not in warning


@pytest.mark.parametrize('code', ['', 'missing', '2', '124', '-9'])
def test_missing_or_failed_exit_cannot_grant_capture_credit(code):
    assert static_capture_summary(code, None)['completed'] is False


@pytest.mark.parametrize('code', ['0', '1'])
def test_completed_exit_still_requires_no_capture_warning(code):
    assert static_capture_summary(code, None)['completed'] is True
    assert static_capture_summary(code, 'partial capture')['completed'] is False
