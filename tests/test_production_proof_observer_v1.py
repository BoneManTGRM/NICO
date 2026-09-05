from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scripts.production_proof_observer_v1 import ProofObserver

ORIGIN = "https://app.nicoaudit.com"
RUN = "comprun_observer_synthetic"
SECRET = "synthetic-observer-session-not-a-production-credential"


def factory(handler, options):
    def create(**kwargs):
        options.append(kwargs)
        return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)
    return create


def observer(tmp_path, handler, **kwargs):
    options = []
    value = ProofObserver(origin=ORIGIN, session=SECRET, output=tmp_path / "proof.json",
                          run_id=lambda: RUN, client_factory=factory(handler, options), **kwargs)
    return value, options


def test_only_exact_frontend_origin_is_accepted(tmp_path):
    for origin in ("http://app.nicoaudit.com", ORIGIN + ".evil.invalid", ORIGIN + "/path", "https://x@nicoaudit.com"):
        with pytest.raises(ValueError, match="origin_or_session"):
            ProofObserver(origin=origin, session=SECRET, output=tmp_path / "proof.json", run_id=lambda: RUN)


def test_independent_get_keeps_credentials_and_untrusted_text_out_of_evidence(tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"run_id": RUN, "status": "running", "current_stage": "static_analysis",
            "terminal": False, "human_review_required": True, "client_delivery_allowed": False,
            "secret": SECRET, "client_name": "private client", "findings": [{"raw": "sensitive"}]})
    value, options = observer(tmp_path, handler)
    result = value.sample()
    assert result["status"] == "running" and not result["shipping_clearance"]
    assert len(requests) == 1 and requests[0].method == "GET"
    assert requests[0].url.host == "app.nicoaudit.com"
    assert requests[0].headers["X-NICO-Operator-Session"] == SECRET
    assert options[0]["follow_redirects"] is False and options[0]["trust_env"] is False
    assert options[0]["timeout"].read == 10
    serialized = json.dumps(result)
    assert all(text not in serialized for text in (SECRET, "private client", "sensitive"))


@pytest.mark.parametrize("code", [302, 401, 403, 429, 500])
def test_error_or_redirect_is_not_followed_or_counted_as_success(tmp_path, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(code, headers={"Location": "https://evil.invalid/"}, text=SECRET)
    value, _ = observer(tmp_path, handler)
    result = value.sample()
    assert len(calls) == 1 and result["read_error_type"] == "ValueError"
    assert "status" not in result and not result["shipping_clearance"]
    assert SECRET not in json.dumps(result)


def test_wrong_run_response_fails_closed(tmp_path):
    value, _ = observer(tmp_path, lambda _: httpx.Response(200, json={"run_id": "another", "terminal": True}))
    assert value.sample()["read_error_type"] == "ValueError"
    assert not list(tmp_path.glob("*.scanner-observation.json"))


def test_large_response_is_bounded(tmp_path):
    value, _ = observer(tmp_path, lambda _: httpx.Response(200, content=b"x" * 250_001))
    assert value.sample()["read_error_type"] == "ValueError"


def test_invalid_run_id_never_sends_a_request(tmp_path):
    calls = []
    value, _ = observer(tmp_path, lambda request: calls.append(request))
    value._run_id = lambda: "../foreign-run?token=private"
    assert value.sample()["status"] == "waiting_for_run_identity"
    assert not calls


def test_terminal_api_does_not_grant_browser_or_shipping_clearance(tmp_path):
    source = "a" * 40
    def handler(request):
        if request.url.path.endswith("/report/json"):
            return httpx.Response(200, json={"identity": {"run_id": RUN, "commit_sha": source}, "secret": SECRET})
        return httpx.Response(200, json={"run_id": RUN, "status": "review_required", "terminal": True,
                                        "human_review_required": True, "client_delivery_allowed": False})
    value, _ = observer(tmp_path, handler)
    result = value.sample()
    evidence = json.loads((tmp_path / "proof.scanner-observation.json").read_text())
    assert result["terminal"] is True
    assert result["independent_scanner_gate_passed"] is False
    assert evidence["gate"]["passed"] is False
    assert evidence["shipping_clearance"] is False and evidence["browser_proof_passed"] is False
    assert SECRET not in json.dumps(evidence)


def test_watchdog_retains_failure_before_invoking_failure_handler(tmp_path):
    stopped = []
    value, _ = observer(tmp_path, lambda _: httpx.Response(200, json={"run_id": RUN, "status": "running"}),
                        interval=1, stall_seconds=2, on_stall=lambda: stopped.append(True))
    value.watch_browser_wait(True)
    value._pulse_at -= 10
    value._loop()
    assert stopped == [True]
    result = json.loads((tmp_path / "proof.independent-observer.json").read_text())
    assert result[-1]["proof_failure"] == "browser_wait_heartbeat_stalled"
    assert not result[-1]["shipping_clearance"]


def test_normal_poll_stops_without_failure(tmp_path):
    value, _ = observer(tmp_path, lambda _: httpx.Response(200, json={"run_id": RUN, "status": "running"}))
    with value:
        value.pulse()
    assert not value._thread.is_alive()


def test_observations_are_logged_without_replacing_acceptance_gates():
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/spanish-comprehensive-production-proof.yml").read_text()
    wrapper = (root / "scripts/spanish_comprehensive_authenticated_live_acceptance_v1.py").read_text()
    assert "audit-results/spanish-comprehensive-source-proof.log" in workflow
    helper = (root / "scripts/production_proof_observer_v1.py").read_text()
    assert 'print("NICO_INDEPENDENT_OBSERVER "' in helper
    assert 'print("NICO_INDEPENDENT_SCANNER_GATE "' in helper
    assert "faulthandler.dump_traceback(file=sys.stderr" in helper
    assert "require_complete_assessment(" in wrapper
    assert "observer.watch_browser_wait(True)" in wrapper
    assert "proof.base.recovery._wait_for_terminal = previous_wait" in wrapper
