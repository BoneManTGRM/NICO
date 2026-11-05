"""Failure logging preserves rejection and discloses only fixed classifications."""
from copy import deepcopy
import json
import pytest
from nico.qualification_failure_diagnostics import collection_failure_diagnostic, scanner_failure_diagnostic
from scripts.qualify_cpp_project_configuration import validate_qualification_collection
from scripts.qualify_comprehensive_diagnostic import emit_scanner_failure_diagnostic
from tests.test_cpp_assessment_collection import bundle


def test_real_collection_rejection_reports_static_error_without_accepting(tmp_path, capsys):
    receipt, read, kwargs = bundle(tmp_path, kind=None)
    receipt.update(status='UNPROVEN', stage='execution_unproven')
    receipt['probe'].update(status='UNPROVEN', error='worker_configuration_probe_static_incomplete')
    receipt['probe']['project_static_stage'].update(complete=False, error='worker_project_static_stage_deadline')
    before = deepcopy(receipt)
    with pytest.raises(ValueError, match='^qualification_collection_invalid$'):
        validate_qualification_collection(receipt, read, **kwargs)
    result = json.loads(capsys.readouterr().out)
    assert result['status_combination_allowed'] is False
    assert result['static_error'] == 'worker_project_static_stage_deadline'
    assert receipt == before


def test_real_collection_success_unchanged_and_silent(tmp_path, capsys):
    from nico.assessment_cpp_collection import validate_project_collection
    receipt, read, kwargs = bundle(tmp_path, kind=None)
    assert validate_qualification_collection(receipt, read, **kwargs) == validate_project_collection(receipt, read, **kwargs)
    assert capsys.readouterr().out == ''


def test_logging_failure_cannot_replace_rejection(monkeypatch):
    import nico.assessment_cpp_collection as collection
    original = ValueError('qualification_collection_invalid')
    def fail(*a, **k): raise original
    monkeypatch.setattr(collection, 'validate_project_collection', fail)
    monkeypatch.setattr('builtins.print', lambda *a, **k: 1/0)
    with pytest.raises(ValueError) as exc:
        validate_qualification_collection({}, None)
    assert exc.value is original


@pytest.mark.parametrize('private', ['PRIVATE_SECRET_' * 10000, ['SECRET'], {'secret': 'SECRET'}])
def test_malformed_private_values_are_bounded(private, capsys):
    scan = {k: private for k in ('status', 'current_stage', 'snapshot_match', 'execution_limit', 'tools_run', 'failed_tools')}
    receipt = {'status': private, 'stage': private, 'probe': {'status': private, 'error': private, 'project_static_stage': {'error': private, 'complete': private}}}
    for result in (scanner_failure_diagnostic(scan), collection_failure_diagnostic(receipt)):
        output = json.dumps(result)
        assert 'SECRET' not in output and len(output) < 1500
    emit_scanner_failure_diagnostic({'stage_results': {'dependency_security_static_analysis': {
        'status': 'blocked', 'reason': private, 'scanner_diagnostic': scan}}})
    output = capsys.readouterr().out
    assert 'SECRET' not in output and len(output) < 1000


def test_provider_blocked_scan_reaches_console_without_scan_contents(monkeypatch, capsys):
    from nico import comprehensive_native_providers as native
    from tests.test_comprehensive_cpp_worker_selection import context
    scan = {'status': 'unavailable', 'current_stage': 'execution_limited', 'snapshot_match': True,
            'execution_limit': {'reason': 'repository_size_unverified', 'raw': 'SECRET'}, 'scan_id': 'PRIVATE_ID'}
    monkeypatch.setattr(native, '_scan_id', lambda context: 'existing')
    monkeypatch.setattr(native, 'get_scan', lambda scan_id: scan)
    result = native.scanner_suite_provider(context())
    assert result['status'] == 'blocked' and result['reason'] == 'snapshot_scanner_not_verified'
    emit_scanner_failure_diagnostic({'stage_results': {'dependency_security_static_analysis': result}})
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary['execution_limit_reason'] == 'repository_size_unverified'
    assert summary['snapshot_match'] is True
    assert 'SECRET' not in output and 'PRIVATE_ID' not in output


def test_successful_scanner_is_silent(capsys):
    emit_scanner_failure_diagnostic({'stage_results': {'dependency_security_static_analysis': {'status': 'complete'}}})
    assert capsys.readouterr().out == ''
