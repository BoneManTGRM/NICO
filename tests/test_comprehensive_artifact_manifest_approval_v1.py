from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_artifact_manifest_approval_v1 import (
    APPROVAL_SCHEMA,
    MANIFEST_SCHEMA,
    MAX_CLIENT_PDF_PAGES,
    attach_artifact_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BINDING = ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
COMMIT = "3c4352ae1873c547dd01406da833d2faedb5039b"
RUN_ID = "comprun_manifest_v1"


def _pdf(text: str = "NICO Comprehensive automated draft") -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(40, 780, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _package() -> dict:
    candidate = {
        "candidate_id": "NICO-SCAN-1",
        "finding_id": "NICO-SCAN-1",
        "scanner": "gitleaks",
        "category": "secret",
        "rule_id": "generic-api-key",
        "normalized_rule_family": "secret-candidate:generic-api-key",
        "severity": "medium",
        "scanner_severity": "medium",
        "confidence": "medium",
        "reachability": "not_assessed",
        "production_classification": "production_or_unknown",
        "source_path": "apps/web/example.tsx",
        "line": 12,
        "evidence": "candidate retained",
        "evidence_quality": "count_only",
        "evidence_digest_sha256": "a" * 64,
        "duplicate_group_id": "NICO-DUPE-1",
        "batch_disposition_key": "NICO-BATCH-1",
        "proposed_disposition": "review_required",
        "human_disposition": None,
        "disposition_rationale": "Human review pending.",
        "reviewer_identity": None,
        "review_timestamp": None,
        "raw_payload_retention_state": "count_only",
    }
    finding = {
        "finding_id": "NICO-FINDING-1",
        "priority": "P2",
        "priority_score": 30,
        "priority_rationale": "Complexity alone does not establish P1 impact.",
        "technical_severity": "moderate",
        "category": "architecture",
        "finding_family": "complexity_hotspot",
        "title": "Reduce complexity in example",
        "path": "apps/web/example.tsx",
        "line": 12,
        "location": "apps/web/example.tsx:12",
        "observed_evidence": "cyclomatic_complexity=35",
        "business_impact": "Regression risk is concentrated.",
        "recommended_correction": "Extract bounded components.",
        "verification": "Exact-SHA rerun no longer reports the hotspot.",
        "disposition": "human_review_required",
        "evidence_confidence": "high",
        "critical_path_relevance": [],
    }
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": COMMIT,
            "run_id": RUN_ID,
            "customer_id": "default_customer",
            "project_id": "default_project",
            "evidence_ledger_id": "ledger_manifest_v1",
            "generated_at": "2026-08-04T00:14:12Z",
            "report_language": "en",
        },
        "assessment": {
            "technical_score": 93,
            "evidence_adjusted_score": 89,
            "canonical_scanner_finding_register": {
                "artifact_schema": "nico.canonical-scanner-findings.v1",
                "findings": [candidate],
                "totals": {
                    "raw": 1,
                    "material": 0,
                    "review_required": 1,
                    "approved_or_nonblocking": 0,
                    "excluded_test_only": 0,
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
            "excluded_non_production_findings": [],
        },
        "roadmap": [
            {
                "window": "0-30 days",
                "objective": "Review priority evidence.",
                "approval_state": "illustrative",
            }
        ],
        "staffing_plan": [],
    }
    pdf = _pdf()
    return {
        "json": canonical,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_page_count": 1,
        "markdown": "# NICO Comprehensive\n\nAUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED\n",
        "html": "<html><body><h1>NICO Comprehensive</h1></body></html>",
        "client_report_completion": {},
    }


def test_manifest_binds_all_required_structured_artifacts() -> None:
    result = attach_artifact_manifest(_package())
    manifest = result["artifact_manifest"]
    types = {item["artifact_type"] for item in manifest["artifacts"]}

    assert manifest["artifact_schema"] == MANIFEST_SCHEMA
    assert manifest["manifest_id"].startswith("NICO-MANIFEST-")
    assert types == {
        "findings_csv",
        "evidence_csv",
        "candidate_register_json",
        "remediation_backlog_json",
        "comprehensive_pdf",
        "canonical_json",
    }
    assert manifest["identity"]["repository"] == "BoneManTGRM/NICO"
    assert manifest["identity"]["commit_sha"] == COMMIT
    assert manifest["identity"]["run_id"] == RUN_ID
    assert manifest["lifecycle"]["report_finality"] == "automated_draft"
    assert manifest["lifecycle"]["client_delivery_status"] == "blocked"
    assert manifest["approval"]["artifact_schema"] == APPROVAL_SCHEMA
    assert manifest["approval"]["decision"] == "pending"
    assert manifest["approval"]["client_delivery_allowed"] is False


def test_final_pdf_json_and_manifest_digests_recompute_exactly() -> None:
    result = attach_artifact_manifest(_package())
    pdf = base64.b64decode(result["pdf_base64"])
    canonical_json = result["canonical_json"].encode("utf-8")
    evidence_manifest = result["evidence_manifest_json"].encode("utf-8")

    assert hashlib.sha256(pdf).hexdigest() == result["pdf_sha256"]
    assert hashlib.sha256(canonical_json).hexdigest() == result["canonical_json_sha256"]
    assert hashlib.sha256(evidence_manifest).hexdigest() == result[
        "evidence_manifest_sha256"
    ]
    assert result["draft_artifact_identity"] == {
        "artifact_schema": "nico.comprehensive-draft-artifact-identity.v1",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "run_id": RUN_ID,
        "pdf_sha256": result["pdf_sha256"],
        "canonical_json_sha256": result["canonical_json_sha256"],
        "evidence_manifest_sha256": result["evidence_manifest_sha256"],
        "manifest_id": result["artifact_manifest"]["manifest_id"],
        "report_finality": "automated_draft",
        "human_review_status": "pending",
        "client_delivery_status": "blocked",
    }


def test_pdf_contains_client_manifest_and_pending_approval_record() -> None:
    result = attach_artifact_manifest(_package())
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert len(reader.pages) == 3
    assert len(reader.pages) <= MAX_CLIENT_PDF_PAGES
    assert "Client Artifact Manifest" in extracted
    assert "Human Review and Exact-Artifact Approval Record" in extracted
    assert "REVIEW PACKAGE READY · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED" in extracted
    assert "Review package ready: Yes" in extracted
    assert "Human approval: Pending" in extracted
    assert "Client delivery: Blocked" in extracted
    assert "Automation cannot change this package to APPROVED FINAL" in extracted
    assert "final byte digest" in extracted


def test_structured_exports_are_present_and_nonempty() -> None:
    result = attach_artifact_manifest(_package())

    assert "NICO-FINDING-1" in result["findings_csv"]
    assert "NICO-SCAN-1" in result["evidence_csv"]
    candidate_register = json.loads(result["candidate_register_json"])
    backlog = json.loads(result["remediation_backlog_json"])
    assert candidate_register["findings"][0]["candidate_id"] == "NICO-SCAN-1"
    assert backlog["roadmap"][0]["window"] == "0-30 days"
    assert len(result["findings_csv_sha256"]) == 64
    assert len(result["evidence_csv_sha256"]) == 64
    assert len(result["candidate_register_sha256"]) == 64
    assert len(result["remediation_backlog_sha256"]) == 64


def test_cross_format_readiness_and_manifest_states_match() -> None:
    result = attach_artifact_manifest(_package())
    canonical = result["json"]

    assert result["review_package_ready"] is True
    assert result["human_review_status"] == "pending"
    assert result["client_delivery_status"] == "blocked"
    assert result["report_finality"] == "automated_draft"
    assert result["client_delivery_allowed"] is False
    assert canonical["lifecycle"]["review_package_ready"] is True
    assert canonical["lifecycle"]["human_review_status"] == "pending"
    assert canonical["lifecycle"]["client_delivery_status"] == "blocked"
    assert canonical["approval"]["reviewer_authorized"] is False
    assert "## Client Artifact Manifest" in result["markdown"]
    assert "- Review package ready: Yes" in result["markdown"]
    assert "- Human approval: Pending" in result["markdown"]
    assert "- Client delivery: Blocked" in result["markdown"]
    assert 'data-nico-artifact-manifest="true"' in result["html"]


def test_regenerated_package_creates_new_draft_identity_and_never_reuses_approval() -> None:
    first = attach_artifact_manifest(_package())
    changed = _package()
    changed["pdf_base64"] = base64.b64encode(_pdf("Changed report bytes")).decode("ascii")
    second = attach_artifact_manifest(changed)

    assert first["pdf_sha256"] != second["pdf_sha256"]
    assert first["draft_artifact_identity"] != second["draft_artifact_identity"]
    assert second["json"]["approval"]["decision"] == "pending"
    assert second["json"]["approval"]["approval_record_id"] is None
    assert second["client_delivery_allowed"] is False


def test_runtime_binds_manifest_after_priority_and_review_layers() -> None:
    source = RUNTIME_BINDING.read_text(encoding="utf-8")

    companion = source.index("install_comprehensive_review_companion_v5()")
    priority = source.index("install_client_finding_priority_calibration_v1()")
    manifest = source.index("install_comprehensive_artifact_manifest_approval_v1()")
    assert companion < priority < manifest
    assert 'RUNTIME_REVISION = "v72-exact-digest-approved-delivery"' in source
    assert '"artifact_manifest_present": True' in source
    assert '"detached_manifest_binds_final_pdf": True' in source
    assert '"reviewer_role_required": True' in source
    assert '"reviewer_authorization_required": True' in source
    assert '"regeneration_invalidates_approval": True' in source
    assert '"review_package_ready": True' in source
    assert '"human_review_status": "pending"' in source
    assert '"client_delivery_status": "blocked"' in source
