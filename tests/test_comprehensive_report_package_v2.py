from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.comprehensive_report_package import VERSION, build_comprehensive_report_package


IDENTITY = {
    "run_id": "comprun_report_v2_001",
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "evidence_ledger_id": "ledger_report_v2_001",
    "customer_id": "customer_cody",
    "project_id": "project_nico",
}


STAGES = [
    "authorization_and_scope",
    "immutable_repository_snapshot",
    "repository_and_delivery_evidence",
    "dependency_security_static_analysis",
    "ci_cd_architecture_complexity_velocity",
    "evidence_reconciliation_and_scoring",
    "decision_report_generation",
    "deep_scanner_triage",
    "functional_qa",
    "platform_parity",
    "deployment_and_infrastructure",
    "architecture_and_data_flow",
    "developer_delivery_process",
    "stakeholder_and_business_alignment",
    "requirements_traceability",
    "historical_trends_and_change_failure",
    "six_month_roadmap",
    "staffing_sequencing_and_cost",
    "risk_reduction_and_executive_briefing",
]


def _assessment() -> dict:
    sections = []
    for index, label in enumerate(
        [
            "Code Audit",
            "Dependency / Library Ecosystem",
            "Secrets Exposure Review",
            "Static Analysis",
            "CI/CD Analysis",
            "Architecture & Technical Debt",
            "Velocity / Complexity",
        ]
    ):
        score = 92 - index
        sections.append(
            {
                "id": f"control_{index}",
                "label": label,
                "score": score,
                "presented_score": score,
                "status": "yellow" if index in {2, 3} else "green",
                "presented_status": "yellow" if index in {2, 3} else "green",
                "summary": f"Decision-oriented summary for {label}.",
                "evidence": [
                    f"Exact immutable evidence item {number} for {label}."
                    for number in range(1, 7)
                ],
                "findings": [f"Review-limited finding for {label}."] if index in {2, 3} else [],
                "unavailable": [f"One bounded evidence limitation for {label}."] if index == 3 else [],
            }
        )
    return {
        "status": "complete",
        "service_id": "comprehensive",
        "executive_summary": "Canonical technical evidence produced a Senior maturity signal.",
        "maturity_signal": {
            "level": "Senior",
            "score": 89,
            "presented_score": 89,
            "evidence_readiness_score": 82,
        },
        "sections": sections,
        "unavailable_data_notes": [
            "Stakeholder interviews were not supplied and remain a human-context boundary."
        ],
        "human_review_required": True,
        "client_ready": False,
    }


def _stage_results() -> dict[str, dict]:
    output: dict[str, dict] = {}
    for index, stage_id in enumerate(STAGES):
        output[stage_id] = {
            "status": "complete",
            "summary": f"Substantive summary for {stage_id.replace('_', ' ')}.",
            "evidence": {
                "stage_sequence": index + 1,
                "snapshot_commit_sha": IDENTITY["commit_sha"],
                "verified_signal_count": index + 3,
                "source": "exact immutable assessment fixture",
            },
            "findings": [f"Retained finding for {stage_id}."] if index % 5 == 0 else [],
            "unavailable_data_notes": [f"Human context limitation for {stage_id}."] if index % 6 == 0 else [],
        }
    output["evidence_reconciliation_and_scoring"]["assessment"] = _assessment()
    output["six_month_roadmap"]["roadmap"] = [
        {
            "window": "0-30 days",
            "objective": "Close material evidence and security gaps.",
            "priority_controls": ["Secrets Exposure Review", "Static Analysis"],
        },
        {
            "window": "31-90 days",
            "objective": "Strengthen architecture and regression protection.",
            "priority_controls": ["Architecture & Technical Debt"],
        },
        {
            "window": "91-180 days",
            "objective": "Complete stakeholder-approved delivery improvements.",
            "priority_controls": ["Velocity / Complexity"],
        },
    ]
    output["staffing_sequencing_and_cost"]["staffing_plan"] = [
        {"role": "Product Engineering Architect", "sequence": 1, "focus": "Architecture and evidence governance."},
        {"role": "Senior Product Engineer", "sequence": 2, "focus": "Implementation and remediation."},
        {"role": "Product Quality Engineer", "sequence": 3, "focus": "QA and release acceptance."},
    ]
    output["risk_reduction_and_executive_briefing"]["executive_briefing"] = {
        "maturity_level": "Senior",
        "technical_score": 89,
        "decision": "Proceed to human review; client delivery remains blocked.",
    }
    return output


def _package() -> dict:
    return build_comprehensive_report_package(
        identity=IDENTITY,
        stage_results=_stage_results(),
    )


def test_native_package_is_comprehensive_branded_and_cross_format_complete() -> None:
    package = _package()
    report = package["report_package"]

    assert package["status"] == "complete"
    assert package["artifact_schema"] == VERSION
    assert package["service_id"] == "comprehensive"
    assert report["service_id"] == "comprehensive"
    assert report["markdown"].startswith("# NICO Comprehensive Technical Assessment")
    assert "NICO MID TECHNICAL" not in report["markdown"].upper()
    assert "nico-comprehensive-assessment-" in report["pdf_filename"]
    assert report["pdf_filename"].endswith("-DRAFT.pdf")
    assert report["human_review_required"] is True
    assert report["client_delivery_allowed"] is False


def test_markdown_retains_deep_modules_roadmap_staffing_and_identity() -> None:
    report = _package()["report_package"]
    markdown = report["markdown"]

    for value in (
        IDENTITY["run_id"],
        IDENTITY["repository"],
        IDENTITY["commit_sha"],
        IDENTITY["evidence_ledger_id"],
        "Functional QA",
        "Platform Parity",
        "Stakeholder and Business Alignment",
        "Six-Month Roadmap",
        "Staffing, Sequencing, and Cost",
        "roadmap[0].window: 0-30 days",
        "staffing_plan[0].role: Product Engineering Architect",
        "CLIENT DELIVERY NOT AUTHORIZED",
    ):
        assert value in markdown
    assert "NOT SCORED/100" not in markdown


def test_html_is_semantic_and_not_an_escaped_markdown_dump() -> None:
    report = _package()["report_package"]
    rendered = report["html"]

    assert "<article>" in rendered
    assert "<h2>Executive Decision Brief</h2>" in rendered
    assert "<ul>" in rendered
    assert "<pre>" not in rendered
    assert "DRAFT · HUMAN REVIEW REQUIRED" in rendered


def test_pdf_is_valid_substantive_and_deeper_than_the_old_mid_artifact() -> None:
    report = _package()["report_package"]
    pdf_bytes = base64.b64decode(report["pdf_base64"], validate=True)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert pdf_bytes.startswith(b"%PDF")
    assert report["pdf_page_count"] == len(reader.pages)
    assert len(reader.pages) >= 30
    assert "Comprehensive Technical Assessment" in text
    assert "Evidence Appendix" in text
    assert "Functional QA" in text
    assert "Six-Month Roadmap" in text
    assert "Human Review and Acceptance Gate" in text
    assert "NICO MID TECHNICAL DILIGENCE ASSESSMENT" not in text.upper()


def test_quality_contract_proves_decision_body_appendix_and_module_depth() -> None:
    package = _package()
    quality = package["report_quality_contract"]

    assert quality["semantic_html"] is True
    assert quality["decision_oriented_body"] is True
    assert quality["full_evidence_appendix"] is True
    assert quality["comprehensive_module_count"] == len(STAGES)
    assert quality["technical_control_count"] == 7
    assert quality["not_scored_format_valid"] is True
    assert quality["mid_brand_leakage_absent"] is True
