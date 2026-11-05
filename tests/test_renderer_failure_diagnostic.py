"""Retained renderer failures become bounded classifications, never acceptance."""
from copy import deepcopy
import json
import time

import pytest

from nico.comprehensive_final_report_process_isolation_v1 import _process_worker_failure
from nico.qualification_failure_diagnostics import renderer_failure_diagnostic
from scripts.qualify_comprehensive_diagnostic import (
    FINAL_STAGE, emit_renderer_failure_diagnostic, final_package, poll_diagnostic_run,
)
from tests.test_comprehensive_diagnostic_runner import context


def test_real_worker_failure_keeps_rejection_and_private_error_out_of_console(capsys):
    private = 'PRIVATE_SOURCE_AND_TOKEN_' * 10000
    stage = _process_worker_failure(context(), ValueError(private), {
        'worker_error_type': 'LayoutError', 'worker_error': private,
        'worker_exit_code': 1, 'worker_bootstrap': private,
    })
    record = {'status': 'blocked', 'terminal': True, 'stage_results': {FINAL_STAGE: stage},
              'human_review_required': True, 'client_delivery_allowed': False}
    before = deepcopy(record)
    assert poll_diagnostic_run(None, 'unused', record, started=time.monotonic(), language='es-MX') is record
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary['reason'] == 'detached_stage_execution_failed'
    assert summary['worker_error_type'] == 'LayoutError'
    assert summary['worker_failure_class'] == 'child_exception'
    assert 'PRIVATE' not in output and len(output) < 1500
    with pytest.raises(ValueError, match='^diagnostic_run_not_review_ready$'):
        final_package(record, context())
    assert record == before


@pytest.mark.parametrize('private', ['PRIVATE' * 10000, ['PRIVATE'], {'PRIVATE': 'PRIVATE'}])
def test_arbitrary_fields_and_values_are_never_logged(private, capsys):
    stage = {key: private for key in ('reason', 'error_code', 'worker_error_type', 'worker_error',
        'worker_failure_class', 'worker_exit_signal', 'local_render_deadline_expired', 'artifacts_available')}
    stage.update(status='blocked', stage_execution={'worker_termination_confirmed': private},
                 report_package={'pdf_base64': private})
    emit_renderer_failure_diagnostic({'stage_results': {FINAL_STAGE: stage}}, private)
    output = capsys.readouterr().out
    assert 'PRIVATE' not in output and len(output) < 1500
    summary = json.loads(output)
    assert summary['language'] == 'other'
    assert summary['reason'] == 'other'
    assert summary['worker_termination_confirmed'] == 'other'


def test_deadline_and_signal_are_classified_without_freeform_values():
    summary = renderer_failure_diagnostic({'status': 'blocked',
        'reason': 'final_report_publication_deadline_exceeded', 'local_render_deadline_expired': True,
        'worker_exit_signal': 'SIGKILL', 'stage_execution': {'worker_termination_confirmed': True,
        'physical_worker_exit_confirmed': False}}, 'es-MX')
    assert summary['worker_exit_signal'] == 'SIGKILL'
    assert summary['worker_termination_confirmed'] == 'true'
    assert summary['physical_worker_exit_confirmed'] == 'false'
    assert summary['local_render_deadline_expired'] == 'true'


def test_output_failure_preserves_failed_record_and_rejection(monkeypatch):
    record = {'status': 'blocked', 'terminal': True, 'stage_results': {FINAL_STAGE: {'status': 'blocked'}},
              'human_review_required': True, 'client_delivery_allowed': False}
    monkeypatch.setattr('builtins.print', lambda *a, **k: 1/0)
    assert poll_diagnostic_run(None, 'unused', record, started=time.monotonic(), language='en') is record
    with pytest.raises(ValueError, match='^diagnostic_run_not_review_ready$'):
        final_package(record, context())


@pytest.mark.parametrize('status', ['running', 'complete', None])
def test_nonfailure_and_absent_stage_are_silent(status, capsys):
    emit_renderer_failure_diagnostic({'stage_results': {FINAL_STAGE: {'status': status}}}, 'en')
    emit_renderer_failure_diagnostic({}, 'en')
    assert capsys.readouterr().out == ''


@pytest.mark.parametrize('reason', ['report_generation_failed', 'generated_pdf_not_parseable',
    'comprehensive_final_report_semantic_contract_failed', 'final_report_provider_unavailable'])
def test_source_defined_provider_rejections_remain_specific(reason):
    assert renderer_failure_diagnostic({'status': 'blocked', 'reason': reason}, 'es-MX')['reason'] == reason
