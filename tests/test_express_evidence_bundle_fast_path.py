from __future__ import annotations

import base64
import json
import time

from nico.express_evidence_bundle_fast_path import attach_express_evidence_bundle, build_express_evidence_bundle


def _pdf() -> str:
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n").decode("ascii")


def _result() -> dict:
    huge_findings = [{"id": index, "detail": "x" * 4000} for index in range(5000)]
    return {
        "assessment_type": "express",
        "repository": "BoneManTGRM/NICO",
        "reports": {
            "markdown": "# Report\n" + "content " * 500,
            "html": "<html><body>report</body></html>",
            "pdf_base64": _pdf(),
        },
        "sections": [{"id": "architecture", "label": "Architecture", "score": 81, "evidence": ["verified"]}],
        "maturity_signal": {"score": 81, "label": "managed"},
        "scanner_worker_artifact": {
            "tools": {
                "large_tool": {
                    "status": "completed",
                    "completed": True,
                    "current_run": True,
                    "finding_count": len(huge_findings),
                    "findings": huge_findings,
                }
            }
        },
        "findings": huge_findings,
        "human_review_required": True,
    }


def test_express_bundle_does_not_recursively_embed_large_scanner_payloads() -> None:
    result = _result()
    started = time.monotonic()
    output = attach_express_evidence_bundle(result)
    elapsed = time.monotonic() - started

    assert elapsed < 3.0
    assert output["reports"]["markdown"] == result["reports"]["markdown"]
    assert output["reports"]["html"] == result["reports"]["html"]
    assert output["reports"]["pdf_base64"] == result["reports"]["pdf_base64"]
    assert output["sections"] == result["sections"]
    assert output["maturity_signal"] == result["maturity_signal"]

    encoded = output["reports"]["evidence_bundle_json"].encode("utf-8")
    assert len(encoded) < 2_000_000
    assert b'"findings": [' not in encoded
    assert b'"finding_count": 5000' in encoded


def test_bundle_contains_structural_artifact_proof_and_human_review_guardrail() -> None:
    bundle = build_express_evidence_bundle(_result())
    assert bundle["artifacts"]["markdown"]["available"] is True
    assert bundle["artifacts"]["html"]["available"] is True
    assert bundle["artifacts"]["pdf"]["available"] is True
    assert bundle["artifacts"]["pdf"]["structurally_valid"] is True
    assert bundle["human_review_required"] is True
    assert bundle["evidence_ledger"]["human_review_required"] is True
    assert len(bundle["bundle_hash"]) == 64
    assert len(bundle["evidence_ledger"]["ledger_hash"]) == 64


def test_bundle_json_is_stable_and_json_native() -> None:
    output = attach_express_evidence_bundle(_result())
    decoded = json.loads(output["reports"]["evidence_bundle_json"])
    assert decoded["artifact_schema"] == "nico.evidence_bundle.v2"
    assert decoded["bounded"] is True
    assert decoded["raw_evidence_summary"]["finding_count"] == 5000
