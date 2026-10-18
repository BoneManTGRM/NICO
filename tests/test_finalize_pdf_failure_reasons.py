import json
import logging
import pytest
from nico import report_delivery_timing_v1 as timing


def records(caplog):
    return [json.loads(r.getMessage().split('=',1)[1]) for r in caplog.records
            if r.getMessage().startswith('NICO_REPORT_TIMING=')]


@pytest.mark.parametrize('reason',sorted(timing._FAILURE_REASONS))
def test_fixed_reason_never_serializes_exception_message(caplog,reason):
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    class PrivateError(ValueError):
        def __str__(self): raise AssertionError('exception message must not be inspected')
    original=PrivateError('PRIVATE_SOURCE_PATH TOKEN REPORT CONTENT')
    with pytest.raises(PrivateError) as caught:
        with timing.report_delivery_timing('comprun_'+'a'*32,'es-MX'):
            with timing.report_delivery_phase_scope('finalize_pdf'):
                with timing.report_delivery_failure_scope(reason): raise original
    assert caught.value is original
    assert records(caplog)[0]['failure_reason']==reason
    assert 'PRIVATE_SOURCE_PATH' not in caplog.text
    assert 'TOKEN' not in caplog.text
    assert sum('NICO_REPORT_' in r.getMessage() for r in caplog.records)==3


def test_unknown_reason_is_redacted_and_inner_reason_wins(caplog):
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    with pytest.raises(ValueError):
        with timing.report_delivery_timing('comprun_'+'a'*32,'en'):
            with timing.report_delivery_failure_scope('pdf_compose'):
                timing.record_report_delivery_failure_reason('PRIVATE TOKEN')
                raise ValueError('PRIVATE MESSAGE')
    assert records(caplog)[0]['failure_reason']=='unknown_failure'
    assert 'PRIVATE' not in caplog.text


@pytest.mark.parametrize('review_pages,reason',[(58,'pdf_total_pages_limit'),(61,'pdf_required_pages_limit')])
def test_actual_page_budget_failures_remain_fail_closed(caplog,review_pages,reason):
    from tests.test_client_pdf_compose_v2 import _pdf
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    with pytest.raises(ValueError,match='60-page boundary'):
        with timing.report_delivery_timing('comprun_'+'a'*32,'es-MX'):
            with timing.report_delivery_failure_scope('pdf_compose'):
                compose_compact_client_pdf(_pdf(['Primary evidence']),_pdf(['Register']),_pdf(['Gate']),
                    review_pdf=_pdf(*[[f'Review page {i}'] for i in range(review_pages)]))
    assert records(caplog)[0]['failure_reason']==reason


def test_success_has_no_failure_reason_and_sixty_pages_still_pass(caplog):
    from tests.test_client_pdf_compose_v2 import _pdf
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    import io
    from pypdf import PdfReader
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_'+'a'*32,'en'):
        with timing.report_delivery_failure_scope('pdf_compose'):
            result=compose_compact_client_pdf(_pdf(['Primary evidence']),_pdf(['Register']),_pdf(['Gate']),
                review_pdf=_pdf(*[[f'Review page {i}'] for i in range(57)]))
    assert len(PdfReader(io.BytesIO(result)).pages)==60
    assert 'failure_reason' not in records(caplog)[0]


@pytest.mark.parametrize('attribute,reason',[
 ('render_compact_finding_register_pdf','pdf_register_render'),
 ('render_evidence_review_gate_pdf','pdf_gate_render'),
 ('compose_compact_client_pdf','pdf_compose'),
 ('sanitize_client_pdf_status','pdf_sanitize')])
def test_finalizer_identifies_failed_operation_without_leaking_payload(monkeypatch,caplog,attribute,reason):
    from nico import client_report_completion_v2 as completion
    from tests.test_client_report_completion_v2 import _package
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    original=ValueError('PRIVATE_SOURCE TOKEN REPORT TEXT')
    def fail(*args,**kwargs):raise original
    monkeypatch.setattr(completion,attribute,fail)
    with pytest.raises(ValueError) as caught:
        with timing.report_delivery_timing('comprun_'+'a'*32,'es-MX'):
            completion.finalize_client_report_package(_package())
    assert caught.value is original
    assert records(caplog)[0]['failure_reason']==reason
    assert 'PRIVATE_SOURCE' not in caplog.text


def test_failure_code_survives_progress_budget_without_extra_records(caplog):
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    with pytest.raises(ValueError):
        with timing.report_delivery_timing('comprun_'+'a'*32,'es-MX'):
            for phase in sorted(timing._PHASE_NAMES):
                with timing.report_delivery_phase_scope(phase):pass
            with timing.report_delivery_failure_scope('pdf_compose'):
                timing.record_report_delivery_failure_reason('pdf_total_pages_limit')
                raise ValueError('PRIVATE BUDGET DETAILS')
    assert records(caplog)[0]['failure_reason']=='pdf_total_pages_limit'
    assert len(caplog.records)<=32
    assert 'PRIVATE' not in caplog.text


def test_failed_logging_cannot_replace_original_failure(monkeypatch):
    original=ValueError('PRIVATE ORIGINAL')
    def fail(*args,**kwargs):raise RuntimeError('log transport failed')
    monkeypatch.setattr(timing._LOGGER,'info',fail)
    with pytest.raises(ValueError) as caught:
        with timing.report_delivery_timing('comprun_'+'a'*32,'es-MX'):
            with timing.report_delivery_failure_scope('pdf_review_render'):raise original
    assert caught.value is original


@pytest.mark.parametrize('sanitizer_raises',[False,True])
def test_finalizer_captures_sanitizer_before_compose_time_rebind(monkeypatch,caplog,sanitizer_raises):
    from nico import client_report_completion_v2 as completion
    from tests.test_client_report_completion_v2 import _package
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    compose=completion.compose_compact_client_pdf
    sanitize=completion.sanitize_client_pdf_status
    events=[]
    original_error=ValueError('PRIVATE ORIGINAL SANITIZER ERROR')
    def replacement(*args,**kwargs):
        pytest.fail('compose-time sanitizer rebind changed callable capture order')
    def captured(pdf,**kwargs):
        events.append('captured_sanitizer')
        if sanitizer_raises:raise original_error
        return sanitize(pdf,**kwargs)
    def rebinding_compose(*args,**kwargs):
        events.append('compose')
        monkeypatch.setattr(completion,'sanitize_client_pdf_status',replacement)
        return compose(*args,**kwargs)
    monkeypatch.setattr(completion,'sanitize_client_pdf_status',captured)
    monkeypatch.setattr(completion,'compose_compact_client_pdf',rebinding_compose)
    if sanitizer_raises:
        with pytest.raises(ValueError) as caught:
            with timing.report_delivery_timing('comprun_'+'a'*32,'en'):
                completion.finalize_client_report_package(_package())
        assert caught.value is original_error
        assert records(caplog)[0]['failure_reason']=='pdf_sanitize'
    else:
        with timing.report_delivery_timing('comprun_'+'a'*32,'en'):
            result=completion.finalize_client_report_package(_package())
        assert result['client_delivery_allowed'] is False
        assert 'failure_reason' not in records(caplog)[0]
    assert events==['compose','captured_sanitizer']
    assert 'PRIVATE ORIGINAL' not in caplog.text
