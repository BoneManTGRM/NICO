import base64
import json

import pytest

from scripts.qualify_comprehensive_diagnostic import (
    FINAL_STAGE, accepted_capture, digest, encoded, final_package, isolated_database, observe_worker, retain,
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
