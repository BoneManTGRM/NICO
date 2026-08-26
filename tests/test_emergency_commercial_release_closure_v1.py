from __future__ import annotations

import base64
import io
import sqlite3
from types import SimpleNamespace

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _find_key(value, key: str):
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for nested in value.values():
            found = _find_key(nested, key)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_key(nested, key)
            if found not in (None, ""):
                return found
    return None


def _minimal_stage_results() -> dict:
    return {
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "assessment": {
                "status": "complete",
                "executive_summary": "Synthetic release-closure regression.",
                "maturity_signal": {
                    "level": "Exceptional",
                    "score": 93,
                    "presented_score": 93,
                    "evidence_adjusted_score": 93,
                },
                "technical_score": 93,
                "evidence_adjusted_score": 93,
                "sections": [],
                "unavailable_data_notes": [],
                "human_review_required": True,
                "client_ready": False,
            },
        }
    }


def test_real_intake_persistence_and_report_boundary_keep_all_supplied_display_metadata(
    tmp_path, monkeypatch
) -> None:
    from nico import comprehensive_api_routes as routes
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_commercial_release_closure_v1 import (
        install_comprehensive_commercial_release_closure_v1,
    )
    from nico.comprehensive_report_worker_runtime_v90 import _report_identity
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore
    import nico.comprehensive_report_worker_runtime_v90 as worker

    database = tmp_path / "comprehensive-release-closure.sqlite3"

    def connect():
        return sqlite3.connect(database)

    store = ComprehensiveRunStore(connect)
    store.ensure_schema()
    service = ComprehensiveRunService(store, {})
    controller = ComprehensiveApiController(service)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                comprehensive_api_controller=controller,
                comprehensive_runtime={
                    "configured": True,
                    "persistence_adapter": "sqlite",
                    "durability_verified": True,
                    "survives_container_replacement_verified": True,
                },
            )
        )
    )

    monkeypatch.setattr(
        routes,
        "capture_repository_snapshot",
        lambda _payload: {
            "status": "attached",
            "commit_sha": "a" * 40,
        },
    )
    monkeypatch.setattr(routes, "expected_commit_sha", lambda _payload: "")

    response = routes._intake(
        request,
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_scope_regression",
            "project_id": "project_scope_regression",
            "client_name": "NICO Production Metadata Proof",
            "project_name": "Comprehensive Metadata E2E Proof",
            "assessment_depth": "strategic",
            "report_language": "en",
            "authorized": True,
            "authorization_confirmed": True,
            "human_evidence": {
                "modules": {
                    "stakeholder_context": {
                        "evidence": {
                            "access_method": "Public GitHub HTTPS/API read-only proof",
                            "primary_technical_contact": "NICO Metadata Proof Contact",
                            "authorized_scope": "BoneManTGRM/NICO exact current main read-only proof",
                        }
                    }
                }
            },
        },
    )

    record = store.load(str(response["run_id"]))
    evidence = record["human_evidence"]
    assert _find_key(evidence, "customer_name") == "NICO Production Metadata Proof"
    assert _find_key(evidence, "project_name") == "Comprehensive Metadata E2E Proof"
    assert _find_key(evidence, "primary_technical_contact") == "NICO Metadata Proof Contact"
    assert _find_key(evidence, "access_method") == "Public GitHub HTTPS/API read-only proof"
    assert _find_key(evidence, "authorized_scope") == (
        "BoneManTGRM/NICO exact current main read-only proof"
    )

    identity = dict(record["identity"])
    report_identity = _report_identity(
        {
            **identity,
            "human_evidence": evidence,
            "report_language": "en",
        }
    )
    assert report_identity["customer_name"] == "NICO Production Metadata Proof"
    assert report_identity["project_name"] == "Comprehensive Metadata E2E Proof"
    assert (
        report_identity["primary_technical_contact"]
        == "NICO Metadata Proof Contact"
    )

    install_comprehensive_commercial_release_closure_v1()
    package = worker.build_comprehensive_report_package(
        identity=report_identity,
        stage_results=_minimal_stage_results(),
    )
    assert package["status"] == "complete"
    canonical = package["report_package"]["json"]
    canonical_identity = canonical["identity"]

    assert canonical_identity["customer_id"] == "customer_scope_regression"
    assert canonical_identity["project_id"] == "project_scope_regression"
    assert canonical_identity["customer_name"] == "NICO Production Metadata Proof"
    assert canonical_identity["project_name"] == "Comprehensive Metadata E2E Proof"
    assert (
        canonical_identity["primary_technical_contact"]
        == "NICO Metadata Proof Contact"
    )

    from nico import comprehensive_report_package as report_module

    assert package["report_package"]["canonical_truth_sha256"] == report_module._canonical_hash(
        canonical
    )
    pdf = base64.b64decode(package["report_package"]["pdf_base64"])
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    assert "NICO Production Metadata Proof" in pdf_text
    assert "Comprehensive Metadata E2E Proof" in pdf_text

    # The client-evidence stage is the final presentation surface for the technical
    # contact. It reads canonical report identity, not browser/process memory.
    import nico.comprehensive_report_review_integrity_v1 as integrity
    import nico.v2_premium_report_renderer as renderer

    integrity._install_required_report_sections()
    stages = renderer._canonical_stages(canonical)
    client_summary = next(
        stage for stage in stages if stage.get("stage_id") == "client_evidence_summary"
    )
    retained = "\n".join(client_summary.get("evidence") or [])
    unavailable = "\n".join(client_summary.get("unavailable") or [])
    assert "NICO Production Metadata Proof" in retained
    assert "Comprehensive Metadata E2E Proof" in retained
    assert "NICO Metadata Proof Contact" in retained
    assert "not supplied" not in unavailable.casefold()


def _multi_heading_pdf(*, spanish: bool = False) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    headings = (
        (
            "NICO Comprehensive",
            "NICO Comprehensive | AUTOMATED DRAFT",
        ),
        (
            (
                "Auditoría de código",
                "Ecosistema de dependencias y bibliotecas",
                "Revisión de exposición de secretos",
            )
            if spanish
            else (
                "Code audit",
                "Dependency / Library Ecosystem",
                "Secrets Exposure Review",
            )
        ),
        (
            (
                "Resumen de evidencia del cliente",
                "QA funcional",
                "Paridad de plataformas",
            )
            if spanish
            else (
                "Client Evidence Summary",
                "Functional QA",
                "Platform Parity",
            )
        ),
    )
    for page_index, content in enumerate(headings):
        values = content if isinstance(content, tuple) else (content,)
        y = 744
        if spanish and page_index:
            pdf.drawString(48, y, "NICO Comprehensive | BORRADOR AUTOMATIZADO")
            y -= 24
        for value in values:
            pdf.drawString(48, y, value)
            y -= 24
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_semantic_navigation_keeps_multiple_sections_on_the_same_physical_page() -> None:
    from nico.comprehensive_commercial_release_closure_v1 import (
        semantic_renumber_and_outline,
    )

    output = semantic_renumber_and_outline(_multi_heading_pdf())
    reader = PdfReader(io.BytesIO(output))
    pages = [page.extract_text() or "" for page in reader.pages]
    toc = pages[1]

    for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Client Evidence Summary",
        "Functional QA",
        "Platform Parity",
    ):
        assert title in toc

    # Three semantic sections share final physical page 3; three more share page 4.
    for title in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
    ):
        line = next(line for line in toc.splitlines() if title in line)
        assert line.rstrip().endswith("3")
    for title in ("Client Evidence Summary", "Functional QA", "Platform Parity"):
        line = next(line for line in toc.splitlines() if title in line)
        assert line.rstrip().endswith("4")

    outline_text = " ".join(str(item) for item in reader.outline)
    assert "Code audit" in outline_text
    assert "Dependency / Library Ecosystem" in outline_text
    assert "Secrets Exposure Review" in outline_text


def test_semantic_navigation_localizes_generated_toc_for_es_mx() -> None:
    from nico.comprehensive_commercial_release_closure_v1 import (
        semantic_renumber_and_outline,
    )

    output = semantic_renumber_and_outline(_multi_heading_pdf(spanish=True))
    reader = PdfReader(io.BytesIO(output))
    toc = reader.pages[1].extract_text() or ""

    assert "Tabla de contenido" in toc
    assert "Auditoría de código" in toc
    assert "Ecosistema de dependencias y bibliotecas" in toc
    assert "Revisión de exposición de secretos" in toc
    assert "Resumen de evidencia del cliente" in toc
    assert "QA funcional" in toc
    assert "Paridad de plataformas" in toc
    assert "Table of Contents" not in toc
