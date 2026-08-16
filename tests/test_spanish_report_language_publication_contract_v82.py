from __future__ import annotations

import base64
import io

import pytest
from reportlab.pdfgen import canvas

from nico import client_report_completion_v2 as completion
from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_rendered_ci_boundary_truth_v78 as rendered_truth
from nico import comprehensive_report_language_truth_v77 as language_truth
from nico import comprehensive_run_record as run_record
from nico import phase17_canonical_artifact_rebuild_v1 as phase17
from nico import v2_pipeline_adapter as adapter
from nico import v2_production_authority as production


def _canonical(language: str, *, stale_root: str | None = None) -> dict[str, object]:
    return {
        "report_language": stale_root or language,
        "locale": stale_root or language,
        "identity": {
            "run_id": f"comprun_language_{language}",
            "repository": "example/product",
            "commit_sha": "a" * 40,
            "report_language": language,
        },
        "assessment": {
            "report_language": stale_root or language,
            "locale": stale_root or language,
            "sections": [],
        },
    }


def _markers(*, spanish: bool) -> tuple[str, ...]:
    canonical = _canonical("es-MX" if spanish else "en")
    return ci_v74.ci_cd_boundary_markers(canonical, spanish=spanish)


def _pdf(lines: tuple[str, ...]) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        page.drawString(40, y, line)
        y -= 20
    page.save()
    return buffer.getvalue()


def _rendered_package(
    *,
    language: str,
    stale_root: str | None = None,
    pdf_markers: tuple[str, ...] | None = None,
    html_suffix: str = "",
) -> dict[str, object]:
    spanish = language == "es-MX"
    markers = _markers(spanish=spanish)
    pdf_lines = pdf_markers if pdf_markers is not None else markers
    return {
        "json": _canonical(language, stale_root=stale_root),
        "markdown": "\n".join(markers),
        "html": "<html><body>" + "<br>".join(markers) + html_suffix + "</body></html>",
        "pdf_base64": base64.b64encode(_pdf(tuple(pdf_lines))).decode("ascii"),
    }


def test_run_record_canonicalizes_supported_spanish_alias() -> None:
    record = run_record.create_comprehensive_run_record(
        run_id="comprun_language_alias",
        repository="example/product",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_language_alias",
        customer_id="customer",
        project_id="project",
        authorized=True,
        report_language="es",
    )

    assert record["identity"]["report_language"] == "es-MX"


def test_run_record_rejects_unsupported_language_instead_of_defaulting_to_english() -> None:
    with pytest.raises(ValueError, match="unsupported_report_language:fr"):
        run_record.create_comprehensive_run_record(
            run_id="comprun_language_unsupported",
            repository="example/product",
            commit_sha="a" * 40,
            evidence_ledger_id="ledger_language_unsupported",
            customer_id="customer",
            project_id="project",
            authorized=True,
            report_language="fr",
        )


def test_persisted_run_identity_outweighs_stale_root_english() -> None:
    canonical = _canonical("es-MX", stale_root="en")

    assert language_truth.resolve_report_language(canonical) == "es-MX"
    assert rendered_truth.resolve_report_language(canonical) == "es-MX"
    assert phase17._is_spanish(canonical) is True
    assert adapter._report_language(canonical) == "es-MX"
    assert production._report_language(canonical) == "es-MX"


def test_spanish_markdown_html_pdf_validate_independently_and_repair_projection() -> None:
    result = _rendered_package(language="es-MX", stale_root="en")

    truth = rendered_truth.reconcile_rendered_ci_boundary_language(result)

    assert truth["language"] == "es-MX"
    assert truth["authority_source"] == "run_identity:report_language"
    assert truth["surface_coverage"]["markdown"]["complete"] is True
    assert truth["surface_coverage"]["html"]["complete"] is True
    assert truth["surface_coverage"]["pdf"]["complete"] is True
    assert result["json"]["report_language"] == "es-MX"
    assert result["json"]["identity"]["report_language"] == "es-MX"
    assert result["report_language"] == "es-MX"


def test_spanish_pdf_missing_marker_reports_language_surface_and_marker() -> None:
    markers = _markers(spanish=True)
    result = _rendered_package(
        language="es-MX",
        stale_root="en",
        pdf_markers=markers[1:],
    )

    with pytest.raises(
        ValueError,
        match=(
            r"client report omitted es-MX CI/CD boundary in PDF: "
            r"A\. Madurez de configuración de CI/CD:"
        ),
    ):
        rendered_truth.reconcile_rendered_ci_boundary_language(result)


def test_spanish_package_rejects_english_structural_ci_marker() -> None:
    result = _rendered_package(
        language="es-MX",
        html_suffix="<p>A. CI/CD configuration maturity:</p>",
    )

    with pytest.raises(
        ValueError,
        match=r"contains en CI/CD boundary in HTML for authoritative es-MX report",
    ):
        rendered_truth.reconcile_rendered_ci_boundary_language(result)


def test_english_markdown_html_pdf_regression_passes() -> None:
    result = _rendered_package(language="en")

    truth = rendered_truth.reconcile_rendered_ci_boundary_language(result)

    assert truth["language"] == "en"
    assert all(
        truth["surface_coverage"][surface]["complete"] is True
        for surface in ("markdown", "html", "pdf")
    )


def test_completion_validator_is_bound_without_masking_existing_fail_closed_gates() -> None:
    assert getattr(
        completion._validate_final_surfaces,
        "_nico_report_language_completion_validator_v82",
        False,
    ) is True
    assert getattr(
        completion._validate_final_surfaces,
        "_nico_comprehensive_placeholder_sanitization_v1",
        False,
    ) is False


def test_v2_production_authority_wrapper_keeps_spanish_through_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = {
        "status": "complete",
        "report_package": {"json": _canonical("es-MX", stale_root="en")},
        "canonical_report": _canonical("es-MX", stale_root="en"),
    }
    report_context = {
        "run_id": "comprun_v2_spanish_authority",
        "repository": "example/product",
        "commit_sha": "a" * 40,
        "report_language": "es-MX",
        "prior_stage_results": {"scanner": {"status": "complete"}},
    }

    monkeypatch.setattr(
        production,
        "_canonical_source",
        lambda context: (source, report_context, 0.0),
    )

    def finalize(value: dict[str, object]) -> dict[str, object]:
        canonical = value["report_package"]["json"]
        assert canonical["report_language"] == "es-MX"
        assert canonical["identity"]["report_language"] == "es-MX"
        return {
            **value,
            "report_language": "es-MX",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    monkeypatch.setattr(production, "finalize_report_package", finalize)
    wrapped = production.wrap_final_report_publication(
        lambda context: pytest.fail("legacy delegate must not render canonical source")
    )

    result = wrapped(dict(report_context))

    assert result["status"] == "complete"
    assert result["report_language"] == "es-MX"
    assert result["v2_production_authority"]["authoritative_assessment_state"] == "review_required"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert "client report omitted CI/CD boundary: A. CI/CD configuration maturity:" not in str(result)
