from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_artifact_manifest_approval_v1 import attach_artifact_manifest


def _pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    pdf.drawString(40, 760, "NICO Comprehensive")
    pdf.drawRightString(570, 25, "Page 1")
    pdf.showPage()
    pdf.drawString(40, 760, "Functional QA")
    pdf.drawRightString(570, 25, "Section 1 of 8 | Page 1 of 2")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _package() -> dict:
    candidate = {
        "candidate_id": "NICO-SCAN-NAV-1",
        "finding_id": "NICO-SCAN-NAV-1",
        "scanner": "gitleaks",
        "category": "secret",
        "rule_id": "generic-api-key",
        "source_path": "apps/web/example.tsx",
        "line": 12,
        "evidence": "synthetic candidate",
        "evidence_quality": "count_only",
        "proposed_disposition": "review_required",
    }
    finding = {
        "finding_id": "NICO-FINDING-NAV-1",
        "priority": "P2",
        "title": "Review example complexity",
        "path": "apps/web/example.tsx",
        "line": 12,
        "location": "apps/web/example.tsx:12",
        "observed_evidence": "cyclomatic_complexity=35",
        "business_impact": "Review cost is concentrated.",
        "recommended_correction": "Extract cohesive logic.",
        "verification": "Exact-SHA rerun verifies the correction.",
        "disposition": "human_review_required",
    }
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "run_id": "comprun_manifest_navigation_v1",
            "customer_id": "customer_manifest",
            "project_id": "project_manifest",
            "evidence_ledger_id": "ledger_manifest_navigation_v1",
            "generated_at": "2026-08-04T15:22:00Z",
            "report_language": "en",
        },
        "generated_at": "2026-08-04T15:22:00Z",
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
            "canonical_scanner_finding_register": {
                "findings": [candidate],
                "totals": {
                    "raw": 1,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
                    "material": 0,
                    "review_required": 1,
                    "exact_source": 0,
                    "source_path": 0,
                    "payload_without_source": 0,
                    "count_only": 1,
                },
            },
        },
        "client_finding_remediation_register": {
            "summary": {
                "decision_finding_count": 1,
                "exact_source_code_finding_count": 1,
            },
            "code_findings": [finding],
            "operational_findings": [],
        },
        "roadmap": [],
        "staffing_plan": [],
    }
    pdf = _pdf()
    return {
        "json": canonical,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "markdown": (
            "# NICO Comprehensive\n\n"
            "Generated: 2026-08-04T15:22:00Z\n\n"
            "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n"
        ),
        "html": (
            "<html><body><h1>NICO Comprehensive</h1>"
            "<p>Generated: 2026-08-04T15:22:00Z</p></body></html>"
        ),
        "client_report_completion": {},
    }


def test_manifest_includes_all_client_artifacts_and_metadata() -> None:
    result = attach_artifact_manifest(_package())
    artifacts = result["artifact_manifest"]["artifacts"]
    types = {item["artifact_type"] for item in artifacts}

    assert types == {
        "findings_csv",
        "evidence_csv",
        "candidate_register_json",
        "remediation_backlog_json",
        "markdown_report",
        "html_report",
        "comprehensive_pdf",
        "canonical_json",
    }
    for item in artifacts:
        assert item["filename"]
        assert item["sha256"]
        assert item["size_bytes"] > 0
        assert item["media_type"]
        assert item["repository"] == "BoneManTGRM/NICO"
        assert item["commit_sha"] == "b" * 40
        assert item["run_id"] == "comprun_manifest_navigation_v1"
        assert item["evidence_ledger_id"] == "ledger_manifest_navigation_v1"
        assert item["generated_at"] == "2026-08-04T15:22:00Z"


def test_final_pdf_has_continuous_physical_labels_and_bookmarks() -> None:
    result = attach_artifact_manifest(_package())
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert reader.outline
    for index in range(1, len(reader.pages) + 1):
        assert f"Document page {index} of {len(reader.pages)}" in extracted
    assert "Section 1 of 8 | Sheet 1 of 2" in extracted
    assert "Page 1" not in extracted
