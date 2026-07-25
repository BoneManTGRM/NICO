from __future__ import annotations

import base64
import io
import json
import zipfile

from reportlab.pdfgen import canvas

from nico.decision_grade_premium_delivery_v1 import (
    build_premium_delivery_package,
    wrap_report_builder_with_premium_delivery_package,
)


def _pdf() -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    for page in range(1, 5):
        document.drawString(72, 720, f"NICO page {page}")
        document.showPage()
    document.save()
    return buffer.getvalue()


def _package(*, approved: bool = False) -> dict:
    pdf = _pdf()
    acceptance = {
        "accepted_edition": approved,
        "client_delivery_allowed": approved,
        "review": {
            "reviewer": "reviewer@example.com" if approved else "",
            "decision": "approved" if approved else "pending",
        },
    }
    return {
        "report_id": "report-001",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_page_count": 4,
        "core_report_page_count": 2,
        "findings_csv": "finding_id,priority,title\nRISK-P1-001,P1,Example risk\n",
        "jira_csv": "Summary,Priority\nFix example,P1\n",
        "accepted_edition": acceptance,
        "supply_chain_evidence": {
            "status": "complete",
            "sbom": {"bomFormat": "CycloneDX", "specVersion": "1.5"},
        },
        "json": {
            "identity": {
                "repository": "owner/repo",
                "run_id": "run-001",
                "commit_sha": "a" * 40,
                "report_language": "en",
                "assessment_depth": "strategic",
            },
            "assessment": {
                "maturity_signal": {"score": 82, "score_band_label": "STRONG"},
                "sections": [
                    {
                        "id": "architecture_debt",
                        "label": "Architecture",
                        "score_value": 82,
                        "score_band_label": "STRONG",
                        "assurance_label": "VERIFIED",
                        "risk_disposition": "Advisory findings",
                    }
                ],
            },
            "findings_register": [
                {
                    "finding_id": "RISK-P1-001",
                    "priority": "P1",
                    "title": "Example risk",
                }
            ],
            "executive_risk_register": [
                {
                    "finding_id": "RISK-P1-001",
                    "priority": "P1",
                    "title": "Example risk",
                    "impact": "Release delay",
                    "recommendation": "Fix and verify",
                }
            ],
            "roadmap": [
                {
                    "window": "0-30 days",
                    "objective": "Contain risk",
                    "work_packages": [
                        {
                            "title": "Fix example",
                            "owner_role": "Platform engineer",
                            "effort_range": "2-4 days",
                            "acceptance_criteria": ["Exact-SHA proof passes"],
                        }
                    ],
                },
                {
                    "window": "91-180 days",
                    "objective": "Institutionalize prevention",
                    "work_packages": [
                        {
                            "title": "Add policy gate",
                            "owner_role": "Engineering lead",
                            "effort_range": "1-2 weeks",
                        }
                    ],
                },
            ],
            "staffing_plan": [
                {
                    "role": "Platform engineer",
                    "sequence": 1,
                    "capacity_assumption": "0.5 FTE",
                    "rationale": "Own release controls",
                }
            ],
        },
    }


def _archive(delivery: dict) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(base64.b64decode(delivery["zip_base64"])))


def test_internal_review_package_contains_layered_premium_artifacts() -> None:
    delivery = build_premium_delivery_package(_package())

    assert delivery["status"] == "internal_review_ready"
    assert delivery["client_delivery_allowed"] is False
    assert delivery["missing_required_artifacts"] == []
    with _archive(delivery) as archive:
        names = set(archive.namelist())
        assert "01_executive_decision_report.pdf" in names
        assert "02_detailed_technical_assessment.pdf" in names
        assert "03_evidence_appendix.pdf" in names
        assert "04_findings_register.csv" in names
        assert "11_evidence_manifest.json" in names
        assert "13_sbom.json" in names
        assert "15_approval_record.json" in names
        manifest = json.loads(archive.read("11_evidence_manifest.json"))
        assert manifest["client_delivery_allowed"] is False
        assert manifest["language_parity"]["status"] == "pending_translation_and_parity_verification"


def test_approved_exact_edition_unlocks_complete_package_only() -> None:
    delivery = build_premium_delivery_package(_package(approved=True))

    assert delivery["status"] == "approved_for_delivery"
    assert delivery["client_delivery_allowed"] is True
    assert "APPROVED.zip" in delivery["filename"]


def test_delivery_archive_is_deterministic() -> None:
    first = build_premium_delivery_package(_package())
    second = build_premium_delivery_package(_package())

    assert first["zip_sha256"] == second["zip_sha256"]
    assert first["zip_base64"] == second["zip_base64"]


def test_wrapper_attaches_package_without_automatic_approval() -> None:
    def delegate(*args, **kwargs):
        return {
            "status": "complete",
            "report_package": _package(),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    wrapped = wrap_report_builder_with_premium_delivery_package(delegate)
    result = wrapped()

    assert result["premium_delivery_package"]["status"] == "internal_review_ready"
    assert result["report_package"]["delivery_package_sha256"]
    assert result["client_delivery_allowed"] is False
