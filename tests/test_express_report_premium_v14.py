from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico.express_report_premium_v14 import (
    VERSION,
    build_express_premium_pdf,
    reconcile_express_scores,
)


def _section(section_id: str, label: str, score: int, *, findings=None, unavailable=None, evidence=None):
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": "green" if score >= 75 else "yellow",
        "summary": f"Evidence-bound summary for {label}.",
        "evidence": evidence or [f"Exact snapshot evidence for {label}.", "Structured artifact parsed and retained."],
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def _fixture() -> dict:
    return {
        "status": "complete",
        "repository": "example/nico",
        "client_name": "Example Client",
        "project_name": "NICO",
        "generated_at": "2026-07-17T17:00:00Z",
        "human_review_required": True,
        "executive_summary": "The assessment identified verified strengths and review-limited controls that require bounded repair and human disposition before client delivery.",
        "maturity_signal": {"level": "Senior", "score": 86},
        "sections": [
            _section("code_audit", "Code Audit", 86, findings=["One dynamic execution pattern requires review."]),
            _section("dependency_health", "Dependency / Library Ecosystem", 90, findings=["OSV scanner returned one finding requiring human triage."]),
            _section("secrets_review", "Secrets Exposure Review", 92, findings=["Trufflehog returned one finding requiring human triage."], unavailable=["gitleaks ended with status timeout."]),
            _section("static_analysis", "Static Analysis", 78, findings=["Semgrep findings require review."], unavailable=["Bandit failed during exact-snapshot execution."]),
            _section("ci_cd", "CI/CD Analysis", 95, findings=["Historical reliability includes seven non-success runs."]),
            _section("architecture_debt", "Architecture & Technical Debt", 94, findings=["Runtime compatibility surface creates import-order fragility."]),
            _section("velocity_complexity", "Velocity / Complexity", 73, findings=["Ownership concentration is elevated."]),
        ],
        "repair_intelligence": {
            "candidates": [
                {
                    "rank": "P1",
                    "title": "Runtime compatibility surface creates import-order fragility",
                    "severity": "high",
                    "effort": "high",
                    "business_impact": "Regression risk and engineering cost increase.",
                    "recommended_action": "Migrate one installer family behind an explicit bootstrap registry.",
                    "verification": "Run import-order tests, full suite, production build, and smoke test.",
                    "owner": "Platform engineering",
                },
                {
                    "rank": "P2",
                    "title": "Resolve exact dependency advisory",
                    "severity": "medium",
                    "effort": "medium",
                    "business_impact": "An unresolved advisory can block clean release claims.",
                    "recommended_action": "Identify the exact affected package and fixed version before changing the manifest.",
                    "replacement_code": "package-name>=<minimum-fixed-version>",
                    "verification": "Rerun dependency scanners and the full test suite.",
                },
            ]
        },
        "reports": {},
    }


def _pdf_text(result: dict) -> tuple[PdfReader, str]:
    encoded, error = build_express_premium_pdf(result)
    assert error is None
    assert encoded
    reader = PdfReader(io.BytesIO(base64.b64decode(encoded)))
    text = "\n".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
    return reader, text


def test_v14_uses_evidence_specific_deductions_without_blanket_cap() -> None:
    result = _fixture()
    records, overall = reconcile_express_scores(result)
    secrets = next(item for item in records if item.section_id == "secrets_review")
    dependency = next(item for item in records if item.section_id == "dependency_health")
    ci_cd = next(item for item in records if item.section_id == "ci_cd")

    assert secrets.source_score == 92
    assert secrets.presented_score == 79
    assert dependency.presented_score == 85
    assert ci_cd.presented_score == 92
    assert len({secrets.presented_score, dependency.presented_score, ci_cd.presented_score}) == 3
    assert secrets.status == "yellow"
    assert dependency.status == "yellow"
    assert ci_cd.status == "yellow"
    assert all(item.presented_score != 74 for item in (secrets, dependency, ci_cd))
    assert overall < result["maturity_signal"]["source_score"]
    assert result["express_score_transparency"]["version"] == VERSION
    assert result["express_score_transparency"]["blanket_score_cap_applied"] is False


def test_v14_pdf_meets_express_depth_and_decision_contract() -> None:
    result = _fixture()
    reader, text = _pdf_text(result)

    assert 15 <= len(reader.pages) <= 20
    for required in (
        "Executive Decision Brief",
        "Technical Score and Evidence Assurance",
        "Score Contribution and Assurance Constraints",
        "Evidence Funnel",
        "Risk and Repair Matrix",
        "Prioritized Repair Intelligence",
        "Immediate and 30-Day Roadmap",
        "Integrity, Independence, and Reviewer Record",
        "Self-assessment limitation",
    ):
        assert required in text


def test_v14_withholds_placeholder_code_and_preserves_truth_boundary() -> None:
    result = _fixture()
    _, text = _pdf_text(result)

    assert "<minimum-fixed-version>" not in text
    assert "Unsupported claims permitted: 0" in text
    assert "human review required" in text.lower()
    assert "FINAL REPORT" in text
    assert "Pending approval" in text
    assert "Final report · pending human approval" in text
    assert "Not approved for client delivery" not in text
    assert result["express_delivery_truth"]["report_finality"] == "final"
    assert result["express_delivery_truth"]["approval_status"] == "pending_human_approval"
    assert result["express_delivery_truth"]["client_delivery_allowed"] is False
    assert result["express_premium_report"]["placeholder_code_withheld"] is True


def test_v14_is_bound_after_final_report_layers() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    init_source = (root / "nico" / "__init__.py").read_text(encoding="utf-8")
    live_binding_source = (root / "nico" / "express_live_renderer_binding_v22.py").read_text(encoding="utf-8")
    assert "install_express_report_premium_v14" in init_source
    assert init_source.rindex("install_express_report_premium_v14()") > init_source.index("install_report_intelligence_final_pdf_binding()")
    assert init_source.rindex("install_express_report_premium_v14()") > init_source.index("install_report_quality_gate_compat()")
    assert "install_express_evidence_specific_scoring_v33" in live_binding_source
    assert live_binding_source.index("install_express_evidence_specific_scoring_v33()") > live_binding_source.index("install_express_section_status_truth_v26()")
