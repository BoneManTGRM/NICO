from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def pdf_text(data: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)


def test_customer_workspace_uses_final_report_and_contextual_pending_states() -> None:
    text = source("apps/web/app/assessment/AssessmentWorkspace.tsx")
    assert "Download final PDF" in text
    assert "Download draft PDF" not in text
    assert "Recorded, not durable" not in text
    assert 'durable: "Persistence"' in text
    assert 'value.includes("unavailable")' in text
    assert "running && scannerUnavailable ? copy.awaitingScanner" in text
    assert "running && (!maturityRawStatus || maturityUnavailable)" in text
    assert "no separate report rewrite is required" in text


def test_postgres_persistence_is_durable_when_available_even_with_false_legacy_flag() -> None:
    text = source("nico/runtime_storage_truth_patch.py")
    assert 'or (adapter == "postgres" and persistence_available)' in text
    assert 'status.get("durability_verified", adapter == "postgres")' not in text


def test_express_cover_is_a_final_report_pending_approval() -> None:
    from nico.express_report_premium_polish_v42 import _cover_pdf

    result = {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "generated_at": "2026-07-23T00:00:00Z",
        "maturity_signal": {"score": 85},
        "evidence_adjusted_score": 80,
        "executive_summary": "Evidence-bound final assessment.",
        "repair_intelligence": {"candidates": []},
    }
    text = pdf_text(_cover_pdf(result, 612, 792))
    assert "FINAL REPORT" in text
    assert "Pending approval" in text
    assert "Draft only" not in text


def test_express_delivery_overlay_describes_approval_not_draft_state() -> None:
    text = source("nico/express_report_delivery_truth_v43.py")
    assert "Final report · pending human approval" in text
    assert "Not approved for client delivery" not in text
    assert '"report_finality": "final"' in text


def test_full_pdf_is_final_but_still_review_gated() -> None:
    from nico.full_assessment_pdf import build_full_assessment_pdf_base64
    import base64

    payload = {
        "repository": "BoneManTGRM/NICO",
        "run_id": "comprun_test",
        "generated_at": "2026-07-23T00:00:00Z",
        "maturity_signal": {"level": "Senior", "score": 85},
        "sections": [],
        "human_review_required": True,
        "client_delivery_verdict": {"status": "human_review_required", "blockers": []},
    }
    encoded, error = build_full_assessment_pdf_base64(payload, report_id="report_test")
    assert not error
    assert encoded
    text = pdf_text(base64.b64decode(encoded))
    assert "FINAL REPORT - PENDING HUMAN APPROVAL" in text
    assert "evidence-bound draft" not in text.casefold()
    assert "DRAFT - HUMAN REVIEW REQUIRED" not in text


def test_full_pipeline_separates_artifact_finality_from_delivery_approval() -> None:
    text = source("nico/full_assessment_trust_pipeline.py")
    assert 'candidate["report_finality"] = "final"' in text
    assert 'candidate["review_status"] = "pending_human_approval"' in text
    assert 'candidate["delivery_status"] = "blocked_pending_human_approval"' in text
    assert 'candidate["status"] = "draft"' not in text
    assert 'guarded_package["draft_only"] = False' in text
    assert 'guarded_package["client_delivery_allowed"] = False' in text


def test_final_review_gate_treats_report_as_final_and_approval_as_pending() -> None:
    text = source("nico/client_final_review_gate_patch.py")
    assert '"report_finality": "final"' in text
    assert '"approval_status": "pending_human_approval"' in text
    assert '"automation_finality": "final_report_pending_human_approval"' in text
    assert '"client_delivery_allowed": False' in text
    assert '"automation_finality": "not_final"' not in text
