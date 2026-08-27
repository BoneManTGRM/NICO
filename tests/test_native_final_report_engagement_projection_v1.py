from __future__ import annotations


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


def test_native_final_report_provider_passes_durable_display_identity_to_report_builder(
    monkeypatch,
) -> None:
    from nico import comprehensive_native_providers as providers

    context = _context()
    captured: dict[str, object] = {}

    def fake_build_comprehensive_report_package(*, identity, stage_results):
        captured["identity"] = dict(identity)
        captured["stage_results"] = stage_results
        return {
            "status": "complete",
            "report_id": "report-native-engagement-projection",
            "canonical_truth_sha256": "proof-sha",
            "assessment": {"status": "complete"},
            "report_package": {
                "json": {"identity": dict(identity)},
                "pdf_page_count": 1,
            },
        }

    monkeypatch.setattr(
        providers,
        "build_comprehensive_report_package",
        fake_build_comprehensive_report_package,
    )

    canonical_scope = providers._identity(context)
    assert canonical_scope == {
        "run_id": "comprun_native_engagement_projection",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_native_engagement_projection",
        "customer_id": "customer_scope_native",
        "project_id": "project_scope_native",
    }

    result = providers.final_report_generation_provider(context)
    assert result["status"] == "complete", result

    identity = captured["identity"]
    assert isinstance(identity, dict)
    assert identity["customer_id"] == "customer_scope_native"
    assert identity["project_id"] == "project_scope_native"
    assert identity["customer_name"] == "NICO Acceptance Client"
    assert identity["project_name"] == "NICO Acceptance Project"
    assert identity["primary_technical_contact"] == "NICO Acceptance Contact"

    stages = captured["stage_results"]
    assert isinstance(stages, dict)
    stakeholder = stages["stakeholder_and_business_alignment"]
    evidence = stakeholder["evidence"]
    assert evidence["access_method"] == "GitHub HTTPS/API - read-only"
    assert evidence["primary_technical_contact"] == "NICO Acceptance Contact"
    assert evidence["authorized_scope"] == "Full repository at exact assessed SHA - read-only"


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
