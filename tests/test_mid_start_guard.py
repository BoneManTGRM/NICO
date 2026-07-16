from __future__ import annotations

from copy import deepcopy

from nico import mid_assessment_api as api
from nico import mid_start_guard as guard
from nico.storage import MemoryAdapter


def _request() -> api.MidAssessmentRunRequest:
    return api.MidAssessmentRunRequest(
        repository="https://github.com/Owner/Repository.git",
        customer_id="customer_guard",
        project_id="project_guard",
        authorization_confirmed=True,
        authorized=True,
        auto_continue=True,
    )


def _record(run_id: str = "midrun_existing_guard") -> dict:
    return {
        "run_id": run_id,
        "workflow": "mid_assessment",
        "status": "running",
        "repository": "owner/repository",
        "customer_id": "customer_guard",
        "project_id": "project_guard",
        "created_at": "2026-07-15T23:00:00Z",
        "updated_at": "2026-07-15T23:05:00Z",
        "request": {
            "repository": "owner/repository",
            "customer_id": "customer_guard",
            "project_id": "project_guard",
        },
        "response": {
            "status": "running",
            "run_id": run_id,
            "repository": "owner/repository",
            "current_stage": "scanner_worker",
            "progress_percent": 47,
            "scanner": {"scan_id": "scan_existing_guard", "status": "running"},
            "human_review_required": True,
            "client_ready": False,
        },
    }


def test_active_same_repository_run_is_reused_instead_of_starting_duplicate(monkeypatch) -> None:
    store = MemoryAdapter()
    existing = _record()
    store.put("assessment_runs", existing["run_id"], existing)
    monkeypatch.setattr(guard, "STORE", store)
    monkeypatch.setenv("NICO_ENABLE_MEMORY_START_GUARD", "true")
    monkeypatch.setattr(
        guard,
        "_live_state",
        lambda record, customer_id, project_id: deepcopy(record["response"]),
    )
    starts = {"count": 0}

    def fake_start(_req):
        starts["count"] += 1
        return {"status": "running", "run_id": "midrun_new_should_not_exist"}

    monkeypatch.setattr(api, "mid_assessment_response", fake_start)
    result = guard.install_mid_start_guard()
    response = api.mid_assessment_response(_request())

    assert result["server_side_duplicate_prevention"] is True
    assert result["durable_shared_state_required"] is True
    assert starts["count"] == 0
    assert response["run_id"] == existing["run_id"]
    assert response["idempotent_start_reuse"] is True
    assert response["duplicate_start_prevented"] is True
    assert response["start_guard"]["decision"] == "reuse_existing_exact_run"
    assert response["start_guard"]["cross_worker_serialization"] is True


def test_completed_report_and_review_run_releases_new_start(monkeypatch) -> None:
    store = MemoryAdapter()
    existing = _record()
    existing["status"] = "complete"
    existing["response"].update(
        {
            "status": "complete",
            "report_generation_status": "complete",
            "approval_request": {"approval_id": "approval_guard", "status": "pending"},
        }
    )
    existing["response"]["scanner"] = {"scan_id": "scan_existing_guard", "status": "complete"}
    store.put("assessment_runs", existing["run_id"], existing)
    monkeypatch.setattr(guard, "STORE", store)
    monkeypatch.setenv("NICO_ENABLE_MEMORY_START_GUARD", "true")
    monkeypatch.setattr(
        guard,
        "_live_state",
        lambda record, customer_id, project_id: deepcopy(record["response"]),
    )
    starts = {"count": 0}

    def fake_start(_req):
        starts["count"] += 1
        return {"status": "running", "run_id": "midrun_new_guard"}

    monkeypatch.setattr(api, "mid_assessment_response", fake_start)
    guard.install_mid_start_guard()
    response = api.mid_assessment_response(_request())

    assert starts["count"] == 1
    assert response["run_id"] == "midrun_new_guard"


def test_memory_only_mode_does_not_scan_shared_history_without_explicit_opt_in(monkeypatch) -> None:
    store = MemoryAdapter()
    store.put("assessment_runs", "midrun_memory_old", _record("midrun_memory_old"))
    monkeypatch.setattr(guard, "STORE", store)
    monkeypatch.delenv("NICO_ENABLE_MEMORY_START_GUARD", raising=False)
    starts = {"count": 0}

    def fake_start(_req):
        starts["count"] += 1
        return {"status": "running", "run_id": "midrun_memory_new"}

    monkeypatch.setattr(api, "mid_assessment_response", fake_start)
    guard.install_mid_start_guard()
    response = api.mid_assessment_response(_request())

    assert starts["count"] == 1
    assert response["run_id"] == "midrun_memory_new"


def test_recovery_required_exact_run_blocks_replacement() -> None:
    assert guard._blocks_new_start(
        {
            "status": "interrupted",
            "run_id": "midrun_recovery_guard",
            "recovery_required": True,
            "scanner": {"status": "recovery_required"},
        }
    ) is True


def test_terminal_failed_run_does_not_permanently_block_a_new_assessment() -> None:
    assert guard._blocks_new_start(
        {
            "status": "failed",
            "run_id": "midrun_failed_guard",
            "scanner": {"status": "failed"},
        }
    ) is False


def test_repository_identity_is_normalized_for_server_side_deduplication() -> None:
    assert guard._canonical_repository("https://github.com/Owner/Repository.git?x=1") == "owner/repository"
    assert guard._canonical_repository("owner/repository/") == "owner/repository"


def test_postgres_mode_acquires_and_releases_cross_worker_advisory_lock(monkeypatch) -> None:
    executed: list[tuple[str, tuple]] = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, sql: str, params: tuple):
            executed.append((sql, params))

        def fetchone(self):
            return {"pg_try_advisory_lock": True}

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    connection = Connection()

    class Adapter:
        def _connect(self):
            return connection

    class Store:
        adapter = Adapter()

        @staticmethod
        def status():
            return {"adapter": "postgres", "persistence_available": True}

        @staticmethod
        def list(table: str, customer_id: str | None = None, project_id: str | None = None):
            return []

    monkeypatch.setattr(guard, "STORE", Store())
    monkeypatch.setenv("NICO_MID_START_LOCK_WAIT_SECONDS", "1")

    with guard._serialized_start("nico:mid-start:customer:project:owner/repository"):
        assert connection.closed is False

    assert connection.closed is True
    assert any("pg_try_advisory_lock" in sql for sql, _ in executed)
    assert any("pg_advisory_unlock" in sql for sql, _ in executed)


def test_postgres_serialization_failure_is_fail_closed(monkeypatch) -> None:
    class Adapter:
        def _connect(self):
            raise RuntimeError("database unavailable")

    class Store:
        adapter = Adapter()

        @staticmethod
        def status():
            return {"adapter": "postgres", "persistence_available": True}

    monkeypatch.setattr(guard, "STORE", Store())

    try:
        with guard._serialized_start("nico:mid-start:test"):
            raise AssertionError("unreachable")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert exc.detail["code"] == "mid_start_guard_unavailable"
        assert exc.detail["duplicate_start_allowed"] is False
    else:
        raise AssertionError("Expected fail-closed HTTPException")
