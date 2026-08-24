from __future__ import annotations

import pytest

from nico.phase3_engagement_intake_v1 import validate_and_enrich_intake


def test_public_optional_client_project_labels_remain_internal_metadata() -> None:
    enriched = validate_and_enrich_intake(
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "client_name": "Cody Jenkins",
            "project_name": "NICO Audit",
            "authorization_confirmed": True,
            "human_evidence": {},
        }
    )

    assert enriched["client_name"] == "Cody Jenkins"
    assert enriched["project_name"] == "NICO Audit"
    assert enriched["phase3_engagement_mode"] == "internal"
    evidence = enriched["human_evidence"]["stakeholder_context"]["evidence"]
    assert evidence["engagement_mode"] == ["internal"]
    assert "client_identity" not in evidence
    assert "project_identity" not in evidence


def test_reserved_spanish_production_proof_scope_remains_non_client() -> None:
    enriched = validate_and_enrich_intake(
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "nico_production_proof",
            "project_id": "spanish_comprehensive_production",
            "client_name": "",
            "project_name": "",
            "authorization_confirmed": True,
            "human_evidence": {},
        }
    )

    assert enriched["phase3_engagement_mode"] == "internal"
    assert enriched["human_evidence"]["stakeholder_context"]["evidence"]["engagement_mode"] == ["internal"]


def test_authoritative_client_scope_still_requires_client_context() -> None:
    with pytest.raises(ValueError, match="client_engagement_context_required"):
        validate_and_enrich_intake(
            {
                "repository": "BoneManTGRM/NICO",
                "customer_id": "customer_acme",
                "project_id": "project_platform",
                "client_name": "Acme",
                "project_name": "Platform",
                "authorization_confirmed": True,
                "human_evidence": {"stakeholder_context": {"evidence": {}}},
            }
        )


def test_partial_authoritative_scope_fails_closed() -> None:
    with pytest.raises(ValueError, match="client_project_scope_identity_required"):
        validate_and_enrich_intake(
            {
                "repository": "BoneManTGRM/NICO",
                "customer_id": "customer_acme",
                "project_id": "default_project",
                "client_name": "Acme",
                "project_name": "Platform",
                "authorization_confirmed": True,
                "human_evidence": {},
            }
        )


def test_legacy_scope_omission_keeps_original_client_mode_contract() -> None:
    with pytest.raises(ValueError, match="client_engagement_context_required"):
        validate_and_enrich_intake(
            {
                "repository": "BoneManTGRM/NICO",
                "client_name": "Acme",
                "project_name": "Platform",
                "authorization_confirmed": True,
                "human_evidence": {"stakeholder_context": {"evidence": {}}},
            }
        )
