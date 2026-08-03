from __future__ import annotations

import base64

from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts


SHA = "7" * 40


def _package(language: str = "en") -> dict:
    return {
        "json": {
            "identity": {
                "repository": "BoneManTGRM/NICO",
                "commit_sha": SHA,
                "run_id": "comprun_premium",
                "evidence_ledger_id": "ledger-premium",
                "customer_id": "customer-premium",
                "project_id": "project-premium",
                "report_language": language,
            },
            "report_language": language,
            "assessment": {
                "report_language": language,
                "technical_score": 84,
                "canonical_evidence_adjusted_score": 82,
                "maturity_signal": {
                    "level": "Strong",
                    "score": 84,
                    "presented_score": 84,
                },
                "sections": [
                    {
                        "id": "architecture",
                        "label": "Architecture & Technical Debt",
                        "status": "verified",
                        "presented_status": "verified",
                        "score": 82,
                        "presented_score": 82,
                        "summary": "Architecture evidence is decision ready.",
                        "evidence": [
                            "Module boundaries and complexity were measured."
                        ],
                    }
                ],
                "unavailable_data_notes": [],
            },
            "canonical_findings": [
                {
                    "finding_id": "RISK-P1-001",
                    "priority": "P1",
                    "category": "architecture",
                    "title": "Reduce complexity in page.tsx",
                    "location": "apps/web/app/page.tsx:100",
                    "business_impact": "Regression risk is concentrated.",
                    "recommendation": "Split the module into bounded components.",
                    "status": "open",
                }
            ],
            "scanner_execution_records": [
                {
                    "scanner_name": "bandit",
                    "state": "completed_with_findings",
                    "status": "completed_with_findings",
                    "completed": True,
                    "verified": True,
                    "exact_commit_match": True,
                    "artifact_hash": "b" * 64,
                    "findings": [{"test_id": "B101"}],
                }
            ],
            "roadmap": [
                {
                    "window": "0-30 days",
                    "objective": "Remove the highest-risk delivery constraints.",
                    "work_packages": [
                        {
                            "work_package_id": "WP-001",
                            "title": "Decompose page.tsx",
                            "owner_role": "Product Engineer",
                            "effort": "M",
                        }
                    ],
                }
            ],
            "stage_summaries": [],
        }
    }


def test_english_premium_renderer_restores_multi_chapter_report():
    result = rebuild_client_artifacts(_package("en"))
    contract = result["premium_report_renderer"]
    assert contract["premium_multi_chapter_layout"] is True
    assert contract["canonical_findings_only"] is True
    assert contract["canonical_scanner_truth_only"] is True
    assert contract["full_evidence_retained_in_structured_exports"] is True
    assert contract["full_evidence_appendix_in_client_pdf"] is False
    assert result["pdf_page_count"] <= contract["client_pdf_page_boundary"]
    assert base64.b64decode(result["pdf_base64"]).startswith(b"%PDF")
    assert "Executive Decision Brief" in result["markdown"]
    assert "Technical Scorecard" in result["markdown"]
    assert "Evidence Foundation" in result["markdown"]
    assert "Roadmap, Resourcing, and Decision" in result["markdown"]
    assert "Evidence Appendix" not in result["markdown"]
    assert "Evidence Package Summary" in result["markdown"]
    assert "Compact Finding and Remediation Register" in result["markdown"]
    assert "Complete exact-source index" in result["markdown"]
    assert "RISK-P1-001" in result["markdown"]
    assert result["json"]["scanner_execution_records"][0]["scanner_name"] == "bandit"
    assert "CLIENT DELIVERY NOT AUTHORIZED" in result["markdown"]
    assert result["report_finality"] == "automated_draft"


def test_spanish_premium_renderer_keeps_localized_layout_and_truth():
    result = rebuild_client_artifacts(_package("es-MX"))
    contract = result["premium_report_renderer"]
    assert contract["bilingual_premium_output"] is True
    assert contract["full_evidence_retained_in_structured_exports"] is True
    assert contract["full_evidence_appendix_in_client_pdf"] is False
    assert result["pdf_page_count"] <= contract["client_pdf_page_boundary"]
    assert base64.b64decode(result["pdf_base64"]).startswith(b"%PDF")
    assert "Evaluación Técnica Integral NICO" in result["markdown"]
    assert "Hoja de ruta de seis meses" in result["markdown"]
    assert "Apéndice de evidencia" not in result["markdown"]
    assert "Resumen del paquete de evidencia" in result["markdown"]
    assert "Registro compacto de hallazgos y remediación" in result["markdown"]
    assert "Índice completo de ubicaciones" in result["markdown"]
    assert result["json"]["scanner_execution_records"][0]["scanner_name"] == "bandit"
    assert "CLIENT DELIVERY NOT AUTHORIZED" in result["markdown"]
    assert result["report_finality"] == "automated_draft"
