from __future__ import annotations

from pathlib import Path

from nico.phase3_engagement_intake_v1 import (
    client_delivery_identity_valid,
    validate_and_enrich_intake,
)


RUN_TOKEN = "a" * 32
RUN_ID = f"comprun_{RUN_TOKEN}"


def _complete_public_client_payload() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "client_name": "Qualification Client",
        "project_name": "Qualification Project",
        "authorized": True,
        "authorization_confirmed": True,
        "human_evidence": {
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": ["Authorized technical contact"],
                    "access_method": ["Authorized read-only repository access"],
                    "authorized_scope": ["Bounded repository assessment"],
                }
            }
        },
    }


def test_complete_authorized_public_client_intake_gets_run_local_scope_before_persistence() -> None:
    enriched = validate_and_enrich_intake(_complete_public_client_payload())

    assert enriched["customer_id"] == f"customer_engagement_{RUN_TOKEN}"
    assert enriched["project_id"] == f"project_engagement_{RUN_TOKEN}"
    assert enriched["phase3_scope_source"] == "authorized_public_client_engagement"
    assert enriched["phase3_engagement_mode"] == "client"

    stakeholder = enriched["human_evidence"]["stakeholder_context"]
    evidence = stakeholder["evidence"]
    assert evidence["engagement_mode"] == ["client"]
    assert evidence["client_identity"] == ["Qualification Client"]
    assert evidence["project_identity"] == ["Qualification Project"]

    record = {
        "identity": {
            "customer_id": enriched["customer_id"],
            "project_id": enriched["project_id"],
        },
        "human_evidence": {"modules": {"stakeholder_context": stakeholder}},
    }
    assert client_delivery_identity_valid(record) is True


def test_display_labels_without_complete_client_context_remain_non_client() -> None:
    payload = _complete_public_client_payload()
    stakeholder = payload["human_evidence"]["stakeholder_context"]
    del stakeholder["evidence"]["access_method"]

    enriched = validate_and_enrich_intake(payload)

    assert enriched["customer_id"] == "default_customer"
    assert enriched["project_id"] == "default_project"
    assert enriched["phase3_engagement_mode"] == "internal"
    assert enriched["human_evidence"]["stakeholder_context"]["evidence"]["engagement_mode"] == ["internal"]


def test_unconfirmed_public_client_context_cannot_mint_client_scope() -> None:
    payload = _complete_public_client_payload()
    payload["authorization_confirmed"] = False

    enriched = validate_and_enrich_intake(payload)

    assert enriched["customer_id"] == "default_customer"
    assert enriched["project_id"] == "default_project"
    assert enriched["phase3_engagement_mode"] == "internal"


def test_reserved_production_proof_scope_is_never_promoted() -> None:
    payload = _complete_public_client_payload()
    payload["customer_id"] = "nico_production_proof"
    payload["project_id"] = "spanish_comprehensive_production"

    enriched = validate_and_enrich_intake(payload)

    assert enriched["customer_id"] == "nico_production_proof"
    assert enriched["project_id"] == "spanish_comprehensive_production"
    assert enriched["phase3_engagement_mode"] == "internal"


def test_operator_review_action_keeps_delivery_scope_separate_and_reads_nested_identity() -> None:
    source = Path("apps/web/app/AssessmentFinalReviewAction.tsx").read_text(encoding="utf-8")

    assert "function clientDeliveryIdentityReady" in source
    assert "const identity = canonicalIdentity(value);" in source
    assert "identity.customer_id" in source
    assert "identity.project_id" in source
    assert 'actions.dataset.nicoReviewGate = "blocked"' in source
    assert "actions.dataset.nicoClientDeliveryIdentity" in source
    assert "ready: passed && reviewRequired && deliveryBlocked," in source
    assert "clientDeliveryIdentityReady: identityReady" in source
