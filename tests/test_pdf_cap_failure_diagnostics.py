import copy
import io
import json
import logging

import pytest
from pypdf import PdfReader

from test_client_pdf_compose_v2 import _pdf
from nico.client_pdf_compose_v2 import compose_compact_client_pdf


def test_required_page_failure_retains_bounded_counts():
    with pytest.raises(ValueError) as caught:
        compose_compact_client_pdf(
            _pdf(["Executive Decision Brief"]),
            _pdf(*[["Register"] for _ in range(60)]),
            _pdf(["Gate"]),
            page_limit=60,
        )
    assert type(caught.value) is ValueError
    assert str(caught.value) == "client-ready PDF required pages exceed the 60-page boundary"
    diagnostic = caught.value.pdf_cap_diagnostic
    assert diagnostic["required_pages"] == 61
    assert diagnostic["base_pages"] == 1
    assert diagnostic["total_pages"] == 62
    assert diagnostic["review_pages"] == 0


def _total_failure():
    base = _pdf(*[["Executive Decision Brief", str(i)] for i in range(57)])
    component = _pdf(["Required component"])
    with pytest.raises(ValueError) as caught:
        compose_compact_client_pdf(base, component, component, review_pdf=component,
                                  ci_boundary_pdf=component, human_evidence_pdf=component, page_limit=60)
    assert type(caught.value) is ValueError
    assert str(caught.value) == "client-ready PDF cannot preserve every primary and required page within the 60-page boundary: 62"
    return caught.value


def test_total_failure_counts_identity_and_single_log(monkeypatch, caplog):
    from nico.pdf_cap_failure_diagnostics import pdf_cap_identity
    run_id = "comprun_" + "a" * 32
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "b" * 40)
    with caplog.at_level(logging.INFO, logger="uvicorn.error"), pdf_cap_identity(run_id):
        error = _total_failure()
    data = error.pdf_cap_diagnostic
    assert data["required_pages"] == 5
    assert data["base_pages"] == data["retained_body_pages_before_reflow"] == data["retained_body_pages_after_reflow"] == 57
    assert data["reflow_attempted"] is True
    assert data["run_id"] == run_id and data["release_commit_sha"] == "b" * 40
    logs = [r.getMessage() for r in caplog.records if r.getMessage().startswith("NICO_PDF_CAP_FAILURE=")]
    assert len(logs) == 1
    assert json.loads(logs[0].split("=", 1)[1]) == data
    assert data["reportlab_version"] != "unavailable"
    assert _total_failure().pdf_cap_diagnostic["run_id"] == "unavailable"


def test_success_reflow_keeps_bytes_and_never_collects_diagnostic(monkeypatch, caplog):
    from nico import comprehensive_pdf_reflow_v1 as reflow
    from nico import pdf_cap_failure_diagnostics as diagnostic
    base = _pdf(*[["Executive Decision Brief", str(i)] for i in range(59)])
    component = _pdf(["Required"])
    snapshot = (base, component)
    calls = []

    def compact(body):
        calls.append(len(PdfReader(io.BytesIO(body)).pages))
        return _pdf(*[["Executive Decision Brief", str(i)] for i in range(58)]), {}

    monkeypatch.setattr(reflow, "compact_sparse_stage_pages", compact)
    monkeypatch.setattr(diagnostic, "_runtime_identity", lambda: pytest.fail("success collected failure identity"))
    result = compose_compact_client_pdf(base, component, component, page_limit=60)
    assert len(PdfReader(io.BytesIO(result)).pages) == 60
    assert calls == [59]
    assert (base, component) == snapshot
    assert not any("NICO_PDF_CAP_FAILURE=" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("key,value", [("required_pages", 99), ("total_pages", 1),
    ("base_pages", True), ("register_pages", -1), ("review_pages", 1.5),
    ("reflow_attempted", "true"), ("page_limit", 0),
    ("retained_body_pages_before_reflow", 0)])
def test_malformed_counts_rejected(key, value):
    from nico.pdf_cap_failure_diagnostics import sanitize_pdf_cap_diagnostic
    data = _total_failure().pdf_cap_diagnostic
    data[key] = value
    assert sanitize_pdf_cap_diagnostic(data) is None


def test_untrusted_fields_are_not_retained(monkeypatch):
    from nico.pdf_cap_failure_diagnostics import sanitize_pdf_cap_diagnostic
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "secret/path\nvalue")
    monkeypatch.setenv("NICO_RELEASE_COMMIT_SHA", "a" * 40)
    data = _total_failure().pdf_cap_diagnostic
    assert data["release_commit_sha"] == "unavailable"
    data.update(run_id="secret/path", stage_id="secret/path", reportlab_version="secret/path",
                composer_version="secret/path", report_text="SECRET", arbitrary={"nested": "SECRET"})
    data["font_registration"] = {"Helvetica": "secret/path", "SECRET": "other"}
    clean = sanitize_pdf_cap_diagnostic(data)
    assert clean["stage_id"] == "final_comprehensive_report_generation"
    assert clean["run_id"] == clean["reportlab_version"] == clean["composer_version"] == "unavailable"
    assert "SECRET" not in json.dumps(clean) and "secret/path" not in json.dumps(clean)


def test_logging_failure_preserves_exception_and_attribute(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("logger unavailable")
    monkeypatch.setattr(logging.getLogger("uvicorn.error"), "info", fail)
    assert _total_failure().pdf_cap_diagnostic["total_pages"] == 62


def test_identity_collection_failure_preserves_counts(monkeypatch):
    from nico import pdf_cap_failure_diagnostics as diagnostic
    def fail():
        raise RuntimeError("metadata unavailable")
    monkeypatch.setattr(diagnostic, "_runtime_identity", fail)
    data = _total_failure().pdf_cap_diagnostic
    assert data["total_pages"] == 62 and data["run_id"] == "unavailable"


@pytest.mark.parametrize("malformed", [False, True])
def test_blocked_provider_persists_only_sanitized_diagnostic(monkeypatch, malformed):
    from nico import v2_production_authority as authority
    source = {"status": "complete", "report_package": {"json": {"identity": {"run_id": "comprun_" + "c" * 32}}}}
    original = copy.deepcopy(source)
    monkeypatch.setattr(authority, "_canonical_source", lambda context: (source, context, 0))
    monkeypatch.setattr(authority, "_inject_live_runtime_truth", lambda result, context: result)
    monkeypatch.setattr(authority, "_reassert_terminal_report_language_authority", lambda: {"bound": True})

    def finalizer(result):
        error = _total_failure()
        error.pdf_cap_diagnostic["unexpected"] = "SECRET"
        if malformed:
            error.pdf_cap_diagnostic["total_pages"] = -1
        raise error

    monkeypatch.setattr(authority, "finalize_report_package", finalizer)
    result = authority.wrap_final_report_publication(lambda _: pytest.fail("legacy called"))({})
    assert result["status"] == "blocked"
    assert result["reason"].endswith("60-page boundary: 62")
    data = result["v2_production_authority"].get("pdf_cap_diagnostic")
    if malformed:
        assert data is None
    else:
        assert data["run_id"] == "comprun_" + "c" * 32
        assert "SECRET" not in json.dumps(data)
    assert source == original
    assert result["human_review_required"] is True and result["client_delivery_allowed"] is False
