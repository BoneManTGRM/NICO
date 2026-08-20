from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader

from nico.comprehensive_delivery_package_v3 import (
    _certificate_page,
    _report_language,
)


def _pdf_text(payload: bytes) -> str:
    return " ".join(
        " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages).split()
    )


def _accepted() -> dict[str, object]:
    return {
        "report_artifact_digest": "a" * 64,
        "accepted_edition_manifest_sha256": "b" * 64,
        "review_work_ledger_sha256": "c" * 64,
        "review_work_source_sha256": "d" * 64,
        "review": {
            "reviewer": "reviewer-123",
            "reviewer_role": "authorized cybersecurity reviewer",
            "decided_at": "2026-08-20T12:00:00+00:00",
            "reason": "Evidence reviewed",
            "approval_certificate_sha256": "e" * 64,
        },
    }


def test_spanish_approval_certificate_has_no_english_delivery_copy() -> None:
    rendered = _pdf_text(_certificate_page(_accepted(), report_language="es-MX"))

    assert "Aprobación final y autorización de entrega al cliente" in rendered
    assert "Aprobación humana final" in rendered
    assert "Autorización de entrega al cliente" in rendered
    assert "APROBADA" in rendered
    assert "AUTORIZADA" in rendered
    assert "Final Approval and Client Delivery Authorization" not in rendered
    assert "Final human approval" not in rendered
    assert "Client-delivery authorization" not in rendered
    assert "Reviewer role" not in rendered
    assert "Decision reason" not in rendered


def test_english_approval_certificate_behavior_is_preserved() -> None:
    rendered = _pdf_text(_certificate_page(_accepted(), report_language="en"))

    assert "Final Approval and Client Delivery Authorization" in rendered
    assert "Final human approval" in rendered
    assert "Client-delivery authorization" in rendered
    assert "Aprobación humana final" not in rendered


def test_delivery_language_prefers_manifest_then_canonical_truth() -> None:
    report = {
        "report_language": "en",
        "json": {"report_language": "es-MX"},
    }
    assert _report_language(report, {"manifest": {"report_language": "es-MX"}}) == "es-MX"
    assert _report_language({"json": {"report_language": "es-MX"}}, {}) == "es-MX"
    assert _report_language({}, {}) == "en"


def test_spanish_public_entrypoint_is_comprehensive_only() -> None:
    home = Path("apps/web/app/es/page.tsx").read_text(encoding="utf-8")
    assessment = Path("apps/web/app/es/assessment/page.tsx").read_text(encoding="utf-8")

    assert "tier=comprehensive" in home
    assert "tier=express" not in home.casefold()
    assert "Express" not in assessment
    assert "NICO Comprehensive" in assessment
