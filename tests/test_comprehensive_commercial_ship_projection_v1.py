from __future__ import annotations

import base64
import io
from copy import deepcopy
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_commercial_ship_projection_v3 import (
    _bind_final_pdf_layout,
    _finalize_artifact_navigation,
    _source_pdf_requires_integrity_reprojection,
    compact_sparse_limitation_pages,
    project_canonical_for_client_presentation,
)
from nico.comprehensive_spanish_current_copy_worker_v98 import (
    localize_current_report_copy_v98,
)


def _canonical_fixture() -> dict:
    return {
        "identity": {
            "run_id": "comprun_dynamic_fixture",
            "repository": "example/repository",
            "commit_sha": "a" * 40,
        },
        "stage_summaries": [
            {
                "stage_id": "requirements_traceability",
                "title": "Requirements Traceability",
                "status": "complete",
                "summary": "The processing pass completed.",
                "evidence": [],
                "findings": [],
                "unavailable": [
                    "Authoritative stakeholder requirements were not supplied."
                ],
            },
            {
                "stage_id": "historical_trends_and_change_failure",
                "title": "Historical Trends and Change Failure",
                "status": "complete",
                "summary": "Historical processing completed.",
                "evidence": [],
                "findings": [],
                "unavailable": ["Production incident history was unavailable."],
            },
            {
                "stage_id": "decision_report_generation",
                "title": "Core Decision Report",
                "status": "complete",
                "summary": "Core report generation completed.",
                "evidence": ["report_package.pdf_page_count: 37"],
                "findings": [],
                "unavailable": [],
            },
            {
                "stage_id": "deployment_and_infrastructure",
                "title": "Deployment and Infrastructure",
                "status": "complete",
                "summary": "Deployment evidence was collected.",
                "evidence": [
                    "Observed deployments: 17",
                    "Successful deployments: 11",
                    "Non-success deployments: 6",
                    "Non-success deployment classification: 2",
                ],
                "findings": [],
                "unavailable": [],
            },
        ],
    }


def test_projection_changes_only_client_presentation_truth() -> None:
    canonical = _canonical_fixture()
    before = deepcopy(canonical)

    projected = project_canonical_for_client_presentation(canonical)

    assert canonical == before
    stages = {item["stage_id"]: item for item in projected["stage_summaries"]}

    requirements = stages["requirements_traceability"]
    assert requirements["status"] == (
        "processing complete · authoritative requirements not supplied"
    )
    assert canonical["stage_summaries"][0]["status"] == "complete"

    history = stages["historical_trends_and_change_failure"]
    assert history["status"] == "processing complete · evidence limited"

    core = stages["decision_report_generation"]
    assert core["evidence"] == [
        "Core decision-report PDF page count: 37 "
        "(intermediate artifact; not final assembled report length)."
    ]
    assert "pdf_page_count" not in " ".join(core["evidence"])

    deployment = stages["deployment_and_infrastructure"]
    rendered = "\n".join(deployment["evidence"])
    assert "observed=17" in rendered
    assert "successful=11" in rendered
    assert "failed/non-success=2" in rendered
    assert "unresolved=4" in rendered
    assert "Non-success deployments: 6" not in rendered
    assert "Non-success deployment classification: 2" not in rendered


def test_final_navigation_is_rebuilt_after_shared_page_compaction() -> None:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(48, 744, "NICO Comprehensive | AUTOMATED DRAFT")
    pdf.showPage()
    pdf.drawString(48, 744, "Table of Contents")
    pdf.drawString(48, 710, "Code Audit")
    pdf.showPage()
    pdf.drawString(48, 744, "Code Audit")
    pdf.drawString(48, 710, "Dependency / Library Ecosystem")
    pdf.drawString(48, 676, "Secrets Exposure Review")
    pdf.showPage()
    pdf.save()
    source = buffer.getvalue()

    finalized = _finalize_artifact_navigation(
        {"pdf_base64": base64.b64encode(source).decode("ascii")},
        {},
    )
    rendered = base64.b64decode(finalized["pdf_base64"])
    reader = PdfReader(io.BytesIO(rendered))
    toc = reader.pages[1].extract_text() or ""

    assert toc.count("Table of Contents") == 1
    assert "Code Audit" in toc
    assert "Dependency / Library Ecosystem" in toc
    assert "Secrets Exposure Review" in toc
    assert "FOUR-PHASE ASSESSMENT PROGRAM" in toc
    assert finalized["pagination_compaction"][
        "final_navigation_rebuilt_after_compaction"
    ] is True


def test_same_run_route_binds_final_layout_before_actual_render_target() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "nico"
        / "comprehensive_commercial_ship_projection_v3.py"
    ).read_text(encoding="utf-8")

    assert "current_render_target = locale_report._render_target" in source
    assert "locale_report._render_target = localized_render_target" in source
    assert "return _finalize_artifact_navigation(artifacts, navigation_truth)" in source
    render_wrapper = source.index("def localized_render_target(")
    bind_layout = source.index("_bind_final_pdf_layout()", render_wrapper)
    render_artifacts = source.index(
        "artifacts = current_render_target(canonical, report_language)",
        render_wrapper,
    )
    assert bind_layout < render_artifacts

    layout = _bind_final_pdf_layout()
    assert layout["toc_rows_per_page"] == 35
    assert layout["review_companion_pages"] == 4
    assert layout["review_small_font_size"] >= 6.75


def test_final_navigation_replaces_spanish_indice_and_keeps_35_rows_on_one_page() -> None:
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(48, 744, "NICO Comprehensive | BORRADOR AUTOMATIZADO")
    pdf.showPage()
    pdf.drawString(48, 744, "Índice")
    pdf.drawString(48, 710, "Evaluación Técnica Integral")
    pdf.showPage()
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for section in CANONICAL_TOC_SECTIONS:
        if section["section_id"] == "canonical_technical_scorecard":
            if current:
                chunks.append(current)
                current = []
            chunks.append([section])
            continue
        current.append(section)
        if len(current) == 6:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)

    for chunk in chunks:
        y = 744
        pdf.drawString(48, y, "NICO Comprehensive | BORRADOR AUTOMATIZADO")
        y -= 28
        for section in chunk:
            pdf.drawString(48, y, section["title_es"])
            y -= 38
        pdf.showPage()
    pdf.save()

    finalized = _finalize_artifact_navigation(
        {"pdf_base64": base64.b64encode(buffer.getvalue()).decode("ascii")},
        {"identity": {"report_language": "es-MX"}},
    )
    reader = PdfReader(io.BytesIO(base64.b64decode(finalized["pdf_base64"])))
    toc = reader.pages[1].extract_text() or ""
    next_page = reader.pages[2].extract_text() or ""

    assert len(CANONICAL_TOC_SECTIONS) == 35
    assert "Tabla de contenido" in toc
    assert "PROGRAMA DE EVALUACIÓN EN CUATRO FASES" in toc
    assert not any(
        line.strip() == "Índice"
        for page in reader.pages
        for line in (page.extract_text() or "").splitlines()
    )
    assert "Tabla de contenido" not in next_page
    for section in CANONICAL_TOC_SECTIONS:
        assert section["title_es"] in toc


def test_provider_access_truth_is_not_limited_to_generic_ten_line_preview() -> None:
    from nico.comprehensive_report_package import _pdf

    snapshot = "assessment_snapshot_id: snapshot_provider_preview_contract"
    evidence = [f"provider access evidence line {index}" for index in range(29)]
    evidence[20] = snapshot
    encoded, error, _page_count = _pdf(
        {
            "run_id": "comprun_provider_preview_contract",
            "repository": "example/public-repository",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_provider_preview_contract",
        },
        {},
        [
            {
                "stage_id": "repository_and_delivery_evidence",
                "title": "Repository and Delivery Evidence",
                "status": "complete",
                "summary": "Frozen public-provider access truth.",
                "evidence": evidence,
                "findings": [],
                "unavailable": [],
            }
        ],
        "2026-09-01T00:00:00Z",
    )

    assert error is None
    assert encoded
    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(base64.b64decode(encoded))).pages
    )
    # Once in the client-facing decision body and once in the full evidence appendix.
    assert text.count(snapshot) == 2


def test_deployment_projection_does_not_guess_failure_split() -> None:
    canonical = {
        "stage_summaries": [
            {
                "stage_id": "deployment_and_infrastructure",
                "title": "Deployment and Infrastructure",
                "status": "complete",
                "summary": "Deployment evidence was collected.",
                "evidence": [
                    "GitHub deployment evidence: observed=23, success=19, non-success=4."
                ],
                "findings": [],
                "unavailable": [],
            }
        ]
    }

    projected = project_canonical_for_client_presentation(canonical)
    text = "\n".join(projected["stage_summaries"][0]["evidence"])
    assert "observed=23" in text
    assert "successful=19" in text
    assert "failed/non-success=not separately evidenced" in text
    assert "unresolved=not separately evidenced" in text
    assert "failed-or-unresolved remainder=4" in text


def test_spanish_projection_localizes_dynamic_deployment_taxonomy() -> None:
    source = (
        "Deployment outcome taxonomy (unscored context): observed=10; "
        "successful=6; failed/non-success=not separately evidenced; "
        "unresolved=not separately evidenced; failed-or-unresolved remainder=4."
    )

    translated = localize_current_report_copy_v98(source)

    assert translated == (
        "Taxonomía de resultados de despliegue (contexto sin puntuación): "
        "observados=10; exitosos=6; fallidos/no exitosos=no se evidenciaron "
        "por separado; no resueltos=no se evidenciaron por separado; "
        "remanente fallido o no resuelto=4."
    )

    score_boundary = (
        "Canonical scoring is reconciled to retained evidence without recomputing "
        "or inflating either score; evidence limitations remain explicit. Candidate "
        "volume and reviewer workload are operational review metrics and have no "
        "numeric technical-maturity or Evidence-Adjusted score effect."
    )
    translated_boundary = localize_current_report_copy_v98(score_boundary)
    assert "Canonical scoring is reconciled" not in translated_boundary
    assert "Candidate volume and reviewer workload" not in translated_boundary
    assert "La puntuación canónica se concilia con la evidencia conservada" in (
        translated_boundary
    )
    assert "no tienen efecto numérico" in translated_boundary

    jobs_without_numerator = (
        "Workflow jobs: 23 observed; successful count and success rate are not "
        "reported because a supported numerator was not retained."
    )
    translated_jobs = localize_current_report_copy_v98(jobs_without_numerator)
    assert translated_jobs == (
        "Trabajos de flujo de trabajo: 23 observados; no se informan el conteo "
        "exitoso ni la tasa de éxito porque no se conservó un numerador compatible."
    )

    metadata_boundary = (
        "Client and project display metadata are descriptive and do not replace "
        "canonical scope identifiers."
    )
    assert localize_current_report_copy_v98(metadata_boundary) == (
        "Los metadatos descriptivos del cliente y del proyecto no sustituyen los "
        "identificadores canónicos de alcance."
    )

    complexity_acceptance = (
        "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
        "nico/comprehensive_approved_delivery_v4.py:338"
    )
    assert localize_current_report_copy_v98(complexity_acceptance) == (
        "La nueva ejecución con SHA exacto ya no informa una complejidad ciclomática "
        "superior a 30 en nico/comprehensive_approved_delivery_v4.py:338"
    )
    assert localize_current_report_copy_v98(
        "Complexity risk: observed; 50 exact-source complexity findings remain "
        "pending human review."
    ) == (
        "Riesgo de complejidad: observado; 50 hallazgos de complejidad con fuente "
        "exacta siguen pendientes de revisión humana."
    )
    assert localize_current_report_copy_v98(
        "The repository's complete required-check suite passes on the remediation commit"
    ) == (
        "El conjunto completo de comprobaciones requeridas del repositorio se aprueba "
        "en el commit de remediación"
    )
    assert localize_current_report_copy_v98(
        "No new material regression or cross-format report-truth mismatch is introduced"
    ) == (
        "No se introduce ninguna regresión material nueva ni discrepancia de verdad "
        "del informe entre formatos"
    )


def test_pending_frozen_source_with_suppressed_known_hashes_is_reprojected() -> None:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(54, 720, "Client Artifact Manifest")
    pdf.drawString(54, 700, "findings_csv | findings.csv | Not available")
    pdf.save()
    artifact_types = (
        "findings_csv",
        "evidence_csv",
        "candidate_register_json",
        "remediation_backlog_json",
        "markdown_report",
        "html_report",
    )
    status = {
        "human_review_required": True,
        "human_review_completed": False,
        "approval_status": "pending_human_approval",
        "client_delivery_allowed": False,
        "reports": {
            "pdf_base64": base64.b64encode(buffer.getvalue()).decode(),
            "artifact_manifest": {
                "artifacts": [
                    {"artifact_type": kind, "sha256": f"{index + 1}" * 64}
                    for index, kind in enumerate(artifact_types)
                ]
            },
        },
    }

    assert _source_pdf_requires_integrity_reprojection(status, "en") is True

    status["human_review_completed"] = True
    status["approval_status"] = "approved"
    status["client_delivery_allowed"] = True
    assert _source_pdf_requires_integrity_reprojection(status, "en") is False


def test_pending_frozen_source_with_footer_only_spill_is_reprojected() -> None:
    artifact_types = (
        "findings_csv",
        "evidence_csv",
        "candidate_register_json",
        "remediation_backlog_json",
        "markdown_report",
        "html_report",
    )
    digests = {
        kind: f"{index + 1}" * 64
        for index, kind in enumerate(artifact_types)
    }
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    header = "NICO Comprehensive · comprun_footer_fixture · AUTOMATED DRAFT"
    pdf.drawString(54, 760, header)
    pdf.drawString(54, 720, "Client Artifact Manifest")
    for index, digest in enumerate(digests.values()):
        pdf.drawString(54, 690 - index * 18, digest)
    pdf.drawString(54, 36, "Document page 1 of 2")
    pdf.showPage()
    pdf.drawString(54, 760, header)
    pdf.drawString(54, 36, "Document page 2 of 2")
    pdf.save()
    status = {
        "human_review_required": True,
        "human_review_completed": False,
        "approval_status": "pending_human_approval",
        "client_delivery_allowed": False,
        "reports": {
            "pdf_base64": base64.b64encode(buffer.getvalue()).decode(),
            "artifact_manifest": {
                "artifacts": [
                    {"artifact_type": kind, "sha256": digest}
                    for kind, digest in digests.items()
                ]
            },
        },
    }

    assert _source_pdf_requires_integrity_reprojection(status, "en") is True


def test_pending_frozen_source_with_stale_scanner_denominator_is_reprojected() -> None:
    node_failures = {
        "npm-audit": "No package-lock.json with an adjacent package.json was found.",
        "eslint": "No supported JavaScript or TypeScript source files were found in apps/web/app.",
        "typescript": "Project dependencies were not prepared.",
    }
    tools = (
        "pip-audit",
        "npm-audit",
        "osv-scanner",
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
        "gitleaks",
        "trufflehog",
    )
    records = [
        {
            "scanner_name": name,
            "status": (
                "unavailable"
                if name == "typescript"
                else "failed" if name in node_failures else "completed"
            ),
            "state": (
                "unavailable"
                if name == "typescript"
                else "failed" if name in node_failures else "completed"
            ),
            "completed": name not in node_failures,
            "verified": name not in node_failures,
            "exact_commit_match": True,
            "artifact_hash": "" if name in node_failures else "a" * 64,
            "failure_reason": node_failures.get(name, ""),
            "findings": [],
        }
        for name in tools
    ]
    canonical = {
        "identity": {"commit_sha": "a" * 40},
        "repository_evidence": {
            "file_evidence": {"sampled_paths": ["requirements.txt", "app.py"]}
        },
        "assessment": {"technical_score": 76},
        "requested_scanner_records": deepcopy(records),
        "scanner_execution_records": deepcopy(records),
    }
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    pdf.drawString(54, 720, "6 of 9 applicable scanner executions completed")
    pdf.save()
    status = {
        "human_review_required": True,
        "human_review_completed": False,
        "approval_status": "pending_human_approval",
        "client_delivery_allowed": False,
        "reports": {
            "json": canonical,
            "pdf_base64": base64.b64encode(buffer.getvalue()).decode(),
            "markdown": "6 of 9 applicable scanner executions completed",
            "html": "<p>6 of 9 applicable scanner executions completed</p>",
        },
    }

    assert _source_pdf_requires_integrity_reprojection(status, "en") is True


def _pdf_with_sparse_limitation_pair() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)

    document.drawString(72, 740, "Canonical Technical Scorecard")
    document.drawString(72, 720, "Dense evidence page remains unchanged")
    document.showPage()

    document.drawString(72, 740, "Six-Month Roadmap")
    document.drawString(72, 710, "Unavailable or Limited Evidence")
    document.drawString(72, 690, "Validated roadmap evidence was not supplied.")
    document.showPage()

    document.drawString(72, 740, "Staffing, Sequencing, and Cost")
    document.drawString(72, 710, "Unavailable or Limited Evidence")
    document.drawString(72, 690, "Authoritative staffing assumptions were not supplied.")
    document.showPage()

    document.drawString(72, 740, "Human Review and Acceptance Gate")
    document.drawString(72, 720, "Human approval remains pending.")
    document.save()
    return buffer.getvalue()


def test_sparse_roadmap_staffing_pages_compact_without_losing_text() -> None:
    original = _pdf_with_sparse_limitation_pair()
    compacted, manifest = compact_sparse_limitation_pages(original)

    assert manifest["status"] == "compacted"
    assert manifest["original_pages"] == 4
    assert manifest["final_pages"] == 3
    assert manifest["pages_removed"] == 1
    assert manifest["truth_preserved"] is True

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(compacted)).pages
    )
    assert "Six-Month Roadmap" in text
    assert "Validated roadmap evidence was not supplied." in text
    assert "Staffing, Sequencing, and Cost" in text
    assert "Authoritative staffing assumptions were not supplied." in text
    assert "Human Review and Acceptance Gate" in text


def _pdf_with_sparse_ordinary_sections() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    header = "NICO Comprehensive · comprun_dynamic_fixture · AUTOMATED DRAFT"
    sections = [
        ("Code audit", "Executable code-risk findings: 0."),
        ("Dependency / Library Ecosystem", "Review-required dependency candidates: 21."),
        ("Secrets Exposure Review", "Review-required secret candidates: 19."),
        ("Static Analysis", "Review-required static candidates: 664."),
        ("CI/CD Analysis", "Workflow configuration exact-SHA match: True."),
        ("Architecture & Technical Debt", "Complexity risk remains pending human review."),
        ("Velocity / Complexity", "Mutable activity volume remains unscored context."),
    ]
    for title, evidence in sections:
        document.drawString(54, 760, header)
        document.drawString(54, 720, title)
        document.drawString(54, 690, evidence)
        document.drawString(54, 670, "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED")
        document.showPage()

    document.drawString(54, 760, header)
    document.drawString(54, 720, "Human Review and Acceptance Gate")
    document.drawString(54, 690, "Only an authorized human reviewer may approve the exact artifact.")
    document.save()
    return buffer.getvalue()


def test_sparse_ordinary_sections_reflow_without_touching_review_gate() -> None:
    original = _pdf_with_sparse_ordinary_sections()
    compacted, manifest = compact_sparse_limitation_pages(original)

    assert manifest["status"] == "compacted"
    assert manifest["original_pages"] == 8
    assert manifest["final_pages"] < 8
    assert manifest["pages_removed"] >= 3
    assert manifest["truth_preserved"] is True
    assert manifest["canonical_truth_mutated"] is False

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(compacted)).pages
    )
    for marker in (
        "Code audit",
        "Dependency / Library Ecosystem",
        "Secrets Exposure Review",
        "Static Analysis",
        "CI/CD Analysis",
        "Architecture & Technical Debt",
        "Velocity / Complexity",
        "Human Review and Acceptance Gate",
        "Only an authorized human reviewer may approve the exact artifact.",
    ):
        assert marker in text


def test_review_pdf_and_markdown_bridges_never_silently_noop() -> None:
    pdf_source = Path("apps/web/app/AssessmentReviewPdfDownload.tsx").read_text(
        encoding="utf-8"
    )
    markdown_source = Path("apps/web/app/AssessmentMarkdownCopyBridge.tsx").read_text(
        encoding="utf-8"
    )
    layout = Path("apps/web/app/layout.tsx").read_text(encoding="utf-8")

    # One user gesture must produce one browser-native PDF navigation attempt. The old
    # window.open + fallback-anchor sequence could dispatch twice when noopener caused
    # window.open to return null after navigation had already started.
    assert "const opened = window.open" not in pdf_source
    assert pdf_source.count("link.click();") == 1
    assert "visibleRunId" in pdf_source
    assert "AUTOMATED-DRAFT-PENDING-APPROVAL.pdf" in pdf_source
    assert "PDF requested. Check the new tab or your downloads." in pdf_source
    assert "data-nico-review-pdf-action-status" in pdf_source

    assert "loadMarkdown" in markdown_source
    assert "navigator.clipboard.writeText" in markdown_source
    assert 'document.execCommand("copy")' in markdown_source
    assert "Markdown copied." in markdown_source
    assert "Markdown could not be copied." in markdown_source
    assert "visibleRunId" in markdown_source
    assert 'actions.getAttribute("data-assessment-report-ready") !== "true"' in markdown_source

    assert 'import AssessmentMarkdownCopyBridge from "./AssessmentMarkdownCopyBridge"' in layout
    assert layout.index("<AssessmentReviewPdfDownload />") < layout.index("<AssessmentHomeRedirect />")
    assert layout.index("<AssessmentMarkdownCopyBridge />") < layout.index("<AssessmentHomeRedirect />")


def test_real_runtime_and_renderer_install_report_metadata_integrity() -> None:
    production = Path("nico/api/same_run_locale_report_bootstrap.py").read_text(
        encoding="utf-8"
    )
    worker = Path("nico/api/final_report_worker_bootstrap.py").read_text(
        encoding="utf-8"
    )

    for source in (production, worker):
        assert "install_comprehensive_report_review_integrity_v1" in source
        assert "REPORT_REVIEW_INTEGRITY" in source
        assert "primary_technical_contact_projected_from_human_evidence" in source
        assert "client_delivery_allowed" in source

    assert "display_metadata_persisted_in_initial_canonical_write" in production
    assert '"report_review_integrity_bound": True' in worker
