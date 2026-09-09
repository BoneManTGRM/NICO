from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from nico.candidate_phase1_report_workload_pdf_v1 import render_phase1_evidence_review_gate_pdf
from nico.candidate_phase1_report_workload_text_v1 import workload_markdown
from nico.comprehensive_review_report_truth_v1 import _synchronize_package
from tests.test_phase1_pdf_numeric_and_footer_integrity_v1 import _canonical


def _truth(pending: int = 0) -> dict:
    return {
        "raw_scanner_candidates": 2,
        "technical_triage_completed": 2,
        "technical_triage_pending": 0,
        "technical_triage_coverage_pct": 100,
        "not_actionable": 0,
        "needs_review": 2,
        "confirmed": 0,
        "authorized_human_disposition_pending": pending,
        "authorized_human_disposition_completed": 2 - pending,
        "confirmed_material_findings": 1,
        "final_human_approval_status": "pending",
        "client_delivery_authorization_status": "blocked",
        "candidate_review": [
            {
                "candidate_id": "A", "category": "static",
                "human_disposition": "confirmed", "confirmed_material_finding": True,
            },
            {
                "candidate_id": "B", "category": "dependency",
                "human_disposition": "" if pending else "not_applicable",
                "confirmed_material_finding": False,
            },
        ],
        "quality_control_required_count": 1,
        "quality_control_completed_count": 1,
    }


def _page(text: str) -> PdfReader:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(50, 700, text)
    document.save()
    return PdfReader(io.BytesIO(buffer.getvalue()))


@pytest.mark.parametrize("spanish", [False, True])
def test_current_review_replaces_owned_summary_and_preserves_technical_pages(spanish: bool) -> None:
    canonical = _canonical()
    canonical["identity"]["report_language"] = "es-MX" if spanish else "en"
    original = render_phase1_evidence_review_gate_pdf(canonical, {}, spanish=spanish)
    writer = PdfWriter()
    technical = "Technical evidence unchanged: scanner finding remains pending remediation."
    writer.add_page(_page(technical).pages[0])
    for page in PdfReader(io.BytesIO(original)).pages:
        writer.add_page(page)
    # An older owned gate occupied an extra page. Replacement must shrink only
    # that span and publish the new base count for the next synchronization.
    writer.add_page(_page("Human Review and Acceptance Gate\nOld review snapshot.").pages[0])
    writer.add_page(_page("Unrelated retained evidence sheet.").pages[0])
    writer.add_page(_page("Client Artifact Manifest").pages[0])
    buffer = io.BytesIO()
    writer.write(buffer)
    technical_stream = writer.pages[0].get_contents().get_data()
    evidence_section = (
        "## Resumen del paquete de evidencia\n\nLimitación conservada: no se probó la producción.\n- Candidatos pendientes de revisión: 18\n- Hallazgos materiales confirmados: 0\n- Efecto en puntuación: solo aseguramiento hasta completar la revisión.\n\n"
        if spanish else
        "## Evidence Package Summary\n\nRetained limitation: production was not tested.\n- Review-required candidates: 18\n- Confirmed material findings: 0\n- Score effect: assurance-only until triaged.\n\n"
    )
    package = {
        "json": canonical,
        "pdf_base64": base64.b64encode(buffer.getvalue()).decode(),
        "markdown": "# Technical\nScanner finding remains pending remediation.\n\n" + evidence_section + workload_markdown(canonical, spanish=spanish),
        "html": "<p>old</p>",
    }
    truth = _truth()
    synchronized_counts = []
    for _ in range(2):
        _synchronize_package(package, truth)
        reader = PdfReader(io.BytesIO(base64.b64decode(package["pdf_base64"])))
        synchronized_counts.append(len(reader.pages))
        assert reader.pages[0].get_contents().get_data() == technical_stream
        assert package["phase2_review_base_pdf_page_count"] == len(reader.pages) - 1
        texts = [page.extract_text() or "" for page in reader.pages]
        assert texts[0].strip() == technical
        joined = " ".join(" ".join(texts).split())
        assert "Human dispositions remain pending" not in joined
        assert "Las disposiciones humanas siguen pendientes" not in joined
        disposition = "Disposiciones registradas: 2; pendientes: 0" if spanish else "Recorded dispositions: 2; pending: 0"
        qc = "Control de calidad: 1/1" if spanish else "Quality control: 1/1"
        assert disposition in joined
        assert qc in joined
        assert sum(text.startswith("Client Artifact Manifest") for text in texts) == 1
        assert sum(text.startswith("Unrelated retained evidence sheet.") for text in texts) == 1
        obsolete = "La disposición y aprobación humanas siguen pendientes" if spanish else "Human disposition and approval remain pending"
        assert obsolete not in package["markdown"]
        retained = "Limitación conservada: no se probó la producción." if spanish else "Retained limitation: production was not tested."
        assert retained in package["markdown"]
        current_count = "Candidatos pendientes de revisión: 0" if spanish else "Review-required candidates: 0"
        assert current_count in package["markdown"]
        assert "assurance-only until triaged" not in package["markdown"]
        assert "solo aseguramiento hasta completar la revisión" not in package["markdown"]
        assert package["json"]["human_review_truth"] == truth
        summary = package["json"]["review_candidate_summary"]
        assert summary["review_required_total"] == 0
        assert summary["verified_material_total"] == 1
        assert summary["by_category"]["dependency"]["review_required"] == 0
        assert package["json"]["client_delivery_allowed"] is False
        assert package["human_review_truth"]["final_human_approval_status"] == "pending"
    assert synchronized_counts[0] == synchronized_counts[1] == len(writer.pages)


@pytest.mark.parametrize("spanish", [False, True])
def test_partial_review_keeps_real_pending_state(spanish: bool) -> None:
    canonical = _canonical()
    canonical["human_review_truth"] = _truth(1)
    pdf = render_phase1_evidence_review_gate_pdf(canonical, {}, spanish=spanish)
    text = " ".join(" ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages).split())
    expected = "Disposiciones registradas: 1; pendientes: 1" if spanish else "Recorded dispositions: 1; pending: 1"
    assert expected in text
