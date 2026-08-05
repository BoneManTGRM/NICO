from __future__ import annotations

import io

from pypdf import PdfReader

from nico.comprehensive_client_review_companion_v7 import (
    COMPANION_PAGE_COUNT,
    render_paired_substantive_review_pdf,
)
from nico.comprehensive_final_six_client_report_cleanup_v1 import (
    expose_candidate_penalty_basis,
    normalize_client_report_line,
    sanitize_client_report_stage,
)
from nico.comprehensive_final_six_package_projection_v1 import (
    project_final_six_package,
)


RUN_ID = "comprun_93972b7929b34f4194a27484d8be78dc"
COMMIT = "75a5c530763a077e2b2b93881d4185c84168f586"


def _register() -> dict:
    return {
        "summary_by_category": {
            "dependency": {"review_required": 59},
            "secret": {"review_required": 17},
            "static": {"review_required": 586},
        },
        "totals": {
            "raw": 662,
            "material": 0,
            "review_required": 662,
        },
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
                "status": "review_required",
                "summary": f"Decision-useful {title} evidence was retained.",
                "evidence": [f"{title} evidence item 1", f"{title} evidence item 2"],
                "findings": [f"{title} priority observation"],
                "unavailable": [f"{title} requires human confirmation."],
            }
        )
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "run_id": RUN_ID,
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
            "score_contract": {
                "candidate_volume_penalty": 4,
                "candidate_volume_penalty_cap": 6,
                "candidate_volume_review_required_total": 662,
            },
            "canonical_scanner_finding_register": _register(),
        },
        "stage_summaries": stages,
    }


def test_client_labels_rates_and_cover_copy_are_truthful() -> None:
    assert (
        normalize_client_report_line("top_level_directories[0]: Dockerfile")
        == "Top-level entries[0]: Dockerfile"
    )
    assert normalize_client_report_line("job_success_rate: 1.0") == "Job success rate: 100%."
    assert (
        normalize_client_report_line("Observed job success rate: 0.925")
        == "Observed job success rate: 92.5%."
    )
    assert (
        normalize_client_report_line(
            "Weighted technical maturity is 93/100; independently evidence-adjusted readiness is 89/100."
        )
        == "Weighted technical maturity is 93/100; separately calculated evidence-adjusted readiness is 89/100."
    )


def test_deployment_population_discloses_remainder_without_calling_it_failure() -> None:
    source = {
        "stage_id": "ci_cd_operational_readiness",
        "evidence": [
            "Jobs observed: 38.",
            "Observed job success rate: 1.0.",
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success deployment classification: Not available.",
        ],
    }

    cleaned = sanitize_client_report_stage(source)

    assert "Observed job success rate: 100%." in cleaned["evidence"]
    assert "Non-success or unresolved deployment observations: 3." in cleaned["evidence"]
    assert "Outcome classification breakdown: Not available." in cleaned["evidence"]
    assert "Non-success deployments: 3." not in cleaned["evidence"]
    assert source["evidence"][-1] == "Non-success deployment classification: Not available."


def test_existing_assurance_model_is_explained_without_changing_score() -> None:
    canonical = _canonical()
    before = canonical["assessment"]["evidence_adjusted_score"]

    explained = expose_candidate_penalty_basis(canonical)
    contract = explained["assessment"]["score_contract"]

    assert explained["assessment"]["evidence_adjusted_score"] == before
    assert contract["candidate_volume_penalty"] == 4
    assert contract["candidate_volume_active_category_count"] == 3
    assert contract["candidate_volume_category_points"] == 3
    assert contract["candidate_volume_band"] == "100-999"
    assert contract["candidate_volume_increment"] == 1
    assert contract["candidate_volume_penalty_arithmetic_verified"] is True
    assert (
        "3 active review categories x 1 point, plus 1 volume point for 662 "
        "review-required candidates in the 100-999 band; bounded total=4 points"
        in contract["candidate_volume_penalty_basis"]
    )


def test_package_projection_exposes_penalty_basis_before_rendering() -> None:
    package = {"json": _canonical(), "opaque_source_payload": {"retained": True}}

    projected = project_final_six_package(package)

    assert (
        projected["json"]["assessment"]["score_contract"]
        ["candidate_volume_penalty_arithmetic_verified"]
        is True
    )
    assert projected["opaque_source_payload"] == {"retained": True}
    assert "candidate_volume_penalty_basis" not in package["json"]["assessment"]["score_contract"]


def test_eight_review_sections_are_paired_into_four_complete_pages() -> None:
    pdf = render_paired_substantive_review_pdf(_canonical(), spanish=False)
    reader = PdfReader(io.BytesIO(pdf))

    assert len(reader.pages) == COMPANION_PAGE_COUNT == 4
    expected_pairs = (
        ("Functional QA", "Platform Parity"),
        ("Historical Trends and Change Failure", "Requirements Traceability"),
        ("Stakeholder and Business Alignment", "Risk Reduction and Executive Briefing"),
        ("Six-Month Roadmap", "Staffing, Sequencing, and Cost"),
    )
    for page_number, (first, second) in enumerate(expected_pairs, start=1):
        text = " ".join((reader.pages[page_number - 1].extract_text() or "").split())
        assert first in text
        assert second in text
        assert text.count("Decision record") == 2
        assert f"Review page {page_number} of 4" in text
        assert "AUTOMATED DRAFT" in text
        assert "CLIENT DELIVERY BLOCKED" in text
