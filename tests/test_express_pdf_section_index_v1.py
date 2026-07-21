from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.express_pdf_section_index_v1 import append_canonical_section_index


def _base_pdf() -> str:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(612, 792), invariant=1)
    pdf.drawString(72, 720, "NICO Express report")
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _section(section_id: str, label: str, score, status: str, directly_scored: bool = True) -> dict:
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "presented_score": score,
        "status": status,
        "presented_status": status,
        "directly_scored": directly_scored,
    }


def _pdf_text(encoded: str) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(base64.b64decode(encoded)))
    return len(reader.pages), "\n".join(page.extract_text() or "" for page in reader.pages)


def test_append_index_preserves_exact_labels_scores_and_not_scored_controls() -> None:
    result = {
        "maturity_signal": {"score": 90, "source_score": 90, "presented_score": 82},
        "evidence_adjusted_score": 82,
        "sections": [
            _section("code_audit", "Code Audit", 86, "green"),
            _section("dependency_health", "Dependency / Library Ecosystem", 87, "yellow"),
            _section("secrets_review", "Secrets Exposure Review", 73, "yellow"),
            _section("static_analysis", "Static Analysis", 72, "yellow"),
            _section("ci_cd", "CI/CD Analysis", 92, "yellow"),
            _section("architecture_debt", "Architecture & Technical Debt", 86, "yellow"),
            _section("velocity_complexity", "Velocity / Complexity", 77, "yellow"),
            _section(
                "scanner_worker_evidence",
                "Scanner Worker Evidence",
                None,
                "supplemental",
                directly_scored=False,
            ),
            _section(
                "client_human_acceptance",
                "Client / Human Acceptance",
                None,
                "gray",
                directly_scored=False,
            ),
        ],
        "reports": {"pdf_base64": _base_pdf()},
    }

    append_canonical_section_index(result)

    pages, text = _pdf_text(result["reports"]["pdf_base64"])
    assert pages == 2
    for section in result["sections"]:
        assert section["label"] in text
    for score in ("86/100", "87/100", "73/100", "72/100", "92/100", "77/100"):
        assert score in text
    assert "NOT SCORED" in text
    assert "Source maturity score: 90/100" in text
    assert "Evidence-adjusted score: 82/100" in text
    contract = result["express_pdf_section_index"]
    assert contract["canonical_labels_present"] is True
    assert contract["canonical_scores_present"] is True
    assert contract["index_appended"] is True
    assert contract["missing_labels_after"] == []


def test_index_is_idempotent_when_every_label_is_already_present() -> None:
    result = {
        "maturity_signal": {"score": 80, "presented_score": 80},
        "sections": [_section("code_audit", "Code Audit", 80, "green")],
        "reports": {"pdf_base64": _base_pdf()},
    }

    append_canonical_section_index(result)
    first_pages, _ = _pdf_text(result["reports"]["pdf_base64"])
    append_canonical_section_index(result)
    second_pages, text = _pdf_text(result["reports"]["pdf_base64"])

    assert first_pages == second_pages == 2
    assert text.count("Canonical Section and Score Index") == 1
    assert result["express_pdf_section_index"]["index_appended"] is False
