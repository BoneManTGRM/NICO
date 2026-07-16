from __future__ import annotations

import base64
from copy import deepcopy

from nico.report_quality_gate import audit_report_record, evaluate_report_payload, evaluate_rendered_formats


def _section(index: int) -> dict:
    return {
        "id": f"section_{index}",
        "label": f"Technical Section {index}",
        "score": 80 - index,
        "truth_status": "Verified with limitations",
        "summary": "Evidence shows a bounded technical condition with explicit limitations and no unsupported assurance claim.",
        "evidence": [f"Retained exact-run evidence item {index} supports this bounded conclusion."],
        "findings": [f"Evidence-bound finding {index} requires reviewed disposition."],
        "unavailable": ["Exhaustive absence of defects cannot be proven by automated analysis."],
        "human_review_required": True,
    }


def _payload() -> dict:
    return {
        "status": "draft",
        "run_id": "midrun_quality_gate_test",
        "repository": "owner/repository",
        "snapshot_commit_sha": "a" * 40,
        "executive_summary": {
            "assessment": "The exact repository snapshot demonstrates useful engineering foundations, while dependency, static-analysis, and operational limitations remain explicitly disclosed for human review.",
            "decision": "No client delivery or remediation action is authorized by this draft.",
        },
        "decision_summary": {
            "technical_maturity": "Mid",
            "technical_score": 76,
            "recommended_actions": [
                "Review the retained scanner findings and disposition every material item.",
                "Re-run the exact evidence suite after approved remediation.",
            ],
        },
        "sections": [_section(index) for index in range(1, 8)],
        "evidence_coverage": {
            "percent": 87.5,
            "numerator": 14,
            "denominator": 16,
            "method": "Explicit evidence units retained for the exact assessment run.",
        },
        "technical_score": 76,
        "score_integrity": {"score_match": True},
        "unsupported_claims_permitted": 0,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _formats() -> dict:
    markdown = "# NICO MID ASSESSMENT\n\n" + ("Evidence-bound professional report content. " * 30)
    html = "<!doctype html><html><body>" + ("<p>Evidence-bound professional report content.</p>" * 20) + "</body></html>"
    pdf = base64.b64encode(b"%PDF-1.4\n" + (b"0" * 2200)).decode("ascii")
    return {"json": _payload(), "markdown": markdown, "html": html, "pdf": pdf}


def test_complete_evidence_bound_mid_payload_is_ready_for_human_review() -> None:
    manifest = evaluate_report_payload(_payload(), "mid")

    assert manifest["status"] == "ready_for_human_review"
    assert manifest["critical_issue_count"] == 0
    assert manifest["quality_score"] >= 84
    assert manifest["claims_invented"] is False
    assert manifest["missing_evidence_converted_to_pass"] is False
    assert manifest["human_review_required"] is True
    assert manifest["client_delivery_allowed"] is False


def test_section_without_evidence_or_explicit_limitation_is_blocked() -> None:
    payload = _payload()
    payload["sections"][0]["evidence"] = []
    payload["sections"][0]["unavailable"] = []

    manifest = evaluate_report_payload(payload, "mid")

    assert manifest["status"] == "blocked"
    assert any(item["code"] == "unsupported_section_conclusion" for item in manifest["issues"])


def test_score_mismatch_or_premature_delivery_blocks_report() -> None:
    payload = _payload()
    payload["score_integrity"]["score_match"] = False
    payload["client_delivery_allowed"] = True

    manifest = evaluate_report_payload(payload, "mid")

    assert manifest["status"] == "blocked"
    codes = {item["code"] for item in manifest["issues"]}
    assert "score_integrity_mismatch" in codes
    assert "premature_client_delivery" in codes


def test_rendered_format_gate_rejects_missing_or_invalid_pdf_html_and_markdown() -> None:
    rendered = evaluate_rendered_formats({"markdown": "short", "html": "<p>short</p>", "pdf": "not-base64"})

    assert rendered["status"] == "blocked"
    codes = {item["code"] for item in rendered["issues"]}
    assert codes == {"invalid_markdown_export", "invalid_html_export", "invalid_pdf_export"}


def test_nested_full_report_package_is_audited_against_its_json_and_rendered_formats() -> None:
    payload = _payload()
    payload["run_id"] = "fullrun_quality_gate_test"
    formats = _formats()
    formats["json"] = payload
    report = {
        "report_package": {
            "report_id": "report_quality_gate_test",
            "formats": formats,
        },
        "reports": {
            "markdown": formats["markdown"],
            "html": formats["html"],
            "pdf_base64": formats["pdf"],
        },
    }

    manifest = audit_report_record(report, "full")

    assert manifest["status"] == "ready_for_human_review"
    assert manifest["rendered_formats"]["status"] == "verified"
    assert manifest["rendered_formats"]["pdf_signature_valid"] is True


def test_full_report_without_exact_snapshot_remains_review_limited_instead_of_false_failure() -> None:
    payload = _payload()
    payload["run_id"] = "fullrun_review_limited_snapshot"
    payload.pop("snapshot_commit_sha")

    manifest = evaluate_report_payload(payload, "full")

    assert manifest["status"] in {"review_required", "ready_for_human_review"}
    assert manifest["critical_issue_count"] == 0
    snapshot_issue = next(item for item in manifest["issues"] if item["code"] == "missing_snapshot_identity")
    assert snapshot_issue["severity"] == "warning"
    assert manifest["checks"]["full_missing_snapshot_policy"] == "warning_and_review_limited"


def test_placeholder_content_is_never_permitted_in_client_visible_report() -> None:
    payload = deepcopy(_payload())
    payload["sections"][2]["summary"] = "TODO: insert summary after review."

    manifest = evaluate_report_payload(payload, "mid")

    assert manifest["status"] == "blocked"
    assert any(item["code"] == "placeholder_content" for item in manifest["issues"])


def test_todo_text_inside_retained_repository_evidence_does_not_false_block_report() -> None:
    payload = deepcopy(_payload())
    payload["sections"][1]["evidence"].append("Repository source contains literal TODO: rotate this test fixture token.")

    manifest = evaluate_report_payload(payload, "mid")

    assert manifest["status"] == "ready_for_human_review"
    assert not any(item["code"] == "placeholder_content" for item in manifest["issues"])
    assert manifest["checks"]["placeholder_scope"] == "client_presentation_prose_only"
