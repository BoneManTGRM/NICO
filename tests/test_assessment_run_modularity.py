from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
HOOK = ASSESSMENT / "useAssessmentRun.ts"
IDENTITY = ASSESSMENT / "assessmentRunIdentity.ts"
PERSISTENCE = ASSESSMENT / "assessmentRunPersistence.ts"
REQUESTS = ASSESSMENT / "assessmentRunRequests.ts"


def test_assessment_run_hook_delegates_bounded_support_contracts() -> None:
    source = HOOK.read_text(encoding="utf-8")

    assert 'from "./assessmentRunIdentity"' in source
    assert 'from "./assessmentRunPersistence"' in source
    assert 'from "./assessmentRunRequests"' in source
    assert "function preserveRunIdentity" not in source
    assert "function readPersistedRun" not in source
    assert "async function requestWithRetry" not in source
    assert "function issueFor" not in source
    assert "async function continueRun" in source
    assert "async function resumePersistedRun" in source
    assert "async function run()" in source


def test_run_identity_helper_preserves_exact_run_contract() -> None:
    source = IDENTITY.read_text(encoding="utf-8")

    assert "export function preserveRunIdentity" in source
    for field in (
        "run_id",
        "repository",
        "customer_id",
        "project_id",
        "commit_sha",
        "evidence_ledger_id",
    ):
        assert field in source
    assert '"default_customer"' in source
    assert '"default_project"' in source
    assert "repository_snapshot?.commit_sha" in source


def test_run_persistence_helper_keeps_storage_and_url_recovery() -> None:
    source = PERSISTENCE.read_text(encoding="utf-8")

    assert 'ACTIVE_RUN_STORAGE_KEY = "nico.comprehensive.active-run.v1"' in source
    assert 'ACTIVE_RUN_QUERY_KEY = "run_id"' in source
    assert "window.localStorage.getItem" in source
    assert "window.localStorage.setItem" in source
    assert "window.localStorage.removeItem" in source
    assert 'url.searchParams.set("tier", "comprehensive")' in source
    assert "window.history.replaceState" in source
    assert "export function readStoredRun" in source
    assert "export function readPersistedRun" in source
    assert "export function clearPersistedRun" in source
    assert "export function writePersistedRun" in source


def test_run_request_helper_preserves_retry_and_fail_closed_classification() -> None:
    source = REQUESTS.read_text(encoding="utf-8")

    assert "export async function requestWithRetry" in source
    assert "CLIENT_RETRY_DELAYS_MS" in source
    assert "X-NICO-Browser-Projection" in source
    assert "terminal-manifest-v1" in source
    assert "assessment_network_error" in source
    assert "export function issueFor" in source
    assert "PERSISTENCE_BLOCK_CODES" in source
    assert "BACKEND_UNAVAILABLE_CODES" in source
    assert 'kind: "configuration_blocked"' in source
    assert 'kind: "service_unavailable"' in source
    assert 'kind: "run_failed"' in source
