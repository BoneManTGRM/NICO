from __future__ import annotations

import importlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request

import pytest
import yaml

from scripts.github_actions_nico_proof_auth_v1 import AuthenticatedBrowser, SESSION_HEADER

ROOT = Path(__file__).resolve().parents[1]
# Executed scripts use sibling imports when invoked directly by Actions.
SCRIPTS = str(ROOT / "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
consumer = importlib.import_module("completed_run_authenticated_two_pass_acceptance_v1")

WORKFLOWS = {
    "mobile-restart-production-proof.yml": "mobile_restart_authenticated_live_acceptance_v1.py",
    "ios-webkit-paint-proof.yml": "ios_webkit_authenticated_live_acceptance_v1.py",
    "two-service-production-acceptance.yml": "completed_run_authenticated_two_pass_acceptance_v1.py",
}


@pytest.mark.parametrize("filename,entrypoint", WORKFLOWS.items())
def test_canonical_consumer_uses_authenticated_wrapper_and_job_scoped_oidc(filename, entrypoint):
    config = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
    job = config["jobs"]["live-production"]
    assert job["environment"] == "production-smoke"
    assert job["permissions"]["id-token"] == "write"
    assert config.get("permissions", {}).get("id-token") != "write"
    assert config["jobs"]["contract"].get("permissions", {}).get("id-token") != "write"
    assert "github.event.workflow_run.head_branch == 'main'" in job["if"]
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    scripts = "\n".join(step.get("run", "") for step in job["steps"])
    assert f"python scripts/{entrypoint}" in scripts
    assert "--source-workflow-run-id" in scripts
    assert "--source-workflow-run-attempt" in scripts
    assert "--expected-proof-tool-sha" in scripts
    assert "--observation-seconds 90" in scripts
    # Every canonical status is written by its own workflow only. No finalizer
    # can race to overwrite these outcomes, and each job has its own runtime.
    assert not (ROOT / ".github/workflows/specialist-production-proof-finalizer.yml").exists()
    if filename.startswith("mobile-"):
        assert "python scripts/prepare_playwright_native_visibility_v1.py" in scripts
        assert "prepare_playwright_webkit_native_visibility_v1.py" not in scripts
    elif filename.startswith("ios-"):
        assert "python scripts/prepare_playwright_webkit_native_visibility_v1.py" in scripts
        assert "prepare_playwright_native_visibility_v1.py" not in scripts


class Browser:
    def __init__(self):
        self.contexts = []

    def new_context(self, **kwargs):
        cookies = []
        context = SimpleNamespace(cookies=cookies, add_cookies=cookies.extend, options=kwargs)
        self.contexts.append(context)
        return context


def test_each_clean_browser_context_receives_only_origin_scoped_cookie():
    raw = Browser()
    wrapped = AuthenticatedBrowser(raw, session="test-proof-session", frontend_url="https://app.nicoaudit.com")
    first = wrapped.new_context(extra_http_headers={"Cache-Control": "no-store"})
    second = wrapped.new_context(locale="en-US")
    assert first is not second
    for context in (first, second):
        assert context.cookies[0]["url"] == "https://app.nicoaudit.com"
        assert context.cookies[0]["httpOnly"] is True
        assert context.cookies[0]["secure"] is True
        assert context.cookies[0]["sameSite"] == "Strict"
        assert SESSION_HEADER not in context.options.get("extra_http_headers", {})


@pytest.mark.parametrize("url,method", [
    ("https://attacker.invalid/api/nico/assessment/comprehensive-run/run/report/json", "GET"),
    ("http://app.nicoaudit.com/api/nico/assessment/comprehensive-run/run/report/json", "GET"),
    ("https://app.nicoaudit.com/api/nico/admin/config", "GET"),
    ("https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/run/report/json?next=other", "GET"),
    ("https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/run/report/json", "POST"),
])
def test_report_credentials_are_rejected_before_untrusted_request(monkeypatch, url, method):
    calls = []
    monkeypatch.setattr(consumer, "build_opener", lambda *_: SimpleNamespace(open=lambda *a, **kw: calls.append(a)))
    open_report = consumer.authenticated_report_opener("https://app.nicoaudit.com", "test-proof-session")
    with pytest.raises(ValueError):
        open_report(Request(url, method=method), timeout=300)
    assert not calls


def test_fresh_canonical_read_is_authenticated_and_digest_validated(monkeypatch):
    canonical = {"identity": {"run_id": "comprun_test", "commit_sha": "b" * 40}}
    from scripts.comprehensive_production_run_handoff_v1 import canonical_json_sha256
    digest = canonical_json_sha256(canonical)
    response = io.BytesIO(json.dumps(canonical).encode())
    response.status = 200
    response.headers = {"x-nico-canonical-truth-sha256": digest}
    calls = []

    def open_request(req, **kw):
        calls.append((req, kw))
        return response

    handlers = []
    monkeypatch.setattr(consumer, "build_opener", lambda *items: (handlers.extend(items) or SimpleNamespace(open=open_request)))
    open_report = consumer.authenticated_report_opener("https://app.nicoaudit.com", "test-proof-session")
    parsed, observed = consumer.proof._read_final_canonical(
        "https://app.nicoaudit.com", "comprun_test", open_request=open_report,
    )
    assert parsed == canonical
    assert observed == digest
    assert calls[0][0].get_header(SESSION_HEADER.capitalize()) == "test-proof-session"
    assert calls[0][1]["timeout"] >= 300
    assert any(isinstance(item, consumer._RejectRedirects) for item in handlers)
    assert handlers[0].redirect_request(None, None, 302, "found", {}, "https://attacker.invalid") is None


@pytest.mark.parametrize("name,launch", [
    ("mobile_restart_authenticated_live_acceptance_v1", "_launch_chromium"),
    ("ios_webkit_authenticated_live_acceptance_v1", "_launch_webkit"),
])
def test_mobile_wrappers_authenticate_and_restore_launcher_even_on_failure(monkeypatch, name, launch):
    module = importlib.import_module(name)
    monkeypatch.setattr(module.recovery, "parse_args", lambda _: SimpleNamespace(frontend_url="https://app.nicoaudit.com"))
    retained = {"scope": "nico_production_proof"}
    monkeypatch.setattr(module, "acquire_production_proof_session", lambda _: ("test-proof-session", retained))
    original = lambda _: Browser()
    monkeypatch.setattr(module.recovery, launch, original)

    def run(_):
        browser = getattr(module.recovery, launch)(None)
        assert browser.new_context().cookies[0]["value"] == "test-proof-session"
        raise RuntimeError("proof_failure_must_propagate")

    monkeypatch.setattr(module.proof, "main", run)
    with pytest.raises(RuntimeError, match="proof_failure_must_propagate"):
        module.main([])
    assert getattr(module.recovery, launch) is original
    assert retained == {}
