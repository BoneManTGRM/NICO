from __future__ import annotations

import base64

from nico.express_final_gate_completion_patch import normalize_assessment_completion


def _pdf() -> str:
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n").decode("ascii")


def _complete(tier: str = "express") -> dict:
    return {
        "assessment_type": tier,
        "status": "running",
        "reports": {
            "markdown": "# Report",
            "html": "<h1>Report</h1>",
            "pdf_base64": _pdf(),
        },
        "sections": [{"id": "architecture", "score": 82}],
        "maturity_signal": {"score": 82, "level": "Senior"},
    }


def test_complete_express_contract_exposes_each_format_readiness_flag() -> None:
    result = normalize_assessment_completion(_complete(), _complete())
    completion = result["assessment_completion"]
    assert completion["markdown_ready"] is True
    assert completion["html_ready"] is True
    assert completion["pdf_ready"] is True
    assert completion["report_formats_ready"] is True
    assert completion["sections_ready"] is True
    assert completion["score_ready"] is True
    assert result["express_completion"] == completion


def test_truncated_pdf_cannot_satisfy_pdf_or_aggregate_readiness() -> None:
    value = _complete()
    value["reports"]["pdf_base64"] = base64.b64encode(b"%PDF-1.4 truncated").decode("ascii")
    result = normalize_assessment_completion(value, value)
    completion = result["assessment_completion"]
    assert completion["markdown_ready"] is True
    assert completion["html_ready"] is True
    assert completion["pdf_ready"] is False
    assert completion["report_formats_ready"] is False
    assert "pdf" in completion["missing"]


def test_mid_and_full_hash_artifacts_expose_same_readiness_contract() -> None:
    for tier in ("mid", "full"):
        value = {
            "assessment_type": tier,
            "status": "running",
            "evidence_artifact_bundle": {
                "artifacts": {
                    "markdown": {"available": True, "sha256": "a" * 64},
                    "html": {"available": True, "sha256": "b" * 64},
                    "pdf": {"available": True, "sha256": "c" * 64},
                }
            },
            "sections": [{"id": "architecture", "score": 75}],
            "maturity_signal": {"score": 75},
        }
        result = normalize_assessment_completion(value, value)
        completion = result["assessment_completion"]
        assert completion["markdown_ready"] is True
        assert completion["html_ready"] is True
        assert completion["pdf_ready"] is True
        assert completion["report_formats_ready"] is True
        assert completion["status"] == "complete_pending_human_review"
        assert "express_completion" not in result
