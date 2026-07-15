from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import assessment_quality
from nico import report_intelligence_accuracy_patch as accuracy
from nico.report_intelligence_professional_pdf import (
    PDF_STYLE_VERSION,
    build_professional_intelligence_pdf,
    install_professional_report_intelligence_pdf,
)


def _base_pdf(_result: dict) -> tuple[str, None]:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.drawString(72, 720, "Base NICO assessment")
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def _result() -> dict:
    return {
        "status": "complete",
        "repository": "owner/repository",
        "maturity_signal": {"level": "Senior", "score": 92},
        "repository_quality_signals": {
            "status": "complete",
            "finding_count": 2,
            "groups": {
                "branch_hygiene": {
                    "status": "available",
                    "branch_count": 569,
                    "truncated": False,
                },
                "frontend_routes": {
                    "status": "available",
                    "route_count": 41,
                    "route_aliases": ["apps/web/app/dashboard/page.tsx"],
                    "explicit_placeholders": [],
                    "unread_routes": [],
                },
                "runtime_patch_surface": {
                    "status": "available",
                    "patch_compat_fallback_count": 38,
                    "package_installer_call_count": 42,
                },
                "documentation_alignment": {
                    "status": "available",
                    "documents_checked": 3,
                    "missing_link_count": 0,
                    "release_claim_verification_count": 1,
                },
                "security_configuration": {
                    "status": "available",
                    "posture": {
                        "code_scanning": {"status": "available", "open_alert_count": 0},
                        "secret_scanning": {"status": "available", "open_alert_count": 0},
                        "dependabot": {"status": "disabled"},
                    },
                },
            },
            "findings": [
                {
                    "code": "branch_inventory_large",
                    "title": "Very large branch inventory increases repository maintenance cost",
                    "severity": "high",
                    "business_impact": "Review and cleanup cost increase.",
                    "technical_impact": "Obsolete references make release analysis harder.",
                    "recommendation": "Use a human-approved branch retention policy.",
                    "evidence": ["GitHub branch inventory returned 569 branches."],
                },
                {
                    "code": "runtime_patch_surface",
                    "title": "Large runtime patch and compatibility surface creates import-order fragility",
                    "severity": "high",
                    "business_impact": "Import regressions increase debugging cost.",
                    "technical_impact": "Installer order is difficult to reason about.",
                    "recommendation": "Consolidate installers in bounded migration stages.",
                    "evidence": ["Patch modules=38; installer calls=42."],
                },
            ],
            "unavailable": [],
        },
        "repair_intelligence": {
            "status": "complete",
            "mode": "report_only",
            "priority_model": "calibrated_weighted_v2",
            "candidate_count": 2,
            "code_suggestion_count": 1,
            "advisories": [
                {
                    "title": "Source-file footprint is large",
                    "reason": "Scope signal retained for planning context; it is not ranked as a defect by itself.",
                }
            ],
            "portfolio": {
                "severity_counts": {"critical": 0, "high": 2, "medium": 0, "low": 0, "info": 0},
                "effort_counts": {"low": 0, "medium": 1, "high": 1},
                "tgrm_counts": {"level_1": 0, "level_2": 2, "level_3": 0},
                "advisory_count": 1,
                "candidate_count": 2,
                "code_suggestion_count": 1,
            },
            "candidates": [
                {
                    "rank": 1,
                    "title": "Large runtime patch and compatibility surface creates import-order fragility",
                    "severity": "high",
                    "priority_score": 64.2,
                    "effort": "high",
                    "confidence": "high",
                    "exploitability": "low",
                    "impact": "Import regressions increase debugging time.",
                    "technical_impact": "Installers can replace references in different orders.",
                    "recommended_action": "Consolidate installers behind one explicit registry.",
                    "priority_explanation": "Weighted evidence: severity=high, exploitability=low.",
                    "tgrm": {
                        "level": 2,
                        "label": "TGRM-2 bounded structural repair",
                        "scope": "Migrate one capability family per release and preserve rollback evidence.",
                    },
                    "affected_files": ["nico/__init__.py", "nico/example_patch.py"],
                    "evidence": ["38 patch modules and 42 installer calls.", "density=None"],
                    "code_suggestion": {
                        "status": "available",
                        "candidate_kind": "reviewable_template",
                        "suggested_code": "from dataclasses import dataclass\n\n@dataclass(frozen=True)\nclass BootstrapStep:\n    name: str\n\ndef bootstrap_runtime():\n    return [BootstrapStep(name=\"metadata_auth\")]",
                        "accuracy_statement": "This code is a review candidate, not a guaranteed fix.",
                        "applicability_conditions": ["Migrate one installer family at a time."],
                        "verification_steps": ["Run import-order and full assessment tests."],
                    },
                    "rollback_plan": "Revert the approved migration slice if verification fails.",
                },
                {
                    "rank": 2,
                    "title": "Very large branch inventory increases repository maintenance cost",
                    "severity": "high",
                    "priority_score": 60.4,
                    "effort": "medium",
                    "confidence": "high",
                    "exploitability": "low",
                    "impact": "Branch noise increases review cost.",
                    "technical_impact": "Stale-reference analysis becomes slower.",
                    "recommended_action": "Inventory branches before human-approved cleanup.",
                    "priority_explanation": "Weighted evidence: severity=high, exploitability=low.",
                    "tgrm": {"level": 2, "scope": "Use a reversible governance process."},
                    "affected_files": [],
                    "evidence": ["GitHub branch inventory returned 569 branches."],
                    "code_suggestion": {
                        "status": "unavailable",
                        "reason": "Branch governance requires repository-owner review rather than replacement code.",
                    },
                    "rollback_plan": "Restore only branches explicitly archived by the approved process.",
                },
            ],
        },
    }


def test_professional_intelligence_pdf_is_decision_ready_and_not_raw_markdown() -> None:
    result = _result()

    encoded, error = build_professional_intelligence_pdf(_base_pdf, result)

    assert error is None
    assert encoded
    reader = PdfReader(io.BytesIO(base64.b64decode(encoded)))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Base NICO assessment" in text
    assert "Decision-Ready Repository Quality and Repair Intelligence" in text
    assert "Repository Quality and Governance Signals" in text
    assert "Prioritized Repair Intelligence" in text
    assert "Critical / High" in text
    assert "Planning Advisories - Not Ranked as Defects" in text
    assert "Suggested replacement code - not applied and not yet verified" in text
    assert "class BootstrapStep" in text
    assert 'BootstrapStep(name="metadata_auth")' in text
    assert "&quot;" not in text
    assert "-&gt;" not in text
    assert "density=None" not in text
    assert "density=unavailable" in text
    assert "## Prioritized Repair Intelligence" not in text
    assert "**Report-only safety boundary:**" not in text
    assert "```" not in text
    assert result["report_intelligence_pdf"] == {
        "status": "complete",
        "style": PDF_STYLE_VERSION,
        "structured_appendix": True,
        "decision_ready_portfolio": True,
        "raw_markdown_rendered": False,
        "candidate_count": 2,
        "code_suggestion_count": 1,
        "advisory_count": 1,
        "priority_model": "calibrated_weighted_v2",
        "portfolio": result["repair_intelligence"]["portfolio"],
        "report_only": True,
        "human_review_required": True,
        "code_changes_applied": False,
    }


def test_professional_pdf_patch_is_installed_and_idempotent() -> None:
    first = install_professional_report_intelligence_pdf()
    second = install_professional_report_intelligence_pdf()

    assert first["structured_intelligence_appendix"] is True
    assert first["decision_ready_portfolio"] is True
    assert second["status"] == "already_installed"
    assert assessment_quality.PDF_STYLE_VERSION == PDF_STYLE_VERSION
    assert getattr(
        assessment_quality._build_polished_pdf_base64,
        "_nico_professional_report_intelligence_pdf_v2",
        False,
    ) is True


def test_final_rebuild_has_professional_pdf_binding() -> None:
    assert getattr(
        accuracy.rebuild_enriched_reports,
        "_nico_report_intelligence_final_pdf_binding_v1",
        False,
    ) is True
