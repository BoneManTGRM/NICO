from __future__ import annotations

import hashlib
import json
import logging

import pytest

from nico import report_delivery_timing_v1 as timing

RUN = "comprun_" + "a" * 32
PHASES = {
    "phase17_source_tables", "phase17_prepare", "phase17_single_pass",
    "phase17_quality_repair", "phase17_reconcile", "phase17_phase2_truth",
    "phase17_sanitize", "phase17_language_authority", "phase17_finalize",
    "phase17_final_truth_hash", "phase17_source_validation",
}


def _event(caplog):
    events = [
        json.loads(record.getMessage().split("=", 1)[1])
        for record in caplog.records
        if record.getMessage().startswith("NICO_REPORT_TIMING=")
    ]
    return events[-1]


def test_disabled_call_preserves_arguments_return_and_no_event(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    supplied, returned = object(), object()

    def producer(value, *, token):
        assert value is supplied and token is supplied
        return returned

    assert timing.report_delivery_call("owned_call", producer, supplied, token=supplied) is returned
    assert not caplog.records


def test_active_call_is_body_free_and_does_not_cache_results(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    outputs = [object(), object()]
    secret = "OWNED_TEST_BODY_AND_CREDENTIAL_SENTINEL"
    calls = []

    def producer(value):
        calls.append(value)
        return outputs[len(calls) - 1]

    with timing.report_delivery_timing(RUN, "en"):
        assert timing.report_delivery_call("owned_call", producer, secret) is outputs[0]
        assert timing.report_delivery_call("owned_call", producer, secret) is outputs[1]
    event = _event(caplog)
    assert calls == [secret, secret]
    assert secret not in json.dumps(event)
    assert event["phases"]["owned_call"]["calls"] == 2
    assert set(event["phases"]["owned_call"]) == {"calls", "elapsed_ms", "thread_cpu_ms"}
    assert event["http_transfer_completion_inferred"] is False


@pytest.mark.parametrize("active", [False, True])
def test_call_preserves_exact_exception_and_resets_scope(active, caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    failure = ValueError("OWNED_PRIVATE_ERROR_SENTINEL")

    def producer():
        raise failure

    with pytest.raises(ValueError) as caught:
        if active:
            with timing.report_delivery_timing(RUN, "en"):
                timing.report_delivery_call("owned_failure", producer)
        else:
            timing.report_delivery_call("owned_failure", producer)
    assert caught.value is failure
    assert timing._ACTIVE.get() is None
    if active:
        event = _event(caplog)
        assert event["outcome"] == "failed"
        assert event["error_type"] == "ValueError"
        assert event["phases"]["owned_failure"]["calls"] == 1
        assert "OWNED_PRIVATE_ERROR_SENTINEL" not in json.dumps(event)
    else:
        assert not caplog.records


@pytest.mark.parametrize("fails", [False, True])
def test_broken_logger_does_not_replace_return_or_error(monkeypatch, fails):
    returned, failure = object(), RuntimeError("owned failure")

    def logger(*args, **kwargs):
        raise OSError("owned logging failure")

    monkeypatch.setattr(timing._LOGGER, "info", logger)

    def producer():
        if fails:
            raise failure
        return returned

    if fails:
        with pytest.raises(RuntimeError) as caught:
            with timing.report_delivery_timing(RUN, "en"):
                timing.report_delivery_call("owned_call", producer)
        assert caught.value is failure
    else:
        with timing.report_delivery_timing(RUN, "en"):
            assert timing.report_delivery_call("owned_call", producer) is returned


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_phase17_times_actual_order_and_late_bound_finalizer(monkeypatch, caplog, language):
    from nico import client_report_completion_v2 as completion
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    from nico import source_table_export_binding as tables
    from nico import comprehensive_spanish_final_report_runtime_cache_v94 as cache

    caplog.set_level(logging.INFO, logger="uvicorn.error")
    steps = []
    package = {"json": {"owned": "OWNED_INPUT_SENTINEL"}}
    source_tables = object()
    rendered = {"json": {"report_language": language}}
    finalized = {"json": {"owned": "OWNED_FINAL_SENTINEL"}}

    def stage(name, result):
        def called(*args):
            steps.append(name)
            return result
        return called

    monkeypatch.setattr(tables, "capture_source_table_evidence", stage("capture", source_tables))
    monkeypatch.setattr(phase17, "_prepare_client_artifact_package", stage("prepare", package))
    monkeypatch.setattr(phase17, "rebuild_single_pass_premium_artifacts", stage("render", rendered))
    monkeypatch.setattr(phase17, "_is_spanish", lambda canonical: language == "es-MX")
    monkeypatch.setattr(phase17, "repair_rendered_report", stage("repair-en", rendered))
    monkeypatch.setattr(phase17, "repair_localized_rendered_report", stage("repair-es", rendered))
    monkeypatch.setattr(phase17, "_reconcile", stage("reconcile", rendered))
    monkeypatch.setattr(phase17, "_phase2_review_truth_node", stage("phase2", rendered))
    monkeypatch.setattr(phase17, "_sanitize_published_artifacts", stage("sanitize", rendered))
    monkeypatch.setattr(phase17, "canonical_sha256", stage("hash", "d" * 64))

    def stale(*args):
        pytest.fail("finalizer captured before language authority was reasserted")

    def fresh(value):
        assert value is rendered
        steps.append("finalize")
        return finalized

    monkeypatch.setattr(completion, "finalize_client_report_package", stale)

    def reassert():
        steps.append("authority")
        completion.finalize_client_report_package = fresh

    monkeypatch.setattr(phase17, "_reassert_terminal_report_language_authority", reassert)

    def validate(captured, value):
        assert captured is source_tables and value is finalized
        assert value["canonical_truth_sha256"] == "d" * 64
        steps.append("validate")

    monkeypatch.setattr(tables, "validate_source_table_evidence", validate)
    monkeypatch.setattr(cache, "release_comprehensive_spanish_render_input_cache_v94", stage("release", None))
    with timing.report_delivery_timing(RUN, language):
        assert phase17.rebuild_client_artifacts(package) is finalized
    assert steps == [
        "capture", "prepare", "render", "repair-es" if language == "es-MX" else "repair-en",
        "reconcile", "phase2", "sanitize", "authority", "finalize", "hash", "validate", "release",
    ]
    event = _event(caplog)
    assert PHASES <= set(event["phases"])
    assert all(event["phases"][name]["calls"] == 1 for name in PHASES)
    assert "OWNED_INPUT_SENTINEL" not in json.dumps(event)
    assert "OWNED_FINAL_SENTINEL" not in json.dumps(event)


def test_phase17_failure_keeps_original_error_and_releases_inputs(monkeypatch, caplog):
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    from nico import source_table_export_binding as tables
    from nico import comprehensive_spanish_final_report_runtime_cache_v94 as cache

    caplog.set_level(logging.INFO, logger="uvicorn.error")
    failure, released = RuntimeError("OWNED_INPUT_SENTINEL"), []
    monkeypatch.setattr(tables, "capture_source_table_evidence", lambda value: object())

    def fail(value):
        raise failure

    monkeypatch.setattr(phase17, "_prepare_client_artifact_package", fail)
    monkeypatch.setattr(cache, "release_comprehensive_spanish_render_input_cache_v94", lambda: released.append(True))
    with pytest.raises(RuntimeError) as caught:
        with timing.report_delivery_timing(RUN, "en"):
            phase17.rebuild_client_artifacts({"json": {}})
    assert caught.value is failure
    assert released == [True]
    event = _event(caplog)
    assert event["phases"]["phase17_prepare"]["calls"] == 1
    assert "phase17_single_pass" not in event["phases"]
    assert "OWNED_INPUT_SENTINEL" not in json.dumps(event)


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_installed_pipeline_timing_keeps_exact_owned_pdf_and_truth(language, caplog):
    # The tracked public fixture installs specialist-first production wrappers.
    from copy import deepcopy
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from nico import comprehensive_same_run_locale_report_v1 as locale

    caplog.set_level(logging.INFO, logger="uvicorn.error")
    status = _fixed_status("es-MX" if language == "en" else "en")
    baseline = locale.build_same_run_locale_pdf_response(deepcopy(status), language)
    with timing.report_delivery_timing(RUN, language):
        observed = locale.build_same_run_locale_pdf_response(deepcopy(status), language)
    assert observed.body == baseline.body
    assert hashlib.sha256(observed.body).hexdigest() == baseline.headers["X-NICO-PDF-SHA256"]
    assert observed.headers == baseline.headers
    event = _event(caplog)
    assert PHASES <= set(event["phases"])
    assert "locale_localized_draft_view" in event["phases"]
    assert "locale_truth_projection" in event["phases"]
