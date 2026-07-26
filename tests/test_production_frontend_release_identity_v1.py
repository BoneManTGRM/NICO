from __future__ import annotations

import importlib.util
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "production_frontend_release_identity",
    ROOT / "scripts" / "production_frontend_release_identity.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

from production_frontend_release_identity import (
    DEFAULT_UI_CONTRACT,
    HttpResult,
    ReleaseIdentityError,
    probe_release,
    verify_assessment_page,
    verify_production_frontend,
    wait_for_release_identity,
)


SHA = "a" * 40
ORIGIN = "https://app.nicoaudit.com"


class FakeTime:
    def __init__(self) -> None:
        self.value = 0.0

    def clock(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


class SequenceFetch:
    def __init__(self, results: Iterable[HttpResult | Exception]) -> None:
        self.results = iter(results)
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> HttpResult:
        self.requests.append(request)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def release_result(*, sha: str = SHA, contract: str = DEFAULT_UI_CONTRACT, environment: str = "production") -> HttpResult:
    return HttpResult(
        status=200,
        body=json.dumps(
            {
                "status": "ok",
                "release_sha": sha,
                "ui_contract": contract,
                "deployment_environment": environment,
                "git_ref": "main",
            }
        ),
        headers={},
    )


def page_result(label: str) -> HttpResult:
    return HttpResult(
        status=200,
        body=(
            '<main data-workspace="assessment" data-engagement-type="comprehensive" '
            'data-canonical-assessment="strategic" '
            'data-assessment-copy-contract="expert-engagement-v2" '
            'data-assessment-action-copy="create-engagement-v2">'
            f"<button>{label}</button></main>"
        ),
        headers={},
    )


def test_successful_provider_status_cannot_override_stale_custom_domain_sha() -> None:
    fake_time = FakeTime()
    fetch = SequenceFetch([release_result(sha="b" * 40)] * 3)

    with pytest.raises(ReleaseIdentityError) as caught:
        wait_for_release_identity(
            origin=ORIGIN,
            expected_sha=SHA,
            timeout_seconds=2,
            interval_seconds=1,
            fetch=fetch,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
            wall_time_ns=lambda: 100,
        )

    evidence = caught.value.evidence
    assert evidence["status"] == "failed"
    assert evidence["expected_sha"] == SHA
    assert evidence["final_observation"]["release_sha"] == "b" * 40
    assert "production alias remains stale" in evidence["error"]


def test_stale_release_can_converge_to_exact_sha_after_bounded_propagation() -> None:
    fake_time = FakeTime()
    fetch = SequenceFetch([release_result(sha="b" * 40), release_result()])

    observation, attempts, elapsed = wait_for_release_identity(
        origin=ORIGIN,
        expected_sha=SHA,
        timeout_seconds=10,
        interval_seconds=1,
        fetch=fetch,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        wall_time_ns=lambda: 101,
    )

    assert observation["release_sha"] == SHA
    assert len(attempts) == 2
    assert elapsed == 1


def test_wrong_ui_contract_fails_closed() -> None:
    fake_time = FakeTime()
    fetch = SequenceFetch([release_result(contract="obsolete-contract")] * 2)

    with pytest.raises(ReleaseIdentityError) as caught:
        wait_for_release_identity(
            origin=ORIGIN,
            expected_sha=SHA,
            timeout_seconds=1,
            interval_seconds=1,
            fetch=fetch,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
            wall_time_ns=lambda: 102,
        )

    assert caught.value.evidence["final_observation"]["ui_contract"] == "obsolete-contract"


def test_temporarily_unavailable_release_endpoint_is_retried() -> None:
    fake_time = FakeTime()
    fetch = SequenceFetch([TimeoutError("temporary outage"), release_result()])

    observation, attempts, _ = wait_for_release_identity(
        origin=ORIGIN,
        expected_sha=SHA,
        timeout_seconds=10,
        interval_seconds=1,
        fetch=fetch,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        wall_time_ns=lambda: 103,
    )

    assert attempts[0]["http_status"] == 0
    assert "temporary outage" in attempts[0]["error"]
    assert observation["release_sha"] == SHA


def test_preview_deployment_cannot_satisfy_production_acceptance() -> None:
    fake_time = FakeTime()
    fetch = SequenceFetch([release_result(environment="preview")] * 2)

    with pytest.raises(ReleaseIdentityError) as caught:
        wait_for_release_identity(
            origin=ORIGIN,
            expected_sha=SHA,
            timeout_seconds=1,
            interval_seconds=1,
            fetch=fetch,
            clock=fake_time.clock,
            sleep=fake_time.sleep,
            wall_time_ns=lambda: 104,
        )

    assert caught.value.evidence["final_observation"]["deployment_environment"] == "preview"
    assert caught.value.evidence["expected_deployment_environment"] == "production"


def test_release_probe_uses_no_store_headers_and_cache_buster() -> None:
    fetch = SequenceFetch([release_result()])
    probe_release(
        origin=ORIGIN,
        expected_sha=SHA,
        attempt=7,
        fetch=fetch,
        wall_time_ns=lambda: 123456789,
    )

    request = fetch.requests[0]
    headers = {key.lower(): value for key, value in request.header_items()}
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
    assert "no-store" in headers["cache-control"]
    assert headers["pragma"] == "no-cache"
    assert query["attempt"] == ["7"]
    assert query["expected_sha"] == [SHA]
    assert query["_nico_release_probe"] == ["123456789"]


def test_stale_english_label_fails_after_exact_release_identity() -> None:
    page = {
        "http_status": 200,
        "url": ORIGIN + "/assessment",
        "html": page_result("Run NICO Assessment").body,
    }
    with pytest.raises(ReleaseIdentityError) as caught:
        verify_assessment_page(locale="en", page=page)
    assert "Create engagement and capture repository snapshot" in caught.value.evidence["page"]["missing"]
    assert "Run NICO Assessment" in caught.value.evidence["page"]["forbidden"]


def test_stale_spanish_label_fails_after_exact_release_identity() -> None:
    page = {
        "http_status": 200,
        "url": ORIGIN + "/es/assessment",
        "html": page_result("Ejecutar evaluación NICO").body,
    }
    with pytest.raises(ReleaseIdentityError) as caught:
        verify_assessment_page(locale="es-MX", page=page)
    assert "Crear encargo y capturar instantánea del repositorio" in caught.value.evidence["page"]["missing"]
    assert "Ejecutar evaluación NICO" in caught.value.evidence["page"]["forbidden"]


def test_exact_release_and_both_language_contracts_pass() -> None:
    fake_time = FakeTime()
    fetch = SequenceFetch(
        [
            release_result(),
            page_result("Create engagement and capture repository snapshot"),
            page_result("Crear encargo y capturar instantánea del repositorio"),
        ]
    )

    result = verify_production_frontend(
        origin=ORIGIN,
        expected_sha=SHA,
        timeout_seconds=1,
        interval_seconds=0,
        fetch=fetch,
        clock=fake_time.clock,
        sleep=fake_time.sleep,
        wall_time_ns=lambda: 105,
    )

    assert result["status"] == "passed"
    assert result["final_release_observation"]["release_sha"] == SHA
    assert result["pages"]["en"]["verified"] is True
    assert result["pages"]["es-MX"]["verified"] is True
    assert all(result["proof"].values())
