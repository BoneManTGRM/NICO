import base64
import json
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.qualify_comprehensive_diagnostic import (
    FINAL_STAGE, accepted_capture, advance_diagnostic_run, digest, encoded, final_package,
    isolated_database, observe_worker, poll_diagnostic_run, retain,
)


def context():
    return {"run_id": "new-run", "repository": "owner/project", "commit_sha": "a" * 40,
            "report_language": "es-MX", "evidence_ledger_id": "ledger", "customer_id": "customer", "project_id": "project", "prior_stage_results": {"source": {"observed": "ñ", "failed": True}}}


def observer(tmp_path, delegate, **kwargs):
    value = context()
    identity = {k: value[k] for k in ("run_id", "repository", "commit_sha", "report_language", "evidence_ledger_id", "customer_id", "project_id")}
    return observe_worker(delegate, tmp_path, {"new-run": identity}, {"source_sha": "b" * 40}, **kwargs)


def test_exact_input_exists_before_real_delegate_and_is_preserved_after_failure(tmp_path):
    def failure(value, **kwargs):
        saved = next((tmp_path / "es-MX").glob("attempt-*/renderer-input.json"))
        assert json.loads(saved.read_bytes()) == context() == value
        assert saved.stat().st_mode & 0o777 == 0o600
        assert kwargs["max_render_seconds"] == 900
        raise TimeoutError("real renderer timeout")
    with pytest.raises(TimeoutError):
        observer(tmp_path, failure)(context(), max_render_seconds=900)
    assert (next((tmp_path / "es-MX").glob("attempt-*/renderer-input.json"))).read_bytes() == encoded(context())
    assert json.loads((next((tmp_path / "es-MX").glob("attempt-*/renderer-error.json"))).read_bytes())["error_type"] == "TimeoutError"


def test_result_failure_and_process_metadata_are_not_relabelled(tmp_path):
    result = {"status": "blocked", "reason": "source_finding"}
    process = {"worker_exit_code": 0, "render_deadline_seconds": 900}
    assert observer(tmp_path, lambda value, **kw: (result, process))(context(), max_render_seconds=900) == (result, process)
    assert json.loads((next((tmp_path / "es-MX").glob("attempt-*/renderer-result.json"))).read_bytes()) == result


@pytest.mark.parametrize("budget", [None, 0, 600, 901])
def test_missing_or_changed_renderer_budget_cannot_be_accepted(tmp_path, budget):
    with pytest.raises(ValueError, match="deadline_changed"):
        observer(tmp_path, lambda *a, **k: pytest.fail("must not render"))(context(), max_render_seconds=budget)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("field,value", [("commit_sha", "c" * 40), ("run_id", "historical"), ("report_language", "en")])
def test_context_substitution_rejected(tmp_path, field, value):
    wrong = context()
    wrong[field] = value
    with pytest.raises(ValueError, match="identity_mismatch"):
        observer(tmp_path, lambda *a, **k: pytest.fail("must not render"))(wrong, max_render_seconds=900)


def test_runtime_credential_is_rejected_before_retention(tmp_path):
    value = context()
    value["unexpected"] = "test-runtime-token"
    with pytest.raises(ValueError, match="credential"):
        observer(tmp_path, lambda *a, **k: None, secrets=["test-runtime-token"])(value, max_render_seconds=900)
    assert not list(tmp_path.iterdir())


def test_evidence_cannot_be_overwritten_or_redirected(tmp_path):
    file = tmp_path / "input.json"
    retain(file, b"original")
    with pytest.raises(FileExistsError):
        retain(file, b"replacement")
    alias = tmp_path / "alias.json"
    alias.symlink_to(file)
    with pytest.raises(FileExistsError):
        retain(alias, b"replacement")
    assert file.read_bytes() == b"original"


@pytest.mark.parametrize("url", ["", "postgres://u:p@production/nico_report_diagnostic",
    "postgres://u:p@127.0.0.1/production", "postgres://u:p@127.0.0.1/nico_report_diagnostic?host=production",
    "https://127.0.0.1/nico_report_diagnostic"])
def test_non_diagnostic_database_rejected(url):
    with pytest.raises(ValueError, match="dedicated_local"):
        isolated_database(url)


def package_record():
    identity = context()
    pdf = b"%PDF-1.4\nexample-only"
    package = {"json": {"identity": identity}, "report_language": "es-MX",
               "pdf_base64": base64.b64encode(pdf).decode(), "pdf_sha256": digest(pdf),
               "human_review_required": True, "client_delivery_allowed": False}
    record = {"status": "review_required", "terminal": True, "completed_stages": [FINAL_STAGE], "human_review_required": True, "client_delivery_allowed": False,
              "stage_results": {FINAL_STAGE: {"status": "complete", "report_package": package}}}
    return record, identity, pdf


def test_requires_exact_final_stage_bytes_not_earlier_report():
    record, identity, pdf = package_record()
    assert final_package(record, identity)[1] == pdf
    record["stage_results"]["decision_report_generation"] = record["stage_results"].pop(FINAL_STAGE)
    with pytest.raises(ValueError, match="final_stage_not_complete"):
        final_package(record, identity)


@pytest.mark.parametrize("change", ["terminal", "completed", "stage_status", "ledger", "canonical_locale"])
def test_incomplete_stage_or_wrong_canonical_identity_rejected(change):
    record, identity, _ = package_record()
    package = record["stage_results"][FINAL_STAGE]["report_package"]
    if change == "terminal": record["terminal"] = False
    elif change == "completed": record["completed_stages"] = []
    elif change == "stage_status": record["stage_results"][FINAL_STAGE]["status"] = "running"
    elif change == "ledger": package["json"]["identity"] = {**identity, "evidence_ledger_id": "other"}
    else: package["json"]["locale"] = "en"
    with pytest.raises(ValueError):
        final_package(record, identity)


@pytest.mark.parametrize("change", ["digest", "identity", "locale", "approval", "status", "review"])
def test_invalid_final_artifact_or_approval_never_counts_as_acceptance(change):
    record, identity, _ = package_record()
    package = record["stage_results"][FINAL_STAGE]["report_package"]
    if change == "digest": package["pdf_sha256"] = "0" * 64
    elif change == "identity": package["json"]["identity"] = {"run_id": "other"}
    elif change == "locale": package["report_language"] = "en"
    elif change == "approval": record["client_delivery_allowed"] = True
    elif change == "status": record["status"] = "blocked"
    else: record["review_history"] = [{"decision": "approve"}]
    with pytest.raises(ValueError):
        final_package(record, identity)


def test_normal_second_attempt_preserves_first_failure_and_binds_final_result(tmp_path):
    record, identity, pdf = package_record()
    result = record["stage_results"][FINAL_STAGE]
    calls = []
    def delegate(value, **kwargs):
        calls.append(value)
        if len(calls) == 1:
            raise TimeoutError()
        return result, {"render_deadline_seconds": 900}
    invoke = observer(tmp_path, delegate)
    with pytest.raises(TimeoutError):
        invoke(context(), max_render_seconds=900)
    invoke(context(), max_render_seconds=900)
    assert len(calls) == 2
    bound_identity = {k: identity[k] for k in ("run_id", "repository", "commit_sha", "report_language", "evidence_ledger_id", "customer_id", "project_id")}
    capture = accepted_capture(tmp_path, bound_identity, {"source_sha": "b" * 40}, digest(pdf))
    assert capture["input_sha256"] == digest(encoded(context()))
    assert len(list((tmp_path / "es-MX").glob("attempt-*/renderer-error.json"))) == 1
    assert len(list((tmp_path / "es-MX").glob("attempt-*/renderer-input.json"))) == 2


def test_missing_capture_or_substituted_retained_bytes_cannot_pass(tmp_path):
    record, identity, pdf = package_record()
    bound_identity = {k: identity[k] for k in ("run_id", "repository", "commit_sha", "report_language", "evidence_ledger_id", "customer_id", "project_id")}
    producer = {"source_sha": "b" * 40}
    with pytest.raises(ValueError, match="not_unique"):
        accepted_capture(tmp_path, bound_identity, producer, digest(pdf))
    observer(tmp_path, lambda *a, **k: (record["stage_results"][FINAL_STAGE], {"render_deadline_seconds": 900}))(
        context(), max_render_seconds=900)
    path = next((tmp_path / "es-MX").glob("attempt-*/renderer-input.json"))
    path.write_bytes(b'{}')
    with pytest.raises(ValueError, match="artifact_mismatch"):
        accepted_capture(tmp_path, bound_identity, producer, digest(pdf))


@pytest.fixture
def active_publication(tmp_path, monkeypatch):
    from nico import comprehensive_final_report_background_v1 as background
    from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
    from nico.comprehensive_run_record import apply_comprehensive_stage_result, create_comprehensive_run_record
    from nico.comprehensive_run_store import ComprehensiveRunStore

    store = ComprehensiveRunStore(lambda: sqlite3.connect(tmp_path / "observation.sqlite"))
    store.ensure_schema()
    identity = {key: value for key, value in context().items() if key != "prior_stage_results"}
    record = create_comprehensive_run_record(**identity, authorized=True)
    for stage in COMPREHENSIVE_STAGES:
        if stage == FINAL_STAGE:
            break
        record = apply_comprehensive_stage_result(record, stage_id=stage, result={"status": "complete"})
    lease = "frpub_diagnostic_observation"
    now = time.time()
    record = apply_comprehensive_stage_result(record, stage_id=FINAL_STAGE,
        result=background._running_result(context(), lease_id=lease, started_epoch=now))
    store.create(record)
    store.create_final_report_job(lease_id=lease, run_id="new-run", status="rendering",
        started_epoch=now, heartbeat_epoch=now, updated_at=record["updated_at"])

    stop, release = threading.Event(), threading.Event()
    worker = threading.Thread(target=release.wait, daemon=True)
    worker.start()
    state = {"stop": stop, "invoke_thread": worker}
    monkeypatch.setitem(background._LOCAL_TASKS, lease, state)
    service = SimpleNamespace(_store=store, resume=Mock(side_effect=lambda run_id, **kw: store.load(run_id)))
    yield SimpleNamespace(service=service, store=store, record=record, lease=lease,
                          stop=stop, release=release, worker=worker)
    stop.set()
    release.set()
    worker.join(timeout=2)


@pytest.mark.parametrize("status", ["queued", "rendering", "running"])
def test_live_publication_observation_avoids_canonical_load_without_stopping_worker(active_publication, monkeypatch, status):
    case = active_publication
    case.store.update_final_report_job(case.lease, status=status, heartbeat_epoch=time.time(), updated_at="now")
    load = Mock(wraps=case.store.load)
    monkeypatch.setattr(case.store, "load", load)
    before = encoded(case.record)
    for _ in range(3):
        assert advance_diagnostic_run(case.service, "new-run", case.record) is case.record
    load.assert_not_called()
    case.service.resume.assert_not_called()
    assert not case.stop.is_set() and case.worker.is_alive()
    assert encoded(case.record) == before


@pytest.mark.parametrize("status", ["complete", "blocked", "failed", "cancelled", "superseded", "expired"])
def test_every_terminal_lease_refreshes_canonical_record_once(active_publication, status):
    case = active_publication
    case.store.update_final_report_job(case.lease, status=status, heartbeat_epoch=time.time(), updated_at="now")
    refreshed = advance_diagnostic_run(case.service, "new-run", case.record)
    assert refreshed == case.record and refreshed is not case.record
    case.service.resume.assert_called_once_with("new-run", max_stages=1)


@pytest.mark.parametrize("column,value", [
    ("revision", 999), ("integrity_sha256", "changed"), ("status", "blocked"),
    ("terminal", 1), ("customer_id", "other"), ("project_id", "other"),
    ("repository", "other/repo"), ("commit_sha", "b" * 40), ("evidence_ledger_id", "other"),
])
def test_canonical_revision_cancellation_or_identity_change_refreshes_despite_live_worker(active_publication, column, value):
    case = active_publication
    with case.store._connection() as connection:
        connection.execute(f"UPDATE nico_comprehensive_runs SET {column} = ? WHERE run_id = ?", (value, "new-run"))
        connection.commit()
    advance_diagnostic_run(case.service, "new-run", case.record)
    case.service.resume.assert_called_once_with("new-run", max_stages=1)
    assert case.worker.is_alive() and not case.stop.is_set()


@pytest.mark.parametrize("change", ["missing", "wrong_run", "stale_heartbeat", "render_deadline", "queue_deadline", "missing_start"])
def test_missing_stale_or_overdue_lease_uses_existing_recovery_path(active_publication, change):
    from nico import comprehensive_final_report_background_v1 as background

    case = active_publication
    now = time.time()
    with case.store._connection() as connection:
        if change == "missing":
            connection.execute("DELETE FROM nico_comprehensive_final_report_jobs WHERE lease_id = ?", (case.lease,))
        elif change == "wrong_run":
            connection.execute("UPDATE nico_comprehensive_final_report_jobs SET run_id = 'other' WHERE lease_id = ?", (case.lease,))
        elif change == "stale_heartbeat":
            connection.execute("UPDATE nico_comprehensive_final_report_jobs SET heartbeat_epoch = ? WHERE lease_id = ?",
                (now - background._orphan_seconds() - 1, case.lease))
        else:
            status = "queued" if change == "queue_deadline" else "rendering"
            budget = background._max_queue_seconds() if status == "queued" else background._max_publication_seconds()
            started = 0 if change == "missing_start" else now - budget - 1
            connection.execute("UPDATE nico_comprehensive_final_report_jobs SET status = ?, started_epoch = ? WHERE lease_id = ?",
                (status, started, case.lease))
        connection.commit()
    advance_diagnostic_run(case.service, "new-run", case.record)
    case.service.resume.assert_called_once_with("new-run", max_stages=1)


@pytest.mark.parametrize("change", ["stopped", "exited", "orphaned"])
def test_cancelled_or_missing_local_worker_returns_to_bounded_resume(active_publication, change):
    from nico import comprehensive_final_report_background_v1 as background

    case = active_publication
    if change == "stopped":
        case.stop.set()
    elif change == "exited":
        case.release.set()
        case.worker.join(timeout=2)
    else:
        background._LOCAL_TASKS.pop(case.lease)
    advance_diagnostic_run(case.service, "new-run", case.record)
    case.service.resume.assert_called_once_with("new-run", max_stages=1)


def test_observation_error_falls_back_and_does_not_hide_canonical_failure(active_publication, monkeypatch):
    case = active_publication
    monkeypatch.setattr(case.store, "_connection", Mock(side_effect=OSError("observation failed")))
    case.service.resume.side_effect = RuntimeError("canonical read failed")
    with pytest.raises(RuntimeError, match="canonical read failed"):
        advance_diagnostic_run(case.service, "new-run", case.record)
    case.service.resume.assert_called_once_with("new-run", max_stages=1)


def test_completion_acceptance_uses_refreshed_canonical_result(active_publication):
    case = active_publication
    completed, identity, pdf = package_record()
    case.service.resume.side_effect = None
    case.service.resume.return_value = completed
    case.store.update_final_report_job(case.lease, status="complete", heartbeat_epoch=time.time(), updated_at="now")
    refreshed = advance_diagnostic_run(case.service, "new-run", case.record)
    assert refreshed is completed
    assert final_package(refreshed, identity)[1] == pdf
    with pytest.raises(ValueError, match="not_review_ready"):
        final_package(case.record, identity)
    case.service.resume.assert_called_once_with("new-run", max_stages=1)


def test_polling_keeps_two_second_cadence_then_returns_fresh_completion(active_publication, monkeypatch):
    case = active_publication
    completed, identity, pdf = package_record()
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            case.store.update_final_report_job(case.lease, status="complete", heartbeat_epoch=time.time(), updated_at="now")
            case.service.resume.side_effect = None
            case.service.resume.return_value = completed
    monkeypatch.setattr("scripts.qualify_comprehensive_diagnostic.time.sleep", sleep)
    result = poll_diagnostic_run(case.service, "new-run", case.record, started=time.monotonic(), language="es-MX")
    assert sleeps == [2, 2]
    assert result is completed
    assert final_package(result, identity)[1] == pdf
    case.service.resume.assert_called_once_with("new-run", max_stages=1)


def test_whole_run_deadline_still_expires_while_only_observing_live_worker(active_publication, monkeypatch):
    case = active_publication
    clock = [5399.0]
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr("scripts.qualify_comprehensive_diagnostic.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("scripts.qualify_comprehensive_diagnostic.time.sleep", sleep)
    with pytest.raises(TimeoutError, match="diagnostic_whole_run_deadline"):
        poll_diagnostic_run(case.service, "new-run", case.record, started=0.0, language="es-MX")
    assert sleeps == [2]
    assert not case.stop.is_set() and case.worker.is_alive()
    case.service.resume.assert_not_called()
