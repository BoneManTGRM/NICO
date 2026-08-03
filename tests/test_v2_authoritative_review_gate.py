from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.phase17_canonical_artifact_rebuild_v1 import _AUTHORITATIVE_REVIEW_GATE, rebuild_client_artifacts
from nico.v2_authoritative_review_gate import ensure_authoritative_review_gate

SHA = "8" * 40


def _canonical(language: str = "en") -> dict:
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_review_gate",
            "evidence_ledger_id": "ledger-review-gate",
            "customer_id": "customer-review-gate",
            "project_id": "project-review-gate",
            "report_language": language,
        },
        "report_language": language,
        "assessment": {
            "report_language": language,
            "technical_score": 74,
            "canonical_evidence_adjusted_score": 73,
            "maturity_signal": {
                "level": "Moderate",
                "technical_score": 74,
                "presented_score": 74,
                "score": 74,
                "evidence_adjusted_score": 73,
            },
            "executive_summary": "The immutable package is complete and requires internal review.",
            "sections": [],
            "unavailable_data_notes": [],
        },
        "canonical_findings": [],
        "scanner_execution_records": [],
        "stage_summaries": [
            {
                "stage_id": "human_review_request",
                "title": "Human Review Request",
                "status": "review_required",
                "summary": "Human review is required before delivery.",
                "evidence": [],
                "findings": [],
                "unavailable": [],
            }
        ],
        "roadmap": [],
    }


def _pdf_text(encoded: str) -> str:
    pdf = base64.b64decode(encoded)
    assert pdf.startswith(b"%PDF")
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)


def test_authoritative_review_gate_is_bound_once():
    assert _AUTHORITATIVE_REVIEW_GATE["bound"] is True
    assert _AUTHORITATIVE_REVIEW_GATE["markdown_html_pdf_share_gate"] is True
    assert _AUTHORITATIVE_REVIEW_GATE["client_delivery_remains_blocked"] is True


def test_english_review_gate_renders_in_markdown_html_and_pdf():
    result = rebuild_client_artifacts({"json": _canonical()})
    assert result["markdown"].count("## Human Review and Acceptance Gate") == 1
    assert "Human Review and Acceptance Gate" in result["html"]
    assert "Human Review and Acceptance Gate" in _pdf_text(result["pdf_base64"])
    assert "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED" in result["markdown"]
    assert "Approve or reject this immutable automated draft before delivery." in result["markdown"]
    assert "CLIENT DELIVERY NOT AUTHORIZED" in result["markdown"]
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True


def test_spanish_review_gate_is_localized_and_idempotent():
    canonical = _canonical("es-MX")
    source = "# Informe\n\n## Puerta de revisión y entrega\n\nEntrega bloqueada.\n"
    once = ensure_authoritative_review_gate(source, canonical, spanish=True)
    twice = ensure_authoritative_review_gate(once, canonical, spanish=True)
    assert once == twice
    assert once.count("## Puerta de revisión humana y aceptación") == 1
    assert "Revisión humana: Obligatoria antes de cualquier entrega al cliente." in once
    assert "Entrega al cliente: Bloqueada hasta la aprobación explícita." in once
