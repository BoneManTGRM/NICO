from __future__ import annotations

import io

from pypdf import PdfReader

from nico.express_report_quality_v47 import (
    install_express_report_quality_v47,
    normalize_client_report_quality_v47,
)


def _payload() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-24T01:10:50Z",
        "commit_sha": "a" * 40,
        "maturity_signal": {"score": 87, "level": "Senior"},
        "evidence_adjusted_score": 81,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "scanner_assurance_ledger": {
            "analyzers": [
                {"tool": "bandit", "lifecycle_result": "failed"},
                {"tool": "eslint", "lifecycle_result": "not_configured"},
                {"tool": "gitleaks", "lifecycle_result": "timed_out"},
            ]
        },
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "presented_score": 86,
                "score_value": 86,
                "score_band_label": "STRONG",
                "score_tone": "green",
                "assurance_label": "VERIFIED",
                "assurance_tone": "green",
                "status": "green",
                "confidence": "review-limited",
                "summary": "Repository evidence,score reconciliation,and source review completed.",
                "evidence": ["Exact source evidence retained."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 83,
                "presented_score": 83,
                "score_value": 83,
                "score_band_label": "STRONG",
                "score_tone": "green",
                "assurance_label": "VERIFIED",
                "assurance_tone": "green",
                "status": "green",
                "confidence": "review-limited",
                "summary": "Dependency evidence is complete.",
                "evidence": ["Pinned manifests and lockfile retained."],
                "findings": ["One repository-wide OSV candidate requires disposition."],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 64,
                "presented_score": 64,
                "score_value": 64,
                "score_band_label": "WEAK",
                "score_tone": "red",
                "assurance_label": "REVIEW LIMITED",
                "assurance_tone": "yellow",
                "status": "yellow",
                "confidence": "high",
                "summary": "Secret candidates remain review-limited.",
                "evidence": ["Gitleaks and TruffleHog were invoked."],
                "findings": [
                    "Scanner-worker secret tools reported 31 raw candidate(s).",
                    "Gitleaks timed out with 0 retained review-only candidate(s); no verified finding is permitted.",
                ],
                "unavailable": ["Current-run Gitleaks execution timed out."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 84,
                "presented_score": 84,
                "score_value": 84,
                "score_band_label": "STRONG",
                "score_tone": "green",
                "assurance_label": "REVIEW LIMITED",
                "assurance_tone": "yellow",
                "status": "yellow",
                "confidence": "high",
                "summary": "Static analyzers are evaluated independently.",
                "evidence": [
                    "Bandit status=failed.",
                    "No ESLint configuration exists and the package lint script does not execute ESLint.",
                    *[f"Static evidence statement {index}." for index in range(12)],
                ],
                "findings": [f"Review candidate {index}." for index in range(8)],
                "unavailable": ["Accepted current-run execution evidence remains unresolved for: eslint."],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "score": 89,
                "presented_score": 89,
                "score_value": 89,
                "score_band_label": "STRONG",
                "score_tone": "green",
                "assurance_label": "VERIFIED",
                "assurance_tone": "green",
                "status": "green",
                "confidence": "review-limited",
                "summary": "Current release checks are verified.",
                "evidence": ["Required workflows passed."],
                "findings": ["Historical reliability remains visible."],
                "unavailable": [],
            },
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 86,
                "presented_score": 86,
                "score_value": 86,
                "score_band_label": "STRONG",
                "score_tone": "green",
                "assurance_label": "VERIFIED",
                "assurance_tone": "green",
                "status": "green",
                "confidence": "review-limited",
                "summary": "Architecture evidence is retained.",
                "evidence": ["Complexity evidence retained."],
                "findings": ["One high-complexity hotspot remains open."],
                "unavailable": [],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "score": 74,
                "presented_score": 74,
                "score_value": 74,
                "score_band_label": "MODERATE",
                "score_tone": "yellow",
                "assurance_label": "VERIFIED",
                "assurance_tone": "green",
                "status": "green",
                "confidence": "review-limited",
                "summary": "Velocity evidence is retained.",
                "evidence": [f"Velocity evidence statement {index}." for index in range(14)],
                "findings": [f"Velocity finding {index}." for index in range(7)],
                "unavailable": [f"Velocity limitation {index}." for index in range(4)],
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": None,
                "presented_score": None,
                "score_value": None,
                "score_band_label": "NOT SCORED",
                "score_tone": "gray",
                "assurance_label": "SUPPLEMENTAL",
                "assurance_tone": "gray",
                "status": "supplemental",
                "confidence": "review-limited",
                "section_group": "assurance_ledger",
                "technical_section": False,
                "findings": [],
                "evidence": [],
                "unavailable": [],
            },
            {
                "id": "client_human_acceptance",
                "label": "Client / Human Acceptance",
                "score": None,
                "presented_score": None,
                "score_value": None,
                "score_band_label": "NOT SCORED",
                "score_tone": "gray",
                "assurance_label": "PENDING HUMAN APPROVAL",
                "assurance_tone": "gray",
                "status": "human_review_pending",
                "confidence": "review-limited",
                "section_group": "review_delivery",
                "technical_section": False,
                "approval_status": "pending_human_approval",
                "findings": [],
                "evidence": [],
                "unavailable": [],
            },
        ],
    }


def _pdf_text(data: bytes) -> str:
    return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)


def test_semantic_quality_repairs_copy_and_scanner_contradictions() -> None:
    result = normalize_client_report_quality_v47(_payload())
    sections = {item["id"]: item for item in result["sections"]}

    assert "evidence, score reconciliation, and" in sections["code_audit"]["summary"]
    assert sections["dependency_health"]["confidence"] == "high"
    assert sections["ci_cd"]["confidence"] == "high"
    assert sections["architecture_debt"]["confidence"] == "high"
    assert sections["velocity_complexity"]["confidence"] == "high"
    assert sections["secrets_review"]["confidence"] == "review-limited"
    assert not any("0 retained review-only" in item for item in sections["secrets_review"]["findings"])
    assert any("timed out before a complete result" in item for item in sections["secrets_review"]["findings"])
    assert not any("eslint" in item.casefold() for item in sections["static_analysis"]["unavailable"])
    assert any("ESLint is not configured" in item for item in sections["static_analysis"]["evidence"])
    assert any("Live Bandit execution failed" in item for item in sections["static_analysis"]["evidence"])


def test_scorecard_uses_readable_unsplit_labels_and_consistent_assurance() -> None:
    install_express_report_quality_v47()
    from nico import express_pdf_score_assurance_v1 as renderer

    payload = _payload()
    text = _pdf_text(renderer._overview_pdf(payload))

    assert "Technical Score and Evidence Assurance" in text
    assert "SUPPLEMENTAL" in text
    assert "SUPPLEMENTA\nL" not in text
    assert "DELIVERY BLOCKED" in text
    assert "Dependency / Library Ecosystem" in text


def test_control_decision_page_stays_single_page_and_removes_duplicate_confidence() -> None:
    install_express_report_quality_v47()
    from nico import express_pdf_score_assurance_v1 as renderer

    payload = normalize_client_report_quality_v47(_payload())
    data = renderer._decision_pdf(payload, "velocity_complexity", "Velocity, Complexity, and Ownership Decision Record")
    reader = PdfReader(io.BytesIO(data))
    text = _pdf_text(data)

    assert len(reader.pages) == 1
    assert "Evidence assurance" in text
    assert "Risk disposition" in text
    assert "Confidence" not in text
    assert "additional item(s) are retained" in text


def test_contribution_page_moves_long_constraints_below_score_table() -> None:
    install_express_report_quality_v47()
    from nico import express_pdf_score_assurance_v1 as renderer

    text = _pdf_text(renderer._contribution_pdf(normalize_client_report_quality_v47(_payload())))

    assert "Material score constraints" in text
    assert "Primary constraint" not in text
    assert "Score contribution" in text
    assert "Evidence assurance" in text


def test_installer_preserves_final_report_and_human_review_boundaries() -> None:
    result = install_express_report_quality_v47()

    assert result["status"] in {"installed", "already_installed"}
    assert result["report_finality"] == "final"
    assert result["approval_status"] == "pending_human_approval"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert result["full_machine_readable_evidence_preserved"] is True
