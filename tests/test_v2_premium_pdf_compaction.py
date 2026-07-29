from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.v2_pipeline_adapter import _PDF_COMPACTION

SHA = "9" * 40


def test_premium_pdf_removes_only_metadata_spacer_page():
    assert _PDF_COMPACTION["bound"] is True
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_compact",
            "evidence_ledger_id": "ledger-compact",
            "customer_id": "customer-compact",
            "project_id": "project-compact",
        },
        "assessment": {
            "technical_score": 84,
            "canonical_evidence_adjusted_score": 82,
            "maturity_signal": {"level": "Strong", "score": 84, "presented_score": 84},
            "executive_summary": "Canonical evidence is ready for internal review.",
            "sections": [],
            "unavailable_data_notes": [],
        },
        "canonical_findings": [],
        "scanner_execution_records": [],
        "stage_summaries": [],
    }
    result = rebuild_client_artifacts({"json": canonical})
    reader = PdfReader(io.BytesIO(base64.b64decode(result["pdf_base64"])))
    texts = [" ".join((page.extract_text() or "").split()) for page in reader.pages]

    assert any("Executive Dashboard" in text for text in texts)
    assert any("Executive Decision Brief" in text for text in texts)
    assert not any(
        "Generated:" in text
        and "Service ID:" in text
        and "Executive Decision Brief" not in text
        and len(text) < 700
        for text in texts[2:]
    )
    assert any("Evidence Appendix" in text for text in texts)
