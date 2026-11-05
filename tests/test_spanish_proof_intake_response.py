"""Synthetic proof-harness checks; never launch a browser or submit intake."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/spanish_comprehensive_live_acceptance_v3.py"
RUN_ID = "comprun_" + "a" * 32
ORIGIN = "https://fixture.invalid"


def helper():
    tree = ast.parse(SOURCE.read_text())
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "_submit_and_verify_spanish_intake"]
    assert len(selected) == 1, "proof must verify actual intake response before metadata polling"
    namespace = {"Any": Any, "urlparse": urlparse,
                 "base": SimpleNamespace(recovery=SimpleNamespace(ACTION_SELECTOR="button.submit"))}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_submit_and_verify_spanish_intake"]


class Response:
    url = ORIGIN + "/api/nico/assessment/comprehensive-intake"
    request = SimpleNamespace(method="POST")

    def __init__(self, status=200, payload=None):
        self.status = status
        self.ok = 200 <= status < 300
        self.payload = {"run_id": RUN_ID, "operation": "intake_started"} if payload is None else payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Page:
    def __init__(self, response):
        self.response = response
        self.events = []

    def expect_response(self, predicate, *, timeout):
        self.events.append("watch")
        assert timeout == 180_000
        assert predicate(self.response)
        for url, method in [(self.response.url, "GET"),
                            (ORIGIN + "/api/nico/assessment/comprehensive-run/" + RUN_ID, "POST"),
                            ("https://unrelated.invalid/api/nico/assessment/comprehensive-intake", "POST")]:
            assert not predicate(SimpleNamespace(url=url, request=SimpleNamespace(method=method)))
        page = self
        class Pending:
            value = page.response
            def __enter__(self):
                return self
            def __exit__(self, *args):
                page.events.append("received")
        return Pending()

    def locator(self, selector):
        assert selector == "button.submit"
        return self

    def click(self):
        self.events.append("click")


def test_accepted_response_is_observed_before_returning_exact_identity():
    page = Page(Response())
    assert helper()(page, frontend_origin=ORIGIN) == RUN_ID
    assert page.events == ["watch", "click", "received"]


@pytest.mark.parametrize('operation', ['intake_pending', 'intake_failed', None, 'PRIVATE', 'intake_started', 'intake_idempotent_reuse'])
def test_reservation_id_never_counts_as_backend_acceptance(operation):
    with pytest.raises(AssertionError, match='does not establish backend acceptance') as caught:
        helper()(Page(Response(payload={'run_id': RUN_ID, 'operation': operation,
                                        'intake_reserved': True, 'message': 'PRIVATE'})),
                 frontend_origin=ORIGIN)
    assert 'PRIVATE' not in str(caught.value)


def test_exact_idempotent_reuse_is_accepted():
    assert helper()(Page(Response(payload={'run_id': RUN_ID,
                    'operation': 'intake_idempotent_reuse'})), frontend_origin=ORIGIN) == RUN_ID


@pytest.mark.parametrize("status,body,code", [
    (422, {"detail": {"code": "spanish_report_generation_unavailable", "message": "PRIVATE"}}, "spanish_report_generation_unavailable"),
    (422, {"detail": {"code": "unsupported_report_language", "message": "PRIVATE"}}, "unsupported_report_language"),
    (403, {"detail": {"code": "PRIVATE"}}, "unclassified_intake_rejection"),
    (500, ValueError("PRIVATE"), "unclassified_intake_rejection"),
    (404, ["PRIVATE"], "unclassified_intake_rejection"),
])
def test_rejection_fails_with_status_and_allowlisted_code_only(status, body, code):
    with pytest.raises(AssertionError) as caught:
        helper()(Page(Response(status, body)), frontend_origin=ORIGIN)
    assert f"HTTP {status}" in str(caught.value)
    assert code in str(caught.value)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("payload", [{"operation": "intake_started"}, {"operation": "intake_started", "run_id": "PRIVATE"}])
def test_success_without_valid_backend_identity_is_not_accepted(payload):
    with pytest.raises(AssertionError, match="accepted intake response lacks a valid run identity") as caught:
        helper()(Page(Response(200, payload)), frontend_origin=ORIGIN)
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize('payload', [[], ValueError('PRIVATE')])
def test_malformed_success_body_does_not_establish_acceptance(payload):
    with pytest.raises(AssertionError, match='does not establish backend acceptance') as caught:
        helper()(Page(Response(200, payload)), frontend_origin=ORIGIN)
    assert 'PRIVATE' not in str(caught.value)


def test_transport_timeout_propagates_without_retry():
    class TimeoutPage(Page):
        def expect_response(self, *args, **kwargs):
            self.events.append("watch")
            raise TimeoutError("response timeout")
    page = TimeoutPage(Response())
    with pytest.raises(TimeoutError):
        helper()(page, frontend_origin=ORIGIN)
    assert page.events == ["watch"]


def test_proof_requires_accepted_identity_before_existing_durable_checks():
    source = SOURCE.read_text()
    run = source[source.index("def _commercial_spanish_run_proof("):source.index("def install_spanish_terminal_boundary(")]
    assert run.index("_submit_and_verify_spanish_intake(") < run.index("_wait_for_run_id(")
    assert run.index("assert browser_run_id == run_id") < run.index("_fetch_and_verify_durable_engagement(")
    assert "assert base.recovery._start_count(requests) == 1" in run


@pytest.mark.parametrize("outcome", ["timeout", "mismatch"])
def test_ui_failure_retains_and_cleans_up_only_the_backend_accepted_id(outcome):
    # Execute the actual acceptance block and existing finally block in isolation.
    # All other UI/render work is outside this failure boundary.
    tree = ast.parse(SOURCE.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "_commercial_spanish_run_proof")
    boundary = next(n for n in function.body if isinstance(n, ast.Try))
    start = next(i for i, n in enumerate(boundary.body)
                 if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                 and isinstance(n.value.func, ast.Name)
                 and n.value.func.id == "_submit_and_verify_spanish_intake")
    stop = next(i for i in range(start, len(boundary.body))
                if isinstance(boundary.body[i], ast.Assert)
                and "browser_run_id" in ast.unparse(boundary.body[i].test))
    isolated = ast.Module(body=[ast.Try(body=boundary.body[start:stop+1],
                                       handlers=[], orelse=[], finalbody=boundary.finalbody)],
                          type_ignores=[])
    events = []
    args = SimpleNamespace()
    def wait(*unused):
        if outcome == "timeout":
            raise TimeoutError("UI persistence timeout")
        return "comprun_" + "b" * 32, {}
    def cancel(page, origin, run_id):
        events.append(("cancel", run_id))
        return {"succeeded": True}
    namespace = {"page": object(), "origin": ORIGIN, "args": args,
                 "run_id": "", "proof_completed": False,
                 "_submit_and_verify_spanish_intake": lambda *a, **k: RUN_ID,
                 "context": SimpleNamespace(close=lambda: events.append(("close",))),
                 "base": SimpleNamespace(_cancel_proof_run=cancel,
                                         recovery=SimpleNamespace(_wait_for_run_id=wait))}
    expected = TimeoutError if outcome == "timeout" else AssertionError
    with pytest.raises(expected):
        exec(compile(ast.fix_missing_locations(isolated), str(SOURCE), "exec"), namespace)
    assert args.proof_run_id == RUN_ID
    assert args.proof_cleanup == {"succeeded": True}
    assert events == [("cancel", RUN_ID), ("close",)]
