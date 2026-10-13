"""Synthetic credentials only; never requires a browser or network."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import traceback

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_SECRET = 'synthetic-session-value-not-a-real-credential'


@pytest.fixture
def recovery(monkeypatch):
    sync = ModuleType('playwright.sync_api')
    sync.Browser = sync.Page = object
    sync.sync_playwright = lambda: None
    monkeypatch.setitem(sys.modules, 'playwright', ModuleType('playwright'))
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', sync)
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('safe_mobile_proof', ROOT / 'scripts/mobile_restart_live_acceptance_v1.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sensitive_error(kind=TimeoutError):
    return kind('APIRequestContext.get: Timeout 120000ms exceeded\n'
                'Call log:\n Cookie: nico-specialist-session=' + SYNTHETIC_SECRET + '\n'
                'Authorization: Bearer ' + SYNTHETIC_SECRET)


def test_pdf_timeout_keeps_safe_telemetry_without_retry(recovery, monkeypatch):
    calls = []
    class Request:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith('/report/pdf'):
                raise sensitive_error()
            return SimpleNamespace(
                ok=True, status=200, body=lambda: b'{}',
                json=lambda: {'run_id': 'owned-run', 'reports': {
                    'response_bounded': True, 'artifact_delivery': 'on_demand_exact_run',
                    'pdf_available': True, 'markdown_available': True,
                    'canonical_truth_sha256': 'a' * 64}})
    moments = iter((0.0, 1.0, 121.0))
    monkeypatch.setattr(recovery.time, 'monotonic', lambda: next(moments))
    with pytest.raises(recovery.ProofRequestError) as captured:
        recovery._verify_manifest_and_pdf(SimpleNamespace(request=Request()), 'https://example.invalid', 'owned-run')
    text = ''.join(traceback.format_exception(captured.value))
    assert SYNTHETIC_SECRET not in text
    assert 'Authorization:' not in text and 'Cookie:' not in text
    assert 'operation=report_pdf method=GET category=timeout timeout_ms=120000 elapsed_ms=120000' in text
    assert len(calls) == 2
    assert [kwargs['timeout'] for _, kwargs in calls] == [60_000, 120_000]
    assert calls[-1][1]['headers'] == {'Accept': 'application/pdf', 'Cache-Control': 'no-store'}


@pytest.mark.parametrize('operation', ['terminal_manifest', 'report_pdf', 'canonical_status', 'canonical_json', 'localized_markdown'])
def test_transport_error_never_serializes_exception_or_url(recovery, operation):
    class HostileError(Exception):
        def __str__(self):
            raise AssertionError('Exception text must never be inspected')
    def get(*args, **kwargs):
        raise HostileError()
    with pytest.raises(recovery.ProofRequestError) as caught:
        recovery._proof_http_get(SimpleNamespace(request=SimpleNamespace(get=get)), operation,
                                 'https://example.invalid/?token=' + SYNTHETIC_SECRET, timeout=120_000)
    text = ''.join(traceback.format_exception(caught.value))
    assert SYNTHETIC_SECRET not in text
    assert 'category=transport_error' in str(caught.value)


def test_success_response_is_unchanged(recovery):
    response = object()
    page = SimpleNamespace(request=SimpleNamespace(get=lambda *a, **k: response))
    assert recovery._proof_http_get(page, 'report_pdf', 'https://example.invalid', timeout=120_000) is response


@pytest.mark.parametrize('kind', [TimeoutError, AssertionError, RuntimeError, None])
def test_webkit_failure_artifact_and_traceback_are_safe(recovery, monkeypatch, tmp_path, kind):
    monkeypatch.setitem(sys.modules, 'mobile_restart_live_acceptance_v1', recovery)
    layout = ModuleType('mobile_failure_layout_probe')
    layout.prove_failure_layouts = lambda *a: {}
    monkeypatch.setitem(sys.modules, 'mobile_failure_layout_probe', layout)
    spec = importlib.util.spec_from_file_location('safe_webkit_proof', ROOT / 'scripts/mobile_restart_live_acceptance_v2.py')
    webkit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(webkit)
    args = SimpleNamespace(output=tmp_path/'proof.json', frontend_url='https://example.invalid',
                           repository='owner/repo', expected_sha='a' * 40)
    monkeypatch.setattr(recovery, 'parse_args', lambda argv: args)
    class Context:
        def __enter__(self): return object()
        def __exit__(self, *args): return False
    monkeypatch.setattr(webkit, 'sync_playwright', Context)
    monkeypatch.setattr(recovery, '_launch_webkit', lambda p: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(webkit, '_prove_intake_paint', lambda *a: {})
    def fail(*args):
        if kind is None:
            def get(*args, **kwargs): raise sensitive_error()
            return recovery._proof_http_get(
                SimpleNamespace(request=SimpleNamespace(get=get)), 'report_pdf',
                'https://example.invalid/report/pdf', timeout=120_000)
        raise sensitive_error(kind)
    monkeypatch.setattr(recovery, 'run_proof', fail)
    with pytest.raises(RuntimeError) as caught:
        webkit.main([])
    raw = args.output.read_text()
    trace = ''.join(traceback.format_exception(caught.value))
    assert SYNTHETIC_SECRET not in raw + trace
    assert 'Cookie:' not in raw + trace and 'Authorization:' not in raw + trace
    artifact = json.loads(raw)
    assert artifact['status'] == 'failed'
    assert artifact['real_device_tested'] is False
    assert 'fail' in trace  # Original call-site traceback survives without the original message.
    if kind is None:
        assert 'operation=report_pdf' in artifact['error']
        assert 'timeout_ms=120000' in artifact['error']
        assert 'category=timeout' in artifact['error']
    else:
        assert 'exception details redacted' in artifact['error']


def test_artifacts_redact_registered_secrets_in_nested_diagnostics(recovery, monkeypatch, tmp_path, capsys):
    import github_actions_nico_proof_auth_v1 as auth
    monkeypatch.setattr(auth, '_PROOF_SECRETS', set())
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    auth._register_proof_secret(SYNTHETIC_SECRET)
    assert capsys.readouterr().out == ''
    output = tmp_path/'proof.json'
    recovery._write(output, {'status': 'failed', 'diagnostic': {
        'reason': 'Cookie: nico-specialist-session=' + SYNTHETIC_SECRET,
        'nested': [{'body': SYNTHETIC_SECRET}], 'status_code': 200}})
    raw = output.read_text()
    assert SYNTHETIC_SECRET not in raw
    assert json.loads(raw)['diagnostic']['status_code'] == 200
    assert '[REDACTED]' in raw


def test_actions_mask_registration_escapes_command_data(monkeypatch, capsys):
    from scripts import github_actions_nico_proof_auth_v1 as auth
    monkeypatch.setattr(auth, '_PROOF_SECRETS', set())
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    auth._register_proof_secret('synthetic%value\r\n::warning::synthetic')
    assert capsys.readouterr().out == '::add-mask::synthetic%25value%0D%0A::warning::synthetic\n'


def test_exchange_registers_tokens_before_use(monkeypatch):
    from scripts import github_actions_nico_proof_auth_v1 as auth
    monkeypatch.setattr(auth, '_PROOF_SECRETS', set())
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    monkeypatch.setenv('ACTIONS_ID_TOKEN_REQUEST_URL', 'https://example.invalid/oidc')
    monkeypatch.setenv('ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'synthetic-request-token')
    monkeypatch.setenv('RELEASE_SHA', 'a' * 40)
    calls = []
    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps(self.payload).encode()
    def urlopen(request, **kwargs):
        calls.append(request.full_url)
        assert 'synthetic-request-token' in auth._PROOF_SECRETS
        if len(calls) == 1:
            return Response({'value': 'synthetic-oidc-token'})
        assert 'synthetic-oidc-token' in auth._PROOF_SECRETS
        return Response({'session_token': SYNTHETIC_SECRET, 'scope': 'nico_production_proof', 'release_sha': 'a' * 40})
    monkeypatch.setattr(auth.urllib.request, 'urlopen', urlopen)
    token, retained = auth.acquire_production_proof_session('https://example.invalid')
    assert token == SYNTHETIC_SECRET
    assert SYNTHETIC_SECRET in auth._PROOF_SECRETS
    assert SYNTHETIC_SECRET not in json.dumps(retained)


@pytest.mark.parametrize('entrypoint', ['v1', 'v2'])
@pytest.mark.parametrize('outcome', ['success', 'failure', 'artifact_failure'])
def test_entrypoint_output_boundaries(recovery, monkeypatch, tmp_path, capsys, entrypoint, outcome):
    import github_actions_nico_proof_auth_v1 as auth
    monkeypatch.setattr(auth, '_PROOF_SECRETS', {SYNTHETIC_SECRET})
    monkeypatch.delenv('GITHUB_ACTIONS', raising=False)
    args = SimpleNamespace(output=tmp_path/'proof.json', frontend_url='https://example.invalid',
                           repository='owner/repo', expected_sha='a' * 40)
    monkeypatch.setattr(recovery, 'parse_args', lambda argv: args)
    monkeypatch.setattr(recovery, '_require_existing_source_args', lambda args: None)
    class Context:
        def __enter__(self): return object()
        def __exit__(self, *args): return False
    if entrypoint == 'v1':
        module = recovery
        monkeypatch.setattr(recovery, '_launch_chromium', lambda p: SimpleNamespace(close=lambda: None))
    else:
        monkeypatch.setitem(sys.modules, 'mobile_restart_live_acceptance_v1', recovery)
        layout = ModuleType('mobile_failure_layout_probe')
        layout.prove_failure_layouts = lambda *a: {}
        monkeypatch.setitem(sys.modules, 'mobile_failure_layout_probe', layout)
        spec = importlib.util.spec_from_file_location('output_webkit', ROOT / 'scripts/mobile_restart_live_acceptance_v2.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(recovery, '_launch_webkit', lambda p: SimpleNamespace(close=lambda: None))
        monkeypatch.setattr(module, '_prove_intake_paint', lambda *a: {})
    monkeypatch.setattr(module, 'sync_playwright', Context)
    def prove(*args):
        if outcome == 'success':
            return {'status': 'passed', 'nested': [{SYNTHETIC_SECRET: SYNTHETIC_SECRET}]}
        try:
            raise sensitive_error()
        except TimeoutError as inner:
            try:
                raise sensitive_error(RuntimeError) from inner
            except RuntimeError as middle:
                error = sensitive_error(AssertionError)
                error.nico_diagnostic = {'nested': [SYNTHETIC_SECRET]}
                raise error from middle
    monkeypatch.setattr(recovery, 'run_proof', prove)
    if outcome == 'artifact_failure':
        def write_failure(*args):
            raise sensitive_error(OSError)
        monkeypatch.setattr(recovery, '_write', write_failure)
    if outcome == 'success':
        assert module.main([]) == 0
    else:
        with pytest.raises(RuntimeError) as caught:
            module.main([])
        # Emulate the interpreter's uncaught-exception stderr rendering.
        traceback.print_exception(caught.value)
    captured = capsys.readouterr()
    raw = args.output.read_text() if args.output.exists() else '{}'
    assert SYNTHETIC_SECRET not in raw + captured.out + captured.err
    assert 'Authorization:' not in captured.err and 'Cookie:' not in captured.err
    artifact = json.loads(raw)
    if outcome == 'success':
        assert json.loads(captured.out) == artifact
        assert captured.err == ''
        assert artifact['nested'] == [{'[REDACTED]': '[REDACTED]'}]
    else:
        if outcome == 'artifact_failure':
            assert not args.output.exists()
            assert 'artifact_write_failed' in captured.err
        else:
            assert artifact['status'] == 'failed'
            assert 'category=assertion_failed' in artifact['error']
        assert captured.out == ''
        assert 'direct cause' not in captured.err and 'During handling' not in captured.err


def test_assertion_telemetry_uses_allowlisted_operation_not_message(recovery):
    response = SimpleNamespace(ok=False, status=SYNTHETIC_SECRET, body=lambda: b'{}')
    page = SimpleNamespace(request=SimpleNamespace(get=lambda *a, **k: response))
    with pytest.raises(AssertionError) as caught:
        recovery._verify_manifest_and_pdf(page, 'https://example.invalid', 'run')
    text = recovery._safe_exception(caught.value)
    assert SYNTHETIC_SECRET not in text
    assert 'category=assertion_failed operation=_verify_manifest_and_pdf' in text
    assert 'assertion_line=0' not in text


def test_forged_request_error_is_not_a_safe_message(recovery):
    assert SYNTHETIC_SECRET not in recovery._safe_exception(recovery.ProofRequestError(SYNTHETIC_SECRET))
