from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _proof_human_evidence() -> dict[str, object]:
    return {
        "stakeholder_context": {
            "evidence": {
                "access_method": ["GitHub HTTPS/API - read-only"],
                "primary_technical_contact": ["NICO Acceptance Contact"],
                "authorized_scope": ["full repository at exact assessed SHA - read-only"],
            }
        }
    }


def test_direct_intake_display_metadata_reaches_controller(monkeypatch) -> None:
    import nico.comprehensive_api_routes as routes
    import nico.comprehensive_intake_display_metadata_v2 as patch

    original_intake = routes._intake
    original_installed = patch._INSTALLED
    seen: dict[str, object] = {}

    class FakeController:
        def start(self, payload):
            seen.update(payload)
            return {
                "status": "ready",
                "run_id": payload["run_id"],
                "customer_id": payload["customer_id"],
                "project_id": payload["project_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }

    try:
        patch._INSTALLED = False
        monkeypatch.setattr(
            routes,
            "capture_repository_snapshot",
            lambda payload: {
                "status": "attached",
                "commit_sha": "a" * 40,
                "repository": payload["repository"],
            },
        )
        monkeypatch.setattr(routes, "expected_commit_sha", lambda payload: "")
        monkeypatch.setattr(routes, "normalize_repository", lambda value: str(value))
        monkeypatch.setattr(routes, "_controller", lambda request: FakeController())
        monkeypatch.setattr(
            routes,
            "_with_runtime_truth",
            lambda request, response: response,
        )

        state = patch.install_comprehensive_intake_display_metadata_v2()
        assert state["bound"] is True
        assert state["direct_controller_payload"] is True
        assert state["contextvar_required_for_display_metadata"] is False

        response = routes._intake(
            object(),
            {
                "repository": "BoneManTGRM/NICO",
                "client_name": "  Intake Proof Client  ",
                "project_name": " Intake Proof Project ",
                "customer_id": "default_customer",
                "project_id": "default_project",
                "assessment_depth": "strategic",
                "report_language": "en",
                "human_evidence": _proof_human_evidence(),
                "authorized": True,
                "authorization_confirmed": True,
            },
        )

        assert seen["client_name"] == "Intake Proof Client"
        assert seen["project_name"] == "Intake Proof Project"
        assert seen["customer_id"] == "default_customer"
        assert seen["project_id"] == "default_project"
        assert seen["human_evidence"]
        assert response["client_name"] == "Intake Proof Client"
        assert response["project_name"] == "Intake Proof Project"
    finally:
        routes._intake = original_intake
        patch._INSTALLED = original_installed


def test_distinctive_metadata_is_in_initial_canonical_record(monkeypatch) -> None:
    """Prove browser display metadata survives the real controller/create-record seam."""

    import nico.comprehensive_api_routes as routes
    import nico.comprehensive_intake_display_metadata_v2 as direct_patch
    import nico.comprehensive_report_review_integrity_v1 as integrity
    import nico.comprehensive_run_service as run_service_module
    from nico.comprehensive_api_controller import ComprehensiveApiController
    from nico.comprehensive_run_record import _record_hash

    integrity.install_comprehensive_report_review_integrity_v1()
    direct_patch._INSTALLED = False
    direct_patch.install_comprehensive_intake_display_metadata_v2()

    captured: dict[str, object] = {}

    class RecordingService:
        def start(self, **kwargs):
            record = run_service_module.create_comprehensive_run_record(**kwargs)
            captured["record"] = record
            return record

    controller = ComprehensiveApiController(RecordingService())
    monkeypatch.setattr(
        routes,
        "capture_repository_snapshot",
        lambda payload: {
            "status": "attached",
            "commit_sha": "b" * 40,
            "repository": payload["repository"],
        },
    )
    monkeypatch.setattr(routes, "expected_commit_sha", lambda payload: "")
    monkeypatch.setattr(routes, "normalize_repository", lambda value: str(value))
    monkeypatch.setattr(routes, "_controller", lambda request: controller)
    monkeypatch.setattr(routes, "_with_runtime_truth", lambda request, response: response)

    routes._intake(
        object(),
        {
            "repository": "BoneManTGRM/NICO",
            "client_name": "NICO Acceptance Client",
            "project_name": "NICO Acceptance Project",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "assessment_depth": "strategic",
            "report_language": "en",
            "human_evidence": _proof_human_evidence(),
            "authorized": True,
            "authorization_confirmed": True,
        },
    )

    record = captured["record"]
    assert isinstance(record, dict)
    identity = record["identity"]
    assert identity["customer_id"] == "default_customer"
    assert identity["project_id"] == "default_project"
    assert identity["customer_name"] == "NICO Acceptance Client"
    assert identity["project_name"] == "NICO Acceptance Project"
    assert integrity._display_values(record)["primary_technical_contact"] == "NICO Acceptance Contact"
    assert integrity._find_evidence_value(record["human_evidence"], "access_method") == "GitHub HTTPS/API - read-only"
    assert integrity._find_evidence_value(record["human_evidence"], "authorized_scope") == "full repository at exact assessed SHA - read-only"
    assert record["integrity_sha256"] == _record_hash(record)


def _spanish_sparse_pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    header = "NICO Comprehensive · comprun_worker_fixture · BORRADOR AUTOMATIZADO"

    # Production Comprehensive PDFs always retain a cover before semantic body pages.
    # Keep the synthetic reflow fixture production-shaped so navigation may safely treat
    # source page 1 as cover instead of weakening the production cover boundary.
    document.drawString(54, 760, "NICO Comprehensive")
    document.drawString(54, 720, "BORRADOR AUTOMATIZADO · APROBACIÓN HUMANA PENDIENTE")
    document.showPage()

    sections = [
        ("Auditoría de código", "Hallazgos ejecutables de riesgo de código: 0."),
        ("Ecosistema de dependencias", "Candidatos de dependencias para revisión: 21."),
        ("Revisión de secretos", "Candidatos de secretos para revisión: 19."),
    ]
    for title, evidence in sections:
        document.drawString(54, 760, header)
        document.drawString(54, 720, title)
        document.drawString(54, 690, evidence)
        document.showPage()
    document.drawString(54, 760, header)
    document.drawString(54, 720, "Revisión humana y aceptación")
    document.drawString(54, 690, "La aprobación humana permanece pendiente.")
    document.save()
    return buffer.getvalue()


def test_final_worker_reflows_mexican_spanish_before_navigation() -> None:
    import nico.comprehensive_final_worker_pdf_reflow_v1 as worker_reflow
    from nico import comprehensive_manifest_navigation_v1 as navigation

    state = worker_reflow.install_comprehensive_final_worker_pdf_reflow_v1()
    assert state["bound"] is True
    assert state["bilingual_source_headers_supported"] is True
    assert state["reflow_before_final_navigation"] is True
    assert state["mexican_spanish_toc_validation_supported"] is True

    original = _spanish_sparse_pdf()
    output = navigation._renumber_and_outline(original)
    reader = PdfReader(io.BytesIO(output))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    # Five production-shaped source pages would become six after normal TOC insertion.
    # A result below six proves worker-local reflow happened before semantic navigation.
    assert len(reader.pages) < 6
    assert "Tabla de contenido" in text
    assert "Table of Contents" not in text
    for index in range(1, len(reader.pages) + 1):
        assert f"Página del documento {index} de {len(reader.pages)}" in text
    assert "Document page " not in text
    for marker in (
        "Auditoría de código",
        "Hallazgos ejecutables de riesgo de código: 0.",
        "Ecosistema de dependencias",
        "Candidatos de dependencias para revisión: 21.",
        "Revisión de secretos",
        "Candidatos de secretos para revisión: 19.",
        "Revisión humana y aceptación",
        "La aprobación humana permanece pendiente.",
    ):
        assert marker in text


def test_final_worker_installs_sparse_reflow_before_freezing_pdf() -> None:
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(encoding="utf-8")
    reflow_source = Path("nico/comprehensive_final_worker_pdf_reflow_v1.py").read_text(
        encoding="utf-8"
    )
    assert "install_comprehensive_final_worker_pdf_reflow_v1" in source
    assert "FINAL_WORKER_PDF_REFLOW = install_comprehensive_final_worker_pdf_reflow_v1()" in source
    assert '"reflow_before_final_navigation"' in source
    assert '"bilingual_source_headers_supported"' in source
    assert '"toc_page_labels_and_bookmarks_rebuilt_after_reflow"' in source
    assert source.index("FINAL_WORKER_PDF_REFLOW =") < source.index("CANONICAL_TRUTH_HASH_COMPAT =")
    assert "BORRADOR\\s+AUTOMATIZADO" in reflow_source


def test_markdown_bridge_waits_for_terminal_report_before_prefetch() -> None:
    source = Path("apps/web/app/AssessmentMarkdownCopyBridge.tsx").read_text(encoding="utf-8")
    assert 'actions.getAttribute("data-assessment-report-ready") !== "true"' in source
    assert "enabledCopyButton(actions)" in source
    assert "Markdown ready. Click Copy Markdown." in source
    assert "const markdown = entry.markdown || await loadMarkdown(entry)" not in source


def test_pdf_bridge_uses_one_user_gesture_dispatch_and_visible_status() -> None:
    source = Path("apps/web/app/AssessmentReviewPdfDownload.tsx").read_text(encoding="utf-8")
    proof = Path("scripts/mobile_pdf_download_action_proof_v1.py").read_text(encoding="utf-8")
    assert "const opened = window.open" not in source
    assert source.count("link.click();") == 1
    assert "PDF requested. Check the new tab or your downloads." in source
    assert "data-nico-review-pdf-action-status" in source
    assert "assert len(gesture_pdf_requests) == 1" in proof
    assert '"ui_review_pdf_single_dispatch_verified": True' in proof


def test_exact_main_spanish_proof_requires_the_regressions_to_be_fixed() -> None:
    script = Path("scripts/spanish_comprehensive_live_acceptance_v3.py").read_text(
        encoding="utf-8"
    )
    workflow = Path(".github/workflows/spanish-comprehensive-production-proof.yml").read_text(
        encoding="utf-8"
    )
    for marker in (
        "NICO Acceptance Client",
        "NICO Acceptance Project",
        "NICO Acceptance Contact",
        "GitHub HTTPS/API - read-only",
        "Full repository at exact assessed SHA - read-only",
        'report_language="es-MX"',
        'report_language="en"',
        "0 < page_count < 44",
        "same_run_bilingual_pdf_verified",
    ):
        assert marker in script
    for marker in (
        'payload["commercial_display_metadata_verified"] is True',
        'payload["primary_technical_contact_verified"] is True',
        'payload["access_method_verified_in_canonical_truth"] is True',
        'payload["authorized_scope_verified_in_canonical_truth"] is True',
        'payload["same_run_bilingual_pdf_verified"] is True',
        'int(payload["spanish_pdf_page_count"]) < 44',
        'int(payload["english_pdf_page_count"]) < 44',
    ):
        assert marker in workflow
