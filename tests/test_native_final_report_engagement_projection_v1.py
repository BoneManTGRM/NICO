from __future__ import annotations

import base64
import io

from pypdf import PdfReader


def _context() -> dict[str, object]:
    return {
        "run_id": "comprun_native_engagement_projection",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_native_engagement_projection",
        "customer_id": "customer_scope_native",
        "project_id": "project_scope_native",
        "customer_name": "NICO Acceptance Client",
        "project_name": "NICO Acceptance Project",
        "primary_technical_contact": "NICO Acceptance Contact",
        "access_method": "GitHub HTTPS/API - read-only",
        "authorized_scope": "Full repository at exact assessed SHA - read-only",
        "engagement_metadata": {
            "artifact_schema": "nico.comprehensive_engagement_metadata.v1",
            "client_name": "NICO Acceptance Client",
            "project_name": "NICO Acceptance Project",
            "primary_technical_contact": "NICO Acceptance Contact",
            "access_method": "GitHub HTTPS/API - read-only",
            "authorized_scope": "Full repository at exact assessed SHA - read-only",
        },
        "prior_stage_results": {
            "evidence_reconciliation_and_scoring": {
                "status": "complete",
                "assessment": {
                    "status": "complete",
                    "service_id": "comprehensive",
                    "executive_summary": "Synthetic provider-boundary regression.",
                    "maturity_signal": {
                        "level": "Exceptional",
                        "score": 93,
                        "presented_score": 93,
                        "evidence_readiness_score": 93,
                    },
                    "sections": [],
                    "unavailable_data_notes": [],
                    "human_review_required": True,
                    "client_ready": False,
                    "client_delivery_allowed": False,
                },
            },
            "stakeholder_and_business_alignment": {
                "status": "complete",
                "summary": "Client-supplied engagement context retained.",
                "evidence": {
                    "access_method": "GitHub HTTPS/API - read-only",
                    "primary_technical_contact": "NICO Acceptance Contact",
                    "authorized_scope": "Full repository at exact assessed SHA - read-only",
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_native_final_report_provider_does_not_narrow_away_display_identity() -> None:
    from nico import comprehensive_native_providers as providers

    context = _context()
    canonical_scope = providers._identity(context)
    report_identity = providers._report_identity(context)

    assert canonical_scope == {
        "run_id": "comprun_native_engagement_projection",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_native_engagement_projection",
        "customer_id": "customer_scope_native",
        "project_id": "project_scope_native",
    }
    assert report_identity["customer_id"] == "customer_scope_native"
    assert report_identity["project_id"] == "project_scope_native"
    assert report_identity["customer_name"] == "NICO Acceptance Client"
    assert report_identity["project_name"] == "NICO Acceptance Project"
    assert report_identity["primary_technical_contact"] == "NICO Acceptance Contact"

    result = providers.final_report_generation_provider(context)
    assert result["status"] == "complete", result
    package = result["report_package"]
    canonical = package["json"]
    identity = canonical["identity"]

    assert identity["customer_id"] == "customer_scope_native"
    assert identity["project_id"] == "project_scope_native"
    assert identity["customer_name"] == "NICO Acceptance Client"
    assert identity["project_name"] == "NICO Acceptance Project"
    assert identity["primary_technical_contact"] == "NICO Acceptance Contact"

    markdown = package["markdown"]
    assert "Client display name: NICO Acceptance Client" in markdown
    assert "Project display name: NICO Acceptance Project" in markdown
    assert "Primary technical contact: NICO Acceptance Contact" in markdown

    pdf = base64.b64decode(package["pdf_base64"])
    rendered = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    assert "NICO Acceptance Client" in rendered
    assert "NICO Acceptance Project" in rendered


def test_native_report_identity_keeps_genuine_missing_display_fields_missing() -> None:
    from nico import comprehensive_native_providers as providers

    context = _context()
    context["customer_name"] = ""
    context["project_name"] = ""
    context["primary_technical_contact"] = ""
    identity = providers._report_identity(context)

    assert identity["customer_id"] == "customer_scope_native"
    assert identity["project_id"] == "project_scope_native"
    assert "customer_name" not in identity
    assert "project_name" not in identity
    assert "primary_technical_contact" not in identity
