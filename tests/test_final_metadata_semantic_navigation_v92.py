from __future__ import annotations

import io
from types import SimpleNamespace

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _report_pdf(pages: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    _, height = letter
    for lines in pages:
        y = height - 54
        for line in lines:
            pdf.drawString(42, y, line)
            y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _outline_titles(value):
    output: list[str] = []
    if isinstance(value, list):
        for item in value:
            output.extend(_outline_titles(item))
        return output
    title = getattr(value, "title", None)
    if title:
        output.append(str(title))
    return output


def test_final_base_report_canonical_identity_retains_supplied_display_metadata():
    from nico import comprehensive_report_package as base_report
    from nico.comprehensive_final_display_metadata_v92 import (
        install_comprehensive_final_display_metadata_v92,
    )

    installed = install_comprehensive_final_display_metadata_v92()
    assert installed["bound"] is True
    assert installed["canonical_scope_ids_unchanged"] is True
    assert installed["canonical_scores_unchanged"] is True

    result = base_report.build_comprehensive_report_package(
        identity={
            "run_id": "comprun_metadata_regression",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_metadata_regression",
            "customer_id": "customer_scope_regression",
            "project_id": "project_scope_regression",
            "customer_name": "NICO Production Metadata Proof 2026-08-26",
            "project_name": "Comprehensive Metadata E2E Proof",
            "primary_technical_contact": "NICO Metadata Proof Contact",
        },
        stage_results={},
    )

    assert result["status"] == "complete"
    canonical = result["report_package"]["json"]
    identity = canonical["identity"]
    assert identity["customer_id"] == "customer_scope_regression"
    assert identity["project_id"] == "project_scope_regression"
    assert identity["customer_name"] == "NICO Production Metadata Proof 2026-08-26"
    assert identity["project_name"] == "Comprehensive Metadata E2E Proof"
    assert identity["primary_technical_contact"] == "NICO Metadata Proof Contact"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_ui_shaped_intake_survives_persistence_worker_identity_and_final_canonical(monkeypatch):
    from nico import comprehensive_api_routes as routes
    from nico import comprehensive_report_package as base_report
    from nico.comprehensive_final_display_metadata_v92 import (
        install_comprehensive_final_display_metadata_v92,
    )
    from nico.comprehensive_report_worker_runtime_v90 import _report_identity
    from nico.comprehensive_run_record import create_comprehensive_run_record

    class CapturingController:
        payload: dict[str, object] | None = None

        def start(self, payload: dict[str, object]) -> dict[str, object]:
            self.payload = payload
            return {
                "status": "ready",
                "human_review_required": True,
                "client_delivery_allowed": False,
            }

    controller = CapturingController()
    monkeypatch.setattr(routes, "_controller", lambda _request: controller)
    monkeypatch.setattr(
        routes,
        "capture_repository_snapshot",
        lambda _payload: {"status": "attached", "commit_sha": "b" * 40},
    )
    monkeypatch.setattr(routes, "expected_commit_sha", lambda _payload: "")
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                comprehensive_runtime={
                    "configured": True,
                    "persistence_adapter": "postgres",
                    "durability_verified": True,
                    "survives_container_replacement_verified": True,
                }
            )
        )
    )

    response = routes._intake(
        request,
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_scope_canary",
            "project_id": "project_scope_canary",
            "client_name": "NICO Production Metadata Proof 2026-08-26",
            "project_name": "Comprehensive Metadata E2E Proof",
            "authorized_by": "public_assessment_requester",
            "authorization_scope": "authorized defensive repository assessment",
            "assessment_depth": "strategic",
            "report_language": "en",
            "authorized": True,
            "authorization_confirmed": True,
            # This mirrors compactStrategicHumanEvidence output from the real mobile UI.
            "human_evidence": {
                "stakeholder_context": {
                    "evidence": {
                        "access_method": ["Public GitHub HTTPS/API metadata proof — read-only"],
                        "primary_technical_contact": ["NICO Metadata Proof Contact"],
                        "authorized_scope": ["BoneManTGRM/NICO metadata proof scope — read-only"],
                    },
                    "reviewer": "",
                    "observed_at": "",
                    "source_reference": "",
                    "excluded": False,
                    "exclusion_rationale": "",
                }
            },
        },
    )

    assert controller.payload is not None
    payload = controller.payload
    record = create_comprehensive_run_record(
        run_id=str(payload["run_id"]),
        repository=str(payload["repository"]),
        commit_sha=str(payload["commit_sha"]),
        evidence_ledger_id=str(payload["evidence_ledger_id"]),
        customer_id=str(payload["customer_id"]),
        project_id=str(payload["project_id"]),
        authorized=True,
        assessment_depth="strategic",
        report_language="en",
        human_evidence=payload["human_evidence"],
    )
    retained = record["human_evidence"]["modules"]["stakeholder_context"]["evidence"]
    assert retained["customer_name"] == "NICO Production Metadata Proof 2026-08-26"
    assert retained["project_name"] == "Comprehensive Metadata E2E Proof"
    assert "NICO Metadata Proof Contact" in str(retained["primary_technical_contact"])
    assert "Public GitHub HTTPS/API metadata proof" in str(retained["access_method"])
    assert "metadata proof scope" in str(retained["authorized_scope"])

    report_identity = _report_identity(
        {
            **record["identity"],
            "human_evidence": record["human_evidence"],
        }
    )
    assert report_identity["customer_name"] == "NICO Production Metadata Proof 2026-08-26"
    assert report_identity["project_name"] == "Comprehensive Metadata E2E Proof"
    assert report_identity["primary_technical_contact"] == "NICO Metadata Proof Contact"

    install_comprehensive_final_display_metadata_v92()
    final = base_report.build_comprehensive_report_package(
        identity=report_identity,
        stage_results={},
    )
    final_identity = final["report_package"]["json"]["identity"]
    assert final_identity["customer_id"] == "customer_scope_canary"
    assert final_identity["project_id"] == "project_scope_canary"
    assert final_identity["customer_name"] == "NICO Production Metadata Proof 2026-08-26"
    assert final_identity["project_name"] == "Comprehensive Metadata E2E Proof"
    assert final_identity["primary_technical_contact"] == "NICO Metadata Proof Contact"
    assert response["client_name"] == "NICO Production Metadata Proof 2026-08-26"
    assert response["project_name"] == "Comprehensive Metadata E2E Proof"
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False


def test_semantic_toc_keeps_every_heading_when_compaction_puts_three_sections_on_one_page():
    from nico.comprehensive_semantic_navigation_v2 import semantic_renumber_and_outline

    source = _report_pdf(
        [
            ["NICO Comprehensive", "AUTOMATED DRAFT | PENDING HUMAN APPROVAL"],
            [
                "NICO Comprehensive · AUTOMATED DRAFT",
                "Code audit",
                "Evidence for code audit.",
                "Dependency / Library Ecosystem",
                "Evidence for dependencies.",
                "Secrets Exposure Review",
                "Evidence for secrets.",
            ],
            [
                "NICO Comprehensive · AUTOMATED DRAFT",
                "Static Analysis",
                "Evidence for static analysis.",
            ],
            [
                "NICO Comprehensive · AUTOMATED DRAFT",
                "Human Review and Acceptance Gate",
                "Authorized human review remains required.",
            ],
        ]
    )

    revised = semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(revised))
    assert len(reader.pages) == 5

    toc = reader.pages[1].extract_text() or ""
    for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Static Analysis",
        "Human Review and Acceptance Gate",
    ):
        assert title in toc

    # All three compacted technical sections intentionally map to the same physical
    # page after the TOC is inserted. The old one-title-per-page navigation lost two.
    lines = [" ".join(line.split()) for line in toc.splitlines() if line.strip()]
    positions = {title: lines.index(title) for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
    )}
    for title, index in positions.items():
        assert lines[index + 1] == "3", title

    static_index = lines.index("Static Analysis")
    assert lines[static_index + 1] == "4"
    gate_index = lines.index("Human Review and Acceptance Gate")
    assert lines[gate_index + 1] == "5"

    full_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Evidence for code audit." in full_text
    assert "Evidence for dependencies." in full_text
    assert "Evidence for secrets." in full_text
    assert "Evidence for static analysis." in full_text

    outline_titles = _outline_titles(reader.outline)
    for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Static Analysis",
        "Human Review and Acceptance Gate",
    ):
        assert title in outline_titles


def test_spanish_semantic_navigation_adds_no_english_toc_or_document_page_label():
    from nico.comprehensive_semantic_navigation_v2 import semantic_renumber_and_outline

    source = _report_pdf(
        [
            ["NICO", "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE"],
            [
                "NICO Comprehensive · BORRADOR AUTOMATIZADO",
                "Auditoría de código",
                "Evidencia conservada.",
                "Ecosistema de dependencias y bibliotecas",
                "Evidencia conservada.",
            ],
            [
                "NICO Comprehensive · BORRADOR AUTOMATIZADO",
                "Puerta de revisión y aceptación humana",
                "La aprobación humana autorizada sigue pendiente.",
            ],
        ]
    )

    revised = semantic_renumber_and_outline(source)
    reader = PdfReader(io.BytesIO(revised))
    toc = reader.pages[1].extract_text() or ""
    assert "Tabla de contenido" in toc
    assert "Table of Contents" not in toc
    assert "Auditoría de código" in toc
    assert "Ecosistema de dependencias y bibliotecas" in toc
    assert "Puerta de revisión y aceptación humana" in toc

    document_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Página del documento 3 de 4" in document_text
    assert "Document page 3 of 4" not in document_text
