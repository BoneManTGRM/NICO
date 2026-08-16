from __future__ import annotations

import base64
import io
from typing import Any

import pytest
from pypdf import PdfReader

from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_report_language_truth_v77 as language_truth
from nico import phase17_canonical_artifact_rebuild_v1 as phase17
from nico import v2_production_authority as production
from nico import v2_report_quality_repairs as quality
from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source


GENERATED_AT = "2026-08-16T12:55:00Z"


def _canonical(*, stale_root: str, identity_language: str) -> dict[str, Any]:
    duplicate = {
        "finding_id": "ARCH-1",
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "priority": "P1",
        "status": "open",
        "recommendation": "Split orchestration from presentation logic.",
        "acceptance_criteria": [
            "Operations route complexity is reduced [method: static analysis]",
            "Operations route complexity is reduced [target commit: abc123]",
        ],
    }
    return {
        "service_id": "comprehensive",
        "report_language": stale_root,
        "locale": stale_root,
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "abc123",
            "run_id": "comprun_publication_state_regression",
            "customer_id": "customer-publication-state",
            "project_id": "project-publication-state",
            "evidence_ledger_id": "ledger-publication-state",
            "generated_at": GENERATED_AT,
            "report_language": identity_language,
        },
        "generated_at": GENERATED_AT,
        "findings_register": [duplicate, dict(duplicate)],
        "executive_findings": [
            {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
        ],
        "roadmap": [
            {
                "work_packages": [
                    {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
                ]
            }
        ],
        "backlog": [
            {"finding_id": "ARCH-1", "title": "High-complexity code hotspot"}
        ],
        "assessment": {
            "report_language": stale_root,
            "locale": stale_root,
            "executive_summary": "Production assessment completed for review.",
        },
    }


def _source(*, stale_root: str, identity_language: str) -> dict[str, Any]:
    return {
        "status": "complete",
        "report_language": stale_root,
        "locale": stale_root,
        "report_package": {
            "json": _canonical(
                stale_root=stale_root,
                identity_language=identity_language,
            ),
            "generated_at": GENERATED_AT,
            "pdf_filename": "nico-report-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf",
            "spanish_pdf_filename": "nico-report-es-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf",
            "pdf_base64": base64.b64encode(b"%PDF-1.4 proof").decode("ascii"),
        },
    }


def _report_context(*, language: str) -> dict[str, Any]:
    return {
        "run_id": "comprun_publication_state_regression",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "report_language": language,
        "locale": language,
        "prior_stage_results": {},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _pdf_text(encoded: str) -> str:
    pdf = base64.b64decode(encoded)
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def _assert_language(result: dict[str, Any], language: str) -> None:
    assert result["status"] == "complete", result.get("reason")
    package = result["report_package"]
    canonical = package["json"]
    expected = (
        language_truth._ES_BOUNDARY_MARKERS
        if language == "es-MX"
        else language_truth._EN_BOUNDARY_MARKERS
    )
    opposite = (
        language_truth._EN_BOUNDARY_MARKERS
        if language == "es-MX"
        else language_truth._ES_BOUNDARY_MARKERS
    )
    surfaces = (
        str(package["markdown"]),
        str(package["html"]),
        _pdf_text(str(package["pdf_base64"])),
    )

    assert language_truth.resolve_report_language(canonical) == language
    assert canonical["identity"]["report_language"] == language
    assert canonical["report_language"] == language
    assert package["report_language"] == language
    for surface in surfaces:
        for marker in expected:
            assert marker in surface
        for marker in opposite:
            assert marker not in surface
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    authority = result["v2_production_authority"]
    assert authority["canonical_report_language_outranks_runtime_projection"] is True
    assert authority["terminal_report_language_reasserted_per_publication"] is True


def test_persisted_spanish_run_identity_outranks_stale_runtime_english(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source(stale_root="en", identity_language="es-MX")
    stale_runtime = _report_context(language="en")
    monkeypatch.setattr(
        production,
        "_canonical_source",
        lambda context: (source, stale_runtime, 0.0),
    )
    wrapped = production.wrap_final_report_publication(
        lambda context: pytest.fail("canonical source must not use legacy rendering")
    )

    result = wrapped(dict(stale_runtime))

    _assert_language(result, "es-MX")
    assert "client report omitted CI/CD boundary: A. CI/CD configuration maturity:" not in str(
        result
    )


def test_same_process_english_spanish_english_publications_do_not_leak_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def canonical_source(context: dict[str, Any]):
        identity_language = str(context["identity_language"])
        runtime_language = str(context["runtime_language"])
        source = _source(
            stale_root=runtime_language,
            identity_language=identity_language,
        )
        return source, _report_context(language=runtime_language), 0.0

    monkeypatch.setattr(production, "_canonical_source", canonical_source)
    wrapped = production.wrap_final_report_publication(
        lambda context: pytest.fail("canonical source must not use legacy rendering")
    )

    english_first = wrapped(
        {"identity_language": "en", "runtime_language": "en"}
    )
    spanish_second = wrapped(
        {"identity_language": "es-MX", "runtime_language": "en"}
    )
    english_third = wrapped(
        {"identity_language": "en", "runtime_language": "es-MX"}
    )

    _assert_language(english_first, "en")
    _assert_language(spanish_second, "es-MX")
    _assert_language(english_third, "en")


def test_late_global_language_binding_drift_is_repaired_before_next_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"identity_language": "en", "runtime_language": "en"}

    def canonical_source(_context: dict[str, Any]):
        source = _source(
            stale_root=state["runtime_language"],
            identity_language=state["identity_language"],
        )
        return source, _report_context(language=state["runtime_language"]), 0.0

    monkeypatch.setattr(production, "_canonical_source", canonical_source)
    wrapped = production.wrap_final_report_publication(
        lambda context: pytest.fail("canonical source must not use legacy rendering")
    )

    first = wrapped({})
    _assert_language(first, "en")

    def stale_explicit_language(canonical):
        return "en", "simulated:late-root-default"

    monkeypatch.setattr(language_truth, "_explicit_language", stale_explicit_language)
    monkeypatch.setattr(final_truth, "_report_language", lambda canonical: "en")
    monkeypatch.setattr(
        final_truth,
        "_ci_boundary_markers",
        lambda canonical: language_truth._EN_BOUNDARY_MARKERS,
    )
    monkeypatch.setattr(
        final_truth,
        "_ci_lines",
        lambda canonical: list(language_truth._EN_BOUNDARY_MARKERS),
    )
    previous_validator = getattr(final_truth._validate_surfaces, "_nico_previous", None)
    if callable(previous_validator):
        monkeypatch.setattr(final_truth, "_validate_surfaces", previous_validator)
    monkeypatch.setattr(phase17, "_is_spanish", lambda canonical: False)
    monkeypatch.setattr(quality, "_is_spanish", lambda canonical: False)

    state.update({"identity_language": "es-MX", "runtime_language": "en"})
    second = wrapped({})

    _assert_language(second, "es-MX")
    assert production._report_language(
        _report_context(language="en"),
        second["report_package"]["json"],
    ) == "es-MX"


def test_canonical_report_source_persists_run_language_on_every_authoritative_surface() -> None:
    context = {
        "run_id": "comprun_canonical_language_source",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "evidence_ledger_id": "ledger-canonical-language",
        "customer_id": "customer-canonical-language",
        "project_id": "project-canonical-language",
        "generated_at": GENERATED_AT,
        "report_language": "es-MX",
        "locale": "es-MX",
        "prior_stage_results": {
            "immutable_repository_snapshot": {
                "status": "complete",
                "summary": "Immutable repository snapshot captured.",
                "evidence": {"commit_sha": "abc123"},
            }
        },
    }

    source = build_canonical_report_source(context)

    assert source["status"] == "complete", source.get("reason")
    package = source["report_package"]
    canonical = package["json"]
    assert source["report_language"] == "es-MX"
    assert source["locale"] == "es-MX"
    assert package["report_language"] == "es-MX"
    assert package["locale"] == "es-MX"
    assert canonical["report_language"] == "es-MX"
    assert canonical["locale"] == "es-MX"
    assert canonical["identity"]["report_language"] == "es-MX"
    assert canonical["assessment"]["report_language"] == "es-MX"
    assert canonical["assessment"]["locale"] == "es-MX"
    assert source["human_review_required"] is True
    assert source["client_delivery_allowed"] is False
