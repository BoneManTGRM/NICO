from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v4 as v4
from nico import comprehensive_native_providers_v5 as scoring
from nico.comprehensive_candidate_volume_assurance_v2 import (
    MODEL,
    calibrated_candidate_volume_penalty,
    install_candidate_volume_assurance_v2,
)
from nico.comprehensive_client_review_companion_v2 import (
    merge_review_companion_markdown,
    render_comprehensive_review_companion_pdf,
    review_sections,
)


COMMIT = "a" * 40
ROOT = Path(__file__).resolve().parents[1]
MOBILE_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
COMPLETION = ROOT / "nico" / "client_report_completion_v2.py"


def _register() -> dict:
    return {
        "summary_by_category": {
            "dependency": {"review_required": 59},
            "secret": {"review_required": 17},
            "static": {"review_required": 581},
        },
        "totals": {
            "raw": 657,
            "material": 0,
            "review_required": 657,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
            "exact_source": 657,
            "source_path": 0,
            "payload_without_source": 0,
            "count_only": 0,
        },
    }


def _complete_register(commit_sha: str) -> dict:
    return {
        "artifact_schema": "nico.canonical-scanner-findings.v1",
        "status": "complete",
        "exact_commit_sha": commit_sha,
        "findings": [],
        **_register(),
        "count_parity_verified": True,
        "discrepancies": [],
        "canonical_digest_sha256": "f" * 64,
        "raw_payload_retention_complete": True,
    }


def _baseline() -> dict:
    return {
        "status": "complete",
        "assessment": {
            "technical_score": 93,
            "canonical_technical_score": 93,
            "canonical_evidence_adjusted_score": 90,
            "evidence_adjusted_score": 90,
            "maturity_signal": {
                "score": 93,
                "technical_score": 93,
                "evidence_adjusted_score": 90,
            },
            "evidence_coverage": {"percent": 100, "incomplete_analyzers": []},
            "score_contract": {
                "technical_score": 93,
                "evidence_adjusted_score": 90,
                "incomplete_analyzers": [],
            },
            "sections": [
                {"id": "code_audit", "presented_score": 96, "score": 96},
                {"id": "dependency_health", "presented_score": 96, "score": 96},
                {"id": "secrets_review", "presented_score": 96, "score": 96},
                {"id": "static_analysis", "presented_score": 96, "score": 96},
                {"id": "ci_cd", "presented_score": 100, "score": 100},
                {"id": "architecture_debt", "presented_score": 78, "score": 78},
                {"id": "velocity_complexity", "presented_score": 87, "score": 87},
            ],
        },
        "evidence": {"technical_score": 93, "evidence_adjusted_score": 90},
    }


def _scan() -> dict:
    tools = (
        ("pip-audit", "dependency"),
        ("npm-audit", "dependency"),
        ("osv-scanner", "dependency"),
        ("bandit", "static"),
        ("semgrep", "static"),
        ("eslint", "static"),
        ("typescript", "static"),
        ("gitleaks", "secret"),
        ("trufflehog", "secret"),
    )
    by_tool = {
        tool: {
            "raw": 0,
            "material": 0,
            "review_required": 0,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
        }
        for tool, _category in tools
    }
    by_tool["osv-scanner"].update({"raw": 59, "review_required": 59})
    by_tool["gitleaks"].update({"raw": 6, "review_required": 6})
    by_tool["trufflehog"].update({"raw": 11, "review_required": 11})
    by_tool["semgrep"].update({"raw": 581, "review_required": 581})
    results = [
        {
            "tool": tool,
            "scanner_name": tool,
            "category": category,
            "status": "completed_with_findings" if by_tool[tool]["raw"] else "completed",
            "completed": True,
            "verified": True,
            "exact_commit_match": True,
            "raw_artifact_retention_complete": True,
            "findings": [],
        }
        for tool, category in tools
    ]
    return {
        "status": "complete",
        "scanner_results": results,
        "finding_summary": {"by_tool": by_tool},
        "unavailable_data_notes": [],
    }


def _context() -> dict:
    return {
        "run_id": "comprun_assurance_v2",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "evidence_ledger_id": "ledger_assurance_v2",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": {},
    }


def _canonical() -> dict:
    stages = []
    for stage_id, title in (
        ("functional_qa", "Functional QA"),
        ("platform_parity", "Platform Parity"),
        ("historical_trends_and_change_failure", "Historical Trends and Change Failure"),
        ("requirements_traceability", "Requirements Traceability"),
        ("stakeholder_and_business_alignment", "Stakeholder and Business Alignment"),
        ("risk_reduction_and_executive_briefing", "Risk Reduction and Executive Briefing"),
        ("six_month_roadmap", "Six-Month Roadmap"),
        ("staffing_sequencing_and_cost", "Staffing, Sequencing, and Cost"),
    ):
        stages.append(
            {
                "stage_id": stage_id,
                "title": title,
                "status": "complete",
                "summary": f"Decision-useful {title} evidence was retained.",
                "evidence": [f"{title} evidence item 1", f"{title} evidence item 2"],
                "unavailable": [f"{title} requires human confirmation."],
            }
        )
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "run_id": "comprun_review_companion_v2",
        },
        "assessment": {"technical_score": 93, "evidence_adjusted_score": 89},
        "stage_summaries": stages,
    }


def test_657_untriaged_candidates_receive_bounded_workload_penalty() -> None:
    penalty, by_category = calibrated_candidate_volume_penalty(_register())

    assert penalty == 4
    assert by_category == {"dependency": 1, "secret": 1, "static": 2}
    assert penalty < 16


def test_provider_reports_triage_workload_without_technical_deterioration(monkeypatch) -> None:
    install_candidate_volume_assurance_v2()
    monkeypatch.setattr(v4, "canonical_scoring_provider", lambda context: _baseline())
    monkeypatch.setattr(legacy, "_scan", lambda context: _scan())
    monkeypatch.setattr(
        scoring,
        "build_canonical_scanner_finding_register",
        lambda scan, commit_sha: _complete_register(commit_sha),
    )
    monkeypatch.setattr(
        legacy,
        "_repo",
        lambda context: {"workflow_evidence": {"successful_runs": 89, "non_success_runs": 6}},
    )

    assessment = scoring.canonical_scoring_provider(_context())["assessment"]
    contract = assessment["score_contract"]

    assert assessment["technical_score"] == 93
    assert assessment["evidence_adjusted_score"] == 89
    assert contract["candidate_volume_penalty"] == 4
    assert contract["missing_raw_payload_penalty"] == 0
    assert contract["incomplete_analyzer_penalty"] == 0
    assert contract["candidate_volume_penalty_model"] == MODEL
    assert contract["candidate_volume_confirmed_material_total"] == 0
    assert contract["candidate_volume_is_triage_workload_not_defect_severity"] is True
    assert "not evidence that the repository materially worsened" in assessment["executive_summary"]


def test_review_companion_restores_all_decision_sections_in_32_pages() -> None:
    canonical = _canonical()
    sections = review_sections(canonical, spanish=False)
    pdf = render_comprehensive_review_companion_pdf(canonical, spanish=False)
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    normalized = " ".join(extracted.casefold().split())

    assert len(sections) == 8
    assert len(reader.pages) == 32
    for section in sections:
        assert section["title"].casefold() in normalized
    assert "review worksheet" in normalized
    assert "action and acceptance plan" in normalized
    assert "automated draft | human review required" in normalized
    assert "human decision pending | delivery blocked" in normalized
    assert "automated draft | not an approved commitment" in normalized
    assert "\x7f" not in extracted


def test_review_companion_markdown_preserves_automated_draft_boundary() -> None:
    markdown = merge_review_companion_markdown(
        "# NICO Comprehensive\n\nAUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n\n## Evidence Package Summary\nExisting evidence summary.\n",
        _canonical(),
        spanish=False,
    )

    for title in (
        "Functional QA",
        "Platform Parity",
        "Historical Trends and Change Failure",
        "Requirements Traceability",
        "Stakeholder and Business Alignment",
        "Risk Reduction and Executive Briefing",
        "Six-Month Roadmap",
        "Staffing, Sequencing, and Cost",
    ):
        assert f"## {title}" in markdown
    assert "AUTOMATED DRAFT" in markdown
    assert "CLIENT DELIVERY BLOCKED" in markdown
    assert "FINAL REPORT" not in markdown


def test_runtime_and_completion_bind_new_contracts() -> None:
    mobile = MOBILE_BINDING.read_text(encoding="utf-8")
    completion = COMPLETION.read_text(encoding="utf-8")

    assert "install_candidate_volume_assurance_v2" in mobile
    assert "install_comprehensive_review_companion_v4" in mobile
    assert '"decision_useful_review_companion_pages": 32' in mobile
    assert '"candidate_volume_is_triage_workload_not_defect_severity": True' in mobile
    assert "render_comprehensive_review_companion_pdf" in completion
    assert "merge_review_companion_markdown" in completion
    assert '"decision_useful_comprehensive_sections_restored": True' in completion
    assert '"full_evidence_appendix_in_client_pdf": False' in completion
