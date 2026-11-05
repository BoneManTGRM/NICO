import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest


@pytest.fixture
def proof(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    try:
        import playwright.sync_api
    except ModuleNotFoundError:
        api = ModuleType('playwright.sync_api')
        api.Browser = type('Browser', (), {})
        api.Page = type('Page', (), {})
        api.sync_playwright = lambda: None
        monkeypatch.setitem(sys.modules, 'playwright', ModuleType('playwright'))
        monkeypatch.setitem(sys.modules, 'playwright.sync_api', api)
    return importlib.import_module('spanish_comprehensive_live_acceptance_v3')


def busy(delay='5', status=503, reason='retained_pdf_preparing'):
    return httpx.Response(status, json={'detail': {'reason': reason}},
                          headers={} if delay is None else {'Retry-After': delay})


def harness(proof, monkeypatch, responses):
    now = [0.0]; calls = []; retained = []; sleeps = []
    monkeypatch.setattr(proof.time, 'monotonic', lambda: now[0])
    def sleep(seconds):
        sleeps.append(seconds); now[0] += seconds
    monkeypatch.setattr(proof.time, 'sleep', sleep)
    monkeypatch.setattr(proof, 'retain_response', lambda label, **kw: retained.append((label, kw)))
    class Client:
        def get(self, url, **kwargs):
            calls.append((url, kwargs)); return responses[min(len(calls)-1, len(responses)-1)]
    return Client(), now, calls, retained, sleeps


def test_busy_then_success_has_same_target_and_retains_each_attempt(proof, monkeypatch):
    ok = httpx.Response(200, content=b'%PDF-owned')
    client, now, calls, retained, sleeps = harness(proof, monkeypatch, [busy(), ok])
    response = proof._localized_pdf_response(client, frontend_origin='https://owned.invalid', run_id='comprun_owned', report_language='en')
    assert response is ok
    assert len(calls) == len(retained) == 2
    assert calls[0][0] == calls[1][0] == 'https://owned.invalid/api/nico/assessment/comprehensive-run/comprun_owned/localized-report/en/pdf'
    assert sleeps == [5]
    assert [r[1]['status'] for r in retained] == [503, 200]
    assert [r[0] for r in retained] == ['pdf-attempt-en-1', 'pdf-attempt-en-2']


@pytest.mark.parametrize('response', [busy(x) for x in [None, '0', '-1', '1.5', '61', '05', '5 seconds', '999999999999999999', 'Wed, 28 Oct 2026 00:00:00 GMT']] +
    [busy(status=502), busy(status=401), busy(reason='other'), httpx.Response(503, content=b'{'), httpx.Response(503, json=None), httpx.Response(503, json={'detail': []})])
def test_unqualified_failure_never_retries(proof, monkeypatch, response):
    client, now, calls, retained, sleeps = harness(proof, monkeypatch, [response])
    assert proof._localized_pdf_response(client, frontend_origin='https://owned.invalid', run_id='owned', report_language='es-MX') is response
    assert len(calls) == len(retained) == 1
    assert sleeps == []


def test_busy_attempt_cap(proof, monkeypatch):
    client, now, calls, retained, sleeps = harness(proof, monkeypatch, [busy()])
    with pytest.raises(AssertionError, match='attempt limit'):
        proof._localized_pdf_response(client, frontend_origin='https://owned.invalid', run_id='owned', report_language='en')
    assert len(calls) == len(retained) == proof.LOCALIZED_PDF_MAX_ATTEMPTS == 6
    assert sleeps == [5]*5


def test_deadline_does_not_reset_between_attempts(proof, monkeypatch):
    client, now, calls, retained, sleeps = harness(proof, monkeypatch, [busy('60')])
    with pytest.raises(AssertionError, match='deadline'):
        proof._localized_pdf_response(client, frontend_origin='https://owned.invalid', run_id='owned', report_language='en')
    assert now[0] == 240
    assert len(calls) == len(retained) == 5
    assert sleeps == [60]*4


def test_late_success_is_not_accepted(proof, monkeypatch):
    client, now, calls, retained, sleeps = harness(proof, monkeypatch, [httpx.Response(200)])
    get = client.get
    def late(*args, **kwargs):
        result = get(*args, **kwargs); now[0] = 301; return result
    client.get = late
    with pytest.raises(AssertionError, match='deadline'):
        proof._localized_pdf_response(client, frontend_origin='https://owned.invalid', run_id='owned', report_language='en')
    assert len(calls) == len(retained) == 1


@pytest.mark.parametrize('defect', ['signature', 'hash', 'run', 'locale'])
def test_eventual_200_still_requires_pdf_identity(proof, monkeypatch, defect, tmp_path):
    import hashlib
    content = b'wrong' if defect == 'signature' else b'%PDF-owned'
    headers = {'x-nico-run-id': 'wrong' if defect == 'run' else 'owned',
               'x-nico-report-language': 'es-MX' if defect == 'locale' else 'en',
               'x-nico-artifact-sha256': '0'*64 if defect == 'hash' else hashlib.sha256(content).hexdigest()}
    client, now, calls, retained, sleeps = harness(proof, monkeypatch, [busy(), httpx.Response(200, content=content, headers=headers)])
    class Context:
        def __enter__(self): return client
        def __exit__(self, *args): pass
    monkeypatch.setattr(proof.httpx, 'Client', lambda **kw: Context())
    monkeypatch.setattr(proof.httpx, 'HTTPTransport', lambda **kw: object())
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AssertionError):
        proof._fetch_localized_pdf(frontend_origin='https://owned.invalid', run_id='owned', report_language='en')
    assert len(calls) == 2
    assert not (tmp_path/'audit-results').exists()


def test_real_wallclock_alarm_interrupts_and_restores_handler(proof, monkeypatch):
    import signal
    previous = signal.getsignal(signal.SIGALRM)
    monkeypatch.setattr(proof, 'LOCALIZED_PDF_TOTAL_TIMEOUT_SECONDS', 0.02)
    with pytest.raises(AssertionError, match='deadline'):
        with proof._localized_pdf_wallclock_limit():
            proof.time.sleep(0.1)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert signal.getsignal(signal.SIGALRM) == previous


def test_attempt_retention_hashes_and_allowed_headers(proof, monkeypatch, tmp_path):
    import hashlib
    import comprehensive_production_export_retention_v1 as retention
    monkeypatch.chdir(tmp_path)
    capture = retention.Capture('owned', 'a'*40)
    token = retention._ACTIVE.set(capture)
    try:
        retention.retain_response('pdf-attempt-en-1', route='/owned/en/pdf', status=503,
            headers={'Retry-After': '5', 'Authorization': 'PRIVATE', 'Set-Cookie': 'PRIVATE'},
            content=b'{"detail":{"reason":"retained_pdf_preparing"}}')
        item = capture.receipt['files'][0]
        body = (capture.directory/item['path']).read_bytes()
        assert item['sha256'] == hashlib.sha256(body).hexdigest()
        assert item['size_bytes'] == len(body)
        assert item['http_status'] == 503
        assert item['response_headers'] == {'retry-after': '5'}
        assert item['origin'] == 'production_http_response'
        assert 'PRIVATE' not in json.dumps(capture.receipt)
    finally:
        retention._ACTIVE.reset(token)


def test_wallclock_guard_rejects_worker_thread(proof):
    import threading
    errors = []
    def invoke():
        try:
            with proof._localized_pdf_wallclock_limit():
                raise RuntimeError('guard unexpectedly entered')
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=invoke)
    thread.start(); thread.join(timeout=2)
    assert not thread.is_alive()
    assert len(errors) == 1 and isinstance(errors[0], AssertionError)
    assert 'unavailable' in str(errors[0])


def test_wallclock_guard_preserves_preexisting_alarm(proof):
    import signal
    previous = signal.getsignal(signal.SIGALRM)
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    signal.setitimer(signal.ITIMER_REAL, 60)
    try:
        with pytest.raises(AssertionError, match='already in use'):
            with proof._localized_pdf_wallclock_limit():
                raise RuntimeError('guard unexpectedly entered')
        assert signal.getitimer(signal.ITIMER_REAL)[0] > 0
        assert signal.getsignal(signal.SIGALRM) == previous
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
