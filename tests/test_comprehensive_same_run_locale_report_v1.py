from __future__ import annotations

import base64
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI

from nico import comprehensive_same_run_locale_report_v1 as subject


def _canonical() -> dict:
    return {
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_same_run_1",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_same_run_1",
            "customer_id": "customer_same_run_1",
            "project_id": "project_same_run_1",
            "generated_at": "2026-08-24T20:00:00Z",
        },
        "assessment": {
            "maturity_signal": {"score": 93, "presented_score": 93},
            "sections": [],
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
        },
        "stage_summaries": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _status(*, source_language: str = "en") -> dict:
    canonical = _canonical()
    return {
        "run_id": canonical["identity"]["run_id"],
        "repository": canonical["identity"]["repository"],
        "commit_sha": canonical["identity"]["commit_sha"],
        "report_language": source_language,
        "terminal": True,
        "integrity_sha256": "run-integrity",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "reports": {
            "report_id": "comprehensive_report_same_run_1",
            "canonical_truth_sha256": subject._canonical_hash(canonical),
            "json": canonical,
            "markdown": "# source report",
            "html": "<article>source report</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nsource").decode("ascii"),
        },
    }


def test_alternate_locale_uses_same_canonical_run_without_mutating_source(monkeypatch):
    status = _status(source_language="en")
    before = deepcopy(status)

    monkeypatch.setattr(
        subject,
        "_render_target",
        lambda canonical, report_language: {
            "markdown": "# informe",
            "html": "<article>informe</article>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\nes-MX").decode("ascii"),
            "pdf_sha256": "localized-pdf-sha",
            "pdf_page_count": 44,
        },
    )

    result = subject.build_same_run_locale_report(status, "es-MX")

    assert status == before
    assert result["run_id"] == status["run_id"]
    assert result["source_report_id"] == status["reports"]["report_id"]
    assert result["source_report_language"] == "en"
    assert result["report_language"] == "es-MX"
    assert result["same_canonical_run"] is True
    assert result["assessment_rerun"] is False
    assert result["canonical_truth_preserved"] is True
    assert result["canonical_truth_sha256"] == status["reports"]["canonical_truth_sha256"]
    assert result["report"]["json"] == status["reports"]["json"]
    assert result["report"]["presentation_language"] == "es-MX"
    assert result["report"]["pdf_page_count"] == 44
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["approval_state_mutated"] is False
    assert result["delivery_state_mutated"] is False


def test_source_locale_reuses_terminal_artifacts_without_rerender(monkeypatch):
    status = _status(source_language="en")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("source locale should reuse the frozen terminal artifacts")

    monkeypatch.setattr(subject, "_render_target", fail_if_called)
    result = subject.build_same_run_locale_report(status, "en")

    assert result["report"]["markdown"] == status["reports"]["markdown"]
    assert result["report"]["html"] == status["reports"]["html"]
    assert result["report"]["pdf_base64"] == status["reports"]["pdf_base64"]
    assert result["assessment_rerun"] is False


def test_canonical_truth_mismatch_fails_closed(monkeypatch):
    status = _status()
    status["reports"]["canonical_truth_sha256"] = "0" * 64
    monkeypatch.setattr(subject, "_render_target", lambda *args, **kwargs: {})

    with pytest.raises(ValueError, match="canonical_truth_hash_mismatch"):
        subject.build_same_run_locale_report(status, "es-MX")


def test_non_terminal_run_cannot_publish_localized_report():
    status = _status()
    status["terminal"] = False

    with pytest.raises(ValueError, match="terminal_report_required"):
        subject.build_same_run_locale_report(status, "es-MX")


def test_only_english_and_mexican_spanish_are_supported():
    assert subject._normalize_report_language("en") == "en"
    assert subject._normalize_report_language("ES-mx") == "es-MX"
    with pytest.raises(ValueError, match="unsupported_report_language"):
        subject._normalize_report_language("fr")


def test_route_installs_exactly_once_and_preserves_delivery_boundary():
    app = FastAPI()

    first = subject.install_same_run_locale_report(app)
    second = subject.install_same_run_locale_report(app)

    assert first["route_count"] == 1
    assert second["route_count"] == 1
    assert second["same_canonical_run"] is True
    assert second["assessment_rerun"] is False
    assert second["canonical_truth_preserved"] is True
    assert second["human_review_required"] is True
    assert second["client_delivery_allowed"] is False


def test_production_docker_entrypoint_mounts_same_run_locale_wrapper():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "nico.api.same_run_locale_report_bootstrap:app" in dockerfile
