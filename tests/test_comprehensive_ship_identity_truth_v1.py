from __future__ import annotations

from nico.strategic_human_evidence_binding_v1 import (
    _project_descriptive_engagement_identity,
)


def test_stakeholder_projection_keeps_persisted_display_identity_review_bound() -> None:
    result = {
        "evidence": {
            "engagement": {
                "mode": "internal",
                "access_method": "GitHub HTTPS/API - read-only",
                "authorized_scope": "Full repository at exact assessed SHA - read-only",
                "primary_technical_contact": "NICO Acceptance Contact",
                "client_identity": "",
                "project_identity": "",
                "client_delivery_identity_valid": False,
            }
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    context = {
        "customer_name": "NICO Acceptance Client",
        "client_name": "NICO Acceptance Client",
        "project_name": "NICO Acceptance Project",
    }

    _project_descriptive_engagement_identity(result, context)

    engagement = result["evidence"]["engagement"]
    assert engagement["client_identity"] == "NICO Acceptance Client"
    assert engagement["project_identity"] == "NICO Acceptance Project"
    assert engagement["primary_technical_contact"] == "NICO Acceptance Contact"
    assert engagement["access_method"] == "GitHub HTTPS/API - read-only"
    assert engagement["authorized_scope"] == "Full repository at exact assessed SHA - read-only"
    assert engagement["mode"] == "client"
    assert engagement["client_delivery_identity_valid"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_stakeholder_projection_never_invents_missing_display_identity() -> None:
    result = {
        "evidence": {"engagement": {"primary_technical_contact": "NICO Acceptance Contact"}},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    _project_descriptive_engagement_identity(result, {})

    engagement = result["evidence"]["engagement"]
    assert "client_identity" not in engagement
    assert "project_identity" not in engagement
    assert "mode" not in engagement
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_run_service_carries_display_names_into_every_stage_context() -> None:
    # This is a source-level contract around the authoritative orchestration boundary.
    # Provider unit tests above cover the behavioral consumption of these keys.
    from pathlib import Path

    source = Path("nico/comprehensive_run_service.py").read_text(encoding="utf-8")
    assert '"customer_name": customer_name' in source
    assert '"client_name": customer_name' in source
    assert '"project_name": project_name' in source
    assert 'identity.get("customer_name") or identity.get("client_name")' in source
