from __future__ import annotations

from nico.comprehensive_intake_display_metadata_v2 import (
    _human_evidence_with_display_metadata,
)
from nico.comprehensive_report_worker_runtime_v90 import _report_identity
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence


def _context() -> dict[str, object]:
    raw_human_evidence = {
        "stakeholder_context": {
            "evidence": {
                "primary_technical_contact": "NICO Acceptance Contact",
                "access_method": "GitHub HTTPS/API - read-only",
                "authorized_scope": "Full repository at exact assessed SHA - read-only",
            }
        }
    }
    retained = _human_evidence_with_display_metadata(
        raw_human_evidence,
        client_name="NICO Acceptance Client",
        project_name="NICO Acceptance Project",
    )
    return {
        "run_id": "comprun_display_metadata_regression",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_display_metadata_regression",
        "customer_id": "customer-regression",
        "project_id": "project-regression",
        "human_evidence": normalize_strategic_human_evidence(retained),
    }


def test_detached_report_identity_recovers_display_metadata_from_retained_evidence() -> None:
    identity = _report_identity(_context())

    assert identity["run_id"] == "comprun_display_metadata_regression"
    assert identity["repository"] == "BoneManTGRM/NICO"
    assert identity["commit_sha"] == "a" * 40
    assert identity["customer_name"] == "NICO Acceptance Client"
    assert identity["project_name"] == "NICO Acceptance Project"
    assert identity["primary_technical_contact"] == "NICO Acceptance Contact"


def test_direct_final_context_display_metadata_wins_over_retained_fallback() -> None:
    context = _context()
    context.update(
        {
            "customer_name": "Direct Client",
            "project_name": "Direct Project",
            "primary_technical_contact": "Direct Contact",
        }
    )

    identity = _report_identity(context)

    assert identity["customer_name"] == "Direct Client"
    assert identity["project_name"] == "Direct Project"
    assert identity["primary_technical_contact"] == "Direct Contact"
