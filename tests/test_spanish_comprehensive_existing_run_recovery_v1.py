from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
RECOVERY_SCRIPT = ROOT / "scripts/spanish_comprehensive_existing_run_recovery_v1.py"
SOURCE_SCRIPT = ROOT / "scripts/spanish_comprehensive_live_acceptance_v3.py"
SHA = "a" * 40
REPOSITORY = "BoneManTGRM/NICO"
RUN_ID = "comprun_" + "1" * 32
SOURCE_RUN_ID = "12345678901"
SOURCE_RUN_ATTEMPT = "1"


def _load_recovery(monkeypatch: Any) -> ModuleType:
    playwright = ModuleType("playwright")
    sync_api = ModuleType("playwright.sync_api")
    sync_api.Browser = object
    sync_api.Page = object
    sync_api.sync_playwright = lambda: None
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "nico_existing_run_recovery_test_subject",
        RECOVERY_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _failed_source_payload() -> dict[str, Any]:
    return {
        "artifact_schema": "nico.spanish_comprehensive_live_acceptance.v1",
        "status": "failed",
        "expected_sha": SHA,
        "repository": REPOSITORY,
        "report_language_requested": "es-MX",
        "run_id": RUN_ID,
        "error": "TimeoutError: Page.wait_for_function: Timeout 120000ms exceeded.",
        "production_proof_cleanup": {
            "attempted": True,
            "http_status": 404,
            "succeeded": False,
        },
    }


def _source_job_log() -> str:
    return "\n".join(
        (
            f"RELEASE_SHA: {SHA}",
            f"SOURCE_RUN_ID: {SOURCE_RUN_ID}",
            f"SOURCE_RUN_ATTEMPT: {SOURCE_RUN_ATTEMPT}",
            "spanish_comprehensive_live_acceptance_v3.py",
            "in _commercial_spanish_run_proof",
            "running_visibility = base.recovery._prove_visibility_hidden_visible(",
            "in _prove_visibility_hidden_visible",
            "document.hidden === true && document.visibilityState === 'hidden'",
            "TimeoutError: Page.wait_for_function: Timeout 120000ms exceeded.",
            "Process completed with exit code 1",
        )
    )


def test_failed_producer_artifact_is_bound_to_uncancelled_exact_run(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    recovery = _load_recovery(monkeypatch)
    path = tmp_path / "failed.json"
    raw = json.dumps(_failed_source_payload()).encode("utf-8")
    path.write_bytes(raw)

    result = recovery._load_failed_source(
        path,
        expected_sha=SHA,
        repository=REPOSITORY,
    )

    assert result["run_id"] == RUN_ID
    assert result["failed_source_proof_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["failed_source_cleanup"]["succeeded"] is False


@pytest.mark.parametrize(
    ("cleanup", "code"),
    (
        ({"succeeded": False}, "failed_source_cleanup_unproven"),
        (
            {"attempted": True, "succeeded": True},
            "failed_source_run_was_cancelled",
        ),
    ),
)
def test_failed_source_requires_proven_unsuccessful_cleanup(
    monkeypatch: Any,
    tmp_path: Path,
    cleanup: dict[str, Any],
    code: str,
) -> None:
    recovery = _load_recovery(monkeypatch)
    payload = _failed_source_payload()
    payload["production_proof_cleanup"] = cleanup
    path = tmp_path / "failed.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=code):
        recovery._load_failed_source(
            path,
            expected_sha=SHA,
            repository=REPOSITORY,
        )


def test_source_job_log_binds_release_attempt_and_visibility_boundary(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    recovery = _load_recovery(monkeypatch)
    path = tmp_path / "source.log"
    path.write_text(_source_job_log(), encoding="utf-8")

    result = recovery._load_and_validate_source_job_log(
        path,
        expected_sha=SHA,
        source_workflow_run_id=SOURCE_RUN_ID,
        source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
    )

    assert result["failed_source_control_flow_reached_running_visibility"] is True
    assert result["failed_source_prior_intake_assertions_completed"] is True
    assert result["failed_source_running_reload_completed_before_visibility"] is True
    assert len(result["failed_source_job_log_sha256"]) == 64

    path.write_text(
        _source_job_log().replace("SOURCE_RUN_ATTEMPT: 1", "SOURCE_RUN_ATTEMPT: 2"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="failed_source_job_log_control_flow_invalid"):
        recovery._load_and_validate_source_job_log(
            path,
            expected_sha=SHA,
            source_workflow_run_id=SOURCE_RUN_ID,
            source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
        )


def test_immutable_source_script_proves_intake_reload_then_visibility_order(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    recovery = _load_recovery(monkeypatch)
    digest = hashlib.sha256(SOURCE_SCRIPT.read_bytes()).hexdigest()

    result = recovery._validate_immutable_source_script(
        SOURCE_SCRIPT,
        expected_sha256=digest,
    )

    assert result == {
        "source_script_sha256": digest,
        "source_script_control_flow_order_verified": True,
    }

    source = SOURCE_SCRIPT.read_text(encoding="utf-8")
    reload_assertion = "        assert base.recovery._start_count(requests) == 1\n"
    first = source.index(reload_assertion)
    second = source.index(reload_assertion, first + len(reload_assertion))
    invalid = source[:second] + source[second + len(reload_assertion) :]
    invalid_path = tmp_path / "source.py"
    invalid_path.write_text(invalid, encoding="utf-8")
    invalid_digest = hashlib.sha256(invalid_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="immutable_source_control_flow_order_invalid"):
        recovery._validate_immutable_source_script(
            invalid_path,
            expected_sha256=invalid_digest,
        )

    with pytest.raises(ValueError, match="immutable_source_script_sha256_mismatch"):
        recovery._validate_immutable_source_script(
            SOURCE_SCRIPT,
            expected_sha256="0" * 64,
        )


def test_projection_binds_evidence_ledger_and_real_worker_activity_keys(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    payload = {
        "run_id": RUN_ID,
        "repository": REPOSITORY,
        "commit_sha": SHA,
        "evidence_ledger_id": "ledger-1",
        "report_language": "es-MX",
        "status": "running",
        "terminal": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "active_stage_execution": {
            "state": "running",
            "stage_id": "final_comprehensive_report_generation",
            "lease_id": "lease-1",
            "heartbeat_age_seconds": 2.5,
            "elapsed_seconds": 540.0,
            "deadline_seconds": 900.0,
            "overdue": False,
            "durable_lease_found": True,
            "killable_worker": True,
            "status": "must-not-be-projected",
        },
    }

    view = recovery._projection(payload)
    activity = recovery._activity_projection(payload)

    assert view["evidence_ledger_id"] == "ledger-1"
    assert view["report_language"] == "es-MX"
    assert activity == {
        "state": "running",
        "stage_id": "final_comprehensive_report_generation",
        "lease_id": "lease-1",
        "heartbeat_age_seconds": 2.5,
        "elapsed_seconds": 540.0,
        "deadline_seconds": 900.0,
        "overdue": False,
        "durable_lease_found": True,
        "killable_worker": True,
    }


def test_terminal_observation_uses_only_exact_get_reconciliation(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    initial_view = {
        "run_id": RUN_ID,
        "repository": REPOSITORY,
        "commit_sha": SHA,
        "evidence_ledger_id": "ledger-1",
        "report_language": "es-MX",
        "status": "running",
        "current_stage": "final_comprehensive_report_generation",
        "terminal": False,
        "revision": 59,
        "progress_percent": 82.61,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    terminal_view = {
        **initial_view,
        "status": "review_required",
        "terminal": True,
        "revision": 63,
        "progress_percent": 100.0,
    }
    terminal_payload = {
        **terminal_view,
        "active_stage_execution": {},
    }
    gets: list[dict[str, str]] = []

    def exact_get(
        page: Any,
        *,
        expected_evidence_ledger_id: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        gets.append(
            {
                "run_id": kwargs["run_id"],
                "ledger": expected_evidence_ledger_id,
            }
        )
        return terminal_payload, terminal_view

    monkeypatch.setattr(recovery, "_get_exact_run", exact_get)

    class Page:
        def __init__(self) -> None:
            self.waits: list[int] = []

        def wait_for_timeout(self, milliseconds: int) -> None:
            self.waits.append(milliseconds)

    page = Page()
    payload, view, observations = recovery._wait_existing_run_to_terminal(
        page,
        origin="https://app.nicoaudit.com",
        run_id=RUN_ID,
        expected_sha=SHA,
        repository=REPOSITORY,
        expected_evidence_ledger_id="ledger-1",
        initial_payload=initial_view,
        initial_view=initial_view,
        timeout_seconds=30.0,
    )

    assert payload == terminal_payload
    assert view == terminal_view
    assert gets == [{"run_id": RUN_ID, "ledger": "ledger-1"}]
    assert page.waits == [10_000]
    assert observations[-1]["terminal"] is True


def test_recovery_script_contains_no_client_mutation_dispatch() -> None:
    source = RECOVERY_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    post_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
    ]

    assert post_calls == []
    assert 'parsed.path == "/api/nico/assessment/comprehensive-intake"' in source
    assert 'parsed.path.endswith("/continue")' in source
    assert 'route.abort("blockedbyclient")' in source
    assert '"recovery_start_request_count": 0' in source
    assert '"fresh_assessment_count_during_recovery": 0' in source
    assert '"explicit_same_run_continuation_count": 0' in source


def test_git_sha_and_artifact_sha256_are_distinct_contracts(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)

    assert recovery._require_git_sha("A" * 40, code="bad_git") == "a" * 40
    assert recovery._require_sha256("B" * 64, code="bad_digest") == "b" * 64
    with pytest.raises(ValueError, match="bad_git"):
        recovery._require_git_sha("a" * 64, code="bad_git")
    with pytest.raises(ValueError, match="bad_digest"):
        recovery._require_sha256("b" * 40, code="bad_digest")
