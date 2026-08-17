from __future__ import annotations

import io

from pypdf import PdfReader
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico import comprehensive_artifact_manifest_approval_v1 as manifest
from nico.comprehensive_spanish_client_surface_localization_v86 import (
    EN_BOUNDARY,
    ES_BOUNDARY,
    SPANISH_APPROVAL_TITLE,
    SPANISH_MANIFEST_TITLE,
    _english_status_only,
    _localize_presentation_text,
    _render_spanish_manifest,
    _spanish_markdown_manifest,
    _transform_pdf_text,
    localize_spanish_markdown,
)


def _pdf_text(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def _normalized_pdf_text(pdf: bytes) -> str:
    return " ".join(_pdf_text(pdf).split())


def _canonical() -> dict:
    return {
        "report_language": "en",
        "identity": {
            "report_language": "es-MX",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "run_id": "comprun_spanish_surface_localization",
            "evidence_ledger_id": "ledger-spanish-surface",
            "generated_at": "2026-08-16T19:00:00Z",
        },
        "lifecycle": {
            "review_package_ready": True,
            "human_review_status": "pending",
            "client_delivery_status": "blocked",
        },
        "approval": {
            "decision": "pending",
            "reviewer_authorized": False,
        },
    }


def _entries() -> list[dict]:
    return [
        {
            "artifact_type": "findings_csv",
            "filename": "nico-comprun_spanish_surface_localization-findings.csv",
            "sha256": "b" * 64,
        },
        {
            "artifact_type": "evidence_csv",
            "filename": "nico-comprun_spanish_surface_localization-evidence.csv",
            "sha256": "c" * 64,
        },
    ]


def test_markdown_localization_translates_presentation_but_preserves_code() -> None:
    source = """## Client Artifact Manifest

DRAFT · HUMAN REVIEW REQUIRED

Decision findings: 4
Observed workflow runs: 9

```python
status = "DRAFT · HUMAN REVIEW REQUIRED"
heading = "Client Artifact Manifest"
```

Keep `Client Artifact Manifest` and `src/report.py:42` literal.
"""

    localized = localize_spanish_markdown(source)

    assert f"## {SPANISH_MANIFEST_TITLE}" in localized
    assert ES_BOUNDARY in localized
    assert "Hallazgos de decisión: 4" in localized
    assert "Ejecuciones observadas de flujos de trabajo: 9" in localized
    assert 'status = "DRAFT · HUMAN REVIEW REQUIRED"' in localized
    assert 'heading = "Client Artifact Manifest"' in localized
    assert "`Client Artifact Manifest`" in localized
    assert "`src/report.py:42`" in localized


def test_spanish_manifest_pdf_is_fully_localized_and_keeps_exact_artifacts() -> None:
    pdf = _render_spanish_manifest(manifest, _canonical(), _entries())
    extracted = _pdf_text(pdf)
    normalized = _normalized_pdf_text(pdf)

    assert SPANISH_MANIFEST_TITLE in normalized
    assert SPANISH_APPROVAL_TITLE in normalized
    assert "Artefactos estructurados preservados" in extracted
    assert "Repositorio" in extracted
    assert "Commit exacto" in extracted
    assert "ID de ejecución" in extracted
    assert "Paquete de revisión listo: Sí" in extracted
    assert "Aprobación humana: Pendiente" in extracted
    assert "Entrega al cliente: Bloqueada" in extracted
    assert ES_BOUNDARY in extracted
    assert "nico-comprun_spanish_surface_localization-findings.csv" in extracted
    assert "b" * 64 in extracted.replace("\n", "")
    assert "Client Artifact Manifest" not in extracted
    assert "Human Review and Exact-Artifact Approval Record" not in extracted
    assert "Review package ready" not in extracted


def test_spanish_markdown_manifest_translates_labels_and_preserves_hashes() -> None:
    identity = manifest._canonical_identity(_canonical())
    markdown = _spanish_markdown_manifest(
        manifest,
        identity,
        _entries(),
        pdf_sha256="d" * 64,
        canonical_json_sha256="e" * 64,
        manifest_sha256="f" * 64,
    )

    assert f"## {SPANISH_MANIFEST_TITLE}" in markdown
    assert f"## {SPANISH_APPROVAL_TITLE}" in markdown
    assert "- Repositorio: BoneManTGRM/NICO" in markdown
    assert "- Aprobación humana: Pendiente" in markdown
    assert "- Entrega al cliente: Bloqueada" in markdown
    assert "d" * 64 in markdown
    assert "e" * 64 in markdown
    assert "f" * 64 in markdown
    assert "Client Artifact Manifest" not in markdown
    assert "Human Review and Exact-Artifact Approval Record" not in markdown


def test_pdf_localization_removes_stale_review_status_without_touching_literals() -> None:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buffer, invariant=1).build(
        [
            Paragraph("QA funcional", styles["BodyText"]),
            Paragraph("DRAFT · HUMAN REVIEW REQUIRED", styles["BodyText"]),
            Paragraph("Client Artifact Manifest", styles["BodyText"]),
            Paragraph("src/report.py:42", styles["BodyText"]),
            Paragraph("a" * 40, styles["BodyText"]),
        ]
    )

    localized = _transform_pdf_text(buffer.getvalue(), _localize_presentation_text)
    extracted = _pdf_text(localized)

    assert ES_BOUNDARY in extracted
    assert SPANISH_MANIFEST_TITLE in extracted
    assert "DRAFT · HUMAN REVIEW REQUIRED" not in extracted
    assert "Client Artifact Manifest" not in extracted
    assert "src/report.py:42" in extracted
    assert "a" * 40 in extracted.replace("\n", "")


def test_english_stale_review_status_normalizes_without_spanish_translation() -> None:
    normalized = _english_status_only("DRAFT · HUMAN REVIEW REQUIRED")

    assert normalized == EN_BOUNDARY
    assert "BORRADOR" not in normalized


def test_known_review_evidence_labels_are_localized() -> None:
    value = (
        "Decision findings: 7 | Exact-source findings: 5 | "
        "Confirmed material scanner findings: 3 | "
        "Review-required scanner candidates: 2 | "
        "Observed workflow runs: 14 | Outcome taxonomy: success=12"
    )
    localized = _localize_presentation_text(value)

    assert "Hallazgos de decisión: 7" in localized
    assert "Hallazgos con ubicación exacta: 5" in localized
    assert "Hallazgos materiales confirmados por analizadores: 3" in localized
    assert "scanner findings" not in localized
    assert "Candidatos de analizadores que requieren revisión: 2" in localized
    assert "Ejecuciones observadas de flujos de trabajo: 14" in localized
    assert "Taxonomía de resultados:" in localized
