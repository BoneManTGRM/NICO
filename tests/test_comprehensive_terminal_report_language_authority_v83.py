from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_report_language_truth_v77 as language_truth
from nico import v2_production_authority as production
from nico.comprehensive_terminal_report_language_authority_v83 import (
    install_comprehensive_terminal_report_language_authority_v83,
)
from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package


INSTALLATION = install_comprehensive_terminal_report_language_authority_v83()
GENERATED_AT = "2026-08-16T10:44:00Z"


def _canonical(*, stale_root: str = "en", identity_language: str = "es-MX") -> dict:
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
            "run_id": "comprun_spanish_terminal_regression",
            "customer_id": "customer-terminal-language",
            "project_id": "project-terminal-language",
            "evidence_ledger_id": "ledger-terminal-language",
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
            "executive_summary": "Evaluación de producción completada.",
        },
    }


def _source(*, stale_root: str = "en", identity_language: str = "es-MX") -> dict:
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


def _pdf(lines: tuple[str, ...]) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, invariant=1)
    y = 760
    for line in lines:
        document.drawString(40, y, line)
        y -= 20
    document.save()
    return output.getvalue()


def _pdf_text(encoded: str) -> str:
    pdf = base64.b64decode(encoded)
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_terminal_installer_is_bound_after_late_compatibility_layers() -> None:
    assert INSTALLATION["shared_v77_resolver_is_authority"] is True
    assert INSTALLATION["persisted_run_identity_outranks_root_projection"] is True
    assert INSTALLATION["stale_root_english_probe_resolves_es_MX"] is True
    assert INSTALLATION["final_truth_language_bound"] is True
    assert INSTALLATION["final_truth_ci_markers_bound"] is True
    assert INSTALLATION["final_truth_ci_lines_bound"] is True
    assert INSTALLATION["final_surface_validator_bound"] is True
    assert INSTALLATION["human_review_required"] is True
    assert INSTALLATION["client_delivery_allowed"] is False


def test_persisted_es_mx_identity_beats_stale_root_english_everywhere() -> None:
    canonical = _canonical()

    assert language_truth.resolve_report_language(canonical) == "es-MX"
    assert final_truth._report_language(canonical) == "es-MX"
    assert final_truth._ci_boundary_markers(canonical) == language_truth._ES_BOUNDARY_MARKERS
    lines = final_truth._ci_lines(canonical)
    assert len(lines) == 4
    assert all(
        line.startswith(marker)
        for line, marker in zip(lines, language_truth._ES_BOUNDARY_MARKERS, strict=True)
    )
    assert not any(
        line.startswith(marker)
        for line in lines
        for marker in language_truth._EN_BOUNDARY_MARKERS
    )


def test_independent_surface_gate_names_language_surface_and_missing_marker() -> None:
    canonical = _canonical()
    markers = language_truth._ES_BOUNDARY_MARKERS
    with pytest.raises(
        ValueError,
        match=(
            r"client report omitted es-MX CI/CD boundary in PDF: "
            r"A\. Madurez de configuración de CI/CD:"
        ),
    ):
        final_truth._validate_surfaces(
            {
                "json": canonical,
                "markdown": "\n".join(markers),
                "html": "<html><body>" + "<br>".join(markers) + "</body></html>",
                "pdf_base64": base64.b64encode(_pdf(markers[1:])).decode("ascii"),
            }
        )


def test_mixed_language_structural_marker_fails_closed() -> None:
    canonical = _canonical()
    markers = language_truth._ES_BOUNDARY_MARKERS
    with pytest.raises(
        ValueError,
        match=r"contains en CI/CD boundary in HTML for authoritative es-MX report",
    ):
        final_truth._validate_surfaces(
            {
                "json": canonical,
                "markdown": "\n".join(markers),
                "html": (
                    "<html><body>"
                    + "<br>".join(markers)
                    + "<p>A. CI/CD configuration maturity:</p>"
                    + "</body></html>"
                ),
                "pdf_base64": base64.b64encode(_pdf(markers)).decode("ascii"),
            }
        )


def test_real_phase9_finalizer_renders_spanish_ci_boundary_on_all_surfaces() -> None:
    result = finalize_report_package(_source())
    package = result["report_package"]
    canonical = package["json"]
    markdown = str(package["markdown"])
    rendered_html = str(package["html"])
    pdf_text = _pdf_text(str(package["pdf_base64"]))

    assert language_truth.resolve_report_language(canonical) == "es-MX"
    assert canonical["report_language"] == "es-MX"
    assert canonical["identity"]["report_language"] == "es-MX"
    for marker in language_truth._ES_BOUNDARY_MARKERS:
        assert marker in markdown
        assert marker in rendered_html
        assert marker in pdf_text
    for marker in language_truth._EN_BOUNDARY_MARKERS:
        assert marker not in markdown
        assert marker not in rendered_html
        assert marker not in pdf_text
    assert package["human_review_required"] is True
    assert package["client_delivery_allowed"] is False


def test_real_v2_production_authority_does_not_reproduce_english_marker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    report_context = {
        "run_id": "comprun_spanish_terminal_regression",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "report_language": "es-MX",
        "prior_stage_results": {},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    monkeypatch.setattr(
        production,
        "_canonical_source",
        lambda context: (source, report_context, 0.0),
    )
    wrapped = production.wrap_final_report_publication(
        lambda context: pytest.fail("canonical source must not fall back to legacy rendering")
    )

    result = wrapped(dict(report_context))

    assert result["status"] == "complete", result.get("reason")
    assert "client report omitted CI/CD boundary: A. CI/CD configuration maturity:" not in str(result)
    package = result["report_package"]
    assert language_truth.resolve_report_language(package["json"]) == "es-MX"
    for marker in language_truth._ES_BOUNDARY_MARKERS:
        assert marker in str(package["markdown"])
        assert marker in str(package["html"])
        assert marker in _pdf_text(str(package["pdf_base64"]))
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
