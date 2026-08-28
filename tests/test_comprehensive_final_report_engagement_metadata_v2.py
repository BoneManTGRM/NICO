from __future__ import annotations

from nico import comprehensive_report_package as report_package
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
)
from nico.comprehensive_report_worker_runtime_v90 import _report_identity


def _context() -> dict[str, object]:
    metadata = build_comprehensive_engagement_metadata(
        client_name="Cody Jenkins",
        project_name="NICO Audit",
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": "Cody — Repository owner / project lead",
                    "access_method": "Public GitHub repository via HTTPS/API — read-only access",
                    "authorized_scope": "BoneManTGRM/NICO — entire repository, current main branch.",
                }
            },
        },
    )
    return {
        "run_id": "comprun_display_metadata_regression",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_display_metadata_regression",
        "customer_id": "customer_display_metadata_regression",
        "project_id": "project_display_metadata_regression",
        # Detached report publication must not depend on transient scalar projections.
        "engagement_metadata": metadata,
        "human_evidence": {},
    }


def test_detached_report_identity_recovers_durable_engagement_metadata() -> None:
    identity = _report_identity(_context())

    assert identity["customer_name"] == "Cody Jenkins"
    assert identity["project_name"] == "NICO Audit"
    assert (
        identity["primary_technical_contact"]
        == "Cody — Repository owner / project lead"
    )


def test_durable_engagement_metadata_reaches_report_surfaces() -> None:
    identity = _report_identity(_context())
    package = report_package.build_comprehensive_report_package(
        identity=identity,
        stage_results={},
    )

    report = package["report_package"]
    canonical_identity = report["json"]["identity"]
    markdown = report["markdown"]

    assert canonical_identity["customer_name"] == "Cody Jenkins"
    assert canonical_identity["project_name"] == "NICO Audit"
    assert (
        canonical_identity["primary_technical_contact"]
        == "Cody — Repository owner / project lead"
    )
    assert (
        'Client display name: <span data-nico-client-literal="true">Cody Jenkins</span>'
        in markdown
    )
    assert (
        'Project display name: <span data-nico-client-literal="true">NICO Audit</span>'
        in markdown
    )
    assert (
        'Primary technical contact: <span data-nico-client-literal="true">'
        "Cody — Repository owner / project lead</span>"
        in markdown
    )
