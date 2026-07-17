from __future__ import annotations

import io

from pypdf import PdfReader

from nico import mid_report_professional_v7 as v8
from nico.mid_report_professional_v7_runtime_fix import _fixed_premium_enhance


def _payload() -> dict:
    return {
        "repository": "example/nico",
        "snapshot_commit_sha": "a" * 40,
        "canonical_weighted_technical_score": 84,
        "evidence_coverage": {"percent": 88},
        "decision_summary": {"review_decision_reason": "Open evidence requires human disposition."},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "summary": "Code evidence retained.",
                "evidence": ["Exact code artifact."],
                "findings": ["One dynamic execution issue requires review."],
                "unavailable": [],
            },
            {
                "id": "dependency_health",
                "label": "Dependency Health",
                "score": 90,
                "summary": "Dependency evidence retained.",
                "evidence": ["Manifest and lockfile retained."],
                "findings": ["One advisory requires human triage."],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Review",
                "score": 92,
                "summary": "Secrets evidence is incomplete.",
                "evidence": ["Trufflehog artifact retained."],
                "findings": ["One candidate requires review."],
                "unavailable": ["gitleaks timed out."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 88,
                "summary": "Bandit failed and Semgrep requires human triage.",
                "evidence": ["Semgrep artifact retained."],
                "findings": ["Semgrep issue requires review."],
                "unavailable": ["Bandit failed."],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD",
                "score": 95,
                "summary": "CI history retained.",
                "evidence": ["Workflow history retained."],
                "findings": ["Historical non-success runs require classification."],
                "unavailable": [],
            },
            {
                "id": "architecture_debt",
                "label": "Architecture and Technical Debt",
                "score": 91,
                "summary": "Architecture evidence retained.",
                "evidence": ["Module inventory retained."],
                "findings": ["Compatibility surface requires review."],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity and Complexity",
                "score": 76,
                "summary": "Ownership evidence retained.",
                "evidence": ["Churn and ownership metrics retained."],
                "findings": ["Ownership concentration requires review."],
                "unavailable": [],
            },
        ],
    }


def test_active_mid_renderer_outputs_35_substantive_pages() -> None:
    payload = _fixed_premium_enhance(_payload())
    pdf = v8._premium_pdf(payload)
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 35
    page_text = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    assert all(len(text) >= 300 for text in page_text)
    full_text = "\n".join(page_text)
    for required in (
        "Executive Decision Brief",
        "Transparent Weighted Technical Scorecard",
        "Architecture and System Design",
        "Dependency and Supply-Chain Topology",
        "Complexity and Churn Hotspots",
        "Ownership and Delivery Concentration",
        "CI/CD Reliability and Release Controls",
        "Test Maturity and Quality Gates",
        "30 / 60 / 90 Day Roadmap",
        "Final Reviewer Decision Record",
    ):
        assert required in full_text


def test_active_mid_renderer_carries_transparent_score_metadata() -> None:
    payload = _fixed_premium_enhance(_payload())
    contract = payload["mid_premium_contract"]
    scores = payload["mid_score_transparency"]["records"]
    assert contract["page_contract"] == {"minimum": 35, "target": 42, "maximum": 50}
    assert contract["minimum_visuals"] == 10
    assert contract["full_finding_dossiers_required"] is True
    assert scores
    assert all(record["status"] != "green" for record in scores if record["deductions"])


def test_runtime_fix_binds_v8_renderer_to_production_module() -> None:
    from nico import mid_assessment_report as report_module

    assert report_module._pdf is v8._premium_pdf
    assert "v8" in v8.VERSION
