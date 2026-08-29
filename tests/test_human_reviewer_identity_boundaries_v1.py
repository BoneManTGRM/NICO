from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from nico.comprehensive_review_decision_v1 import build_reviewed_edition
from nico.comprehensive_review_work_v1 import apply_review_work_action as apply_review_work_v1
from nico.comprehensive_review_work_v2 import apply_review_work_action as apply_review_work_v2


ReviewWorkAction = Callable[..., dict[str, Any]]


def _review_required_record() -> dict[str, Any]:
    identity = {
        "run_id": "comprun_human_identity_boundary",
        "repository": "owner/repository",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_human_identity_boundary",
        "customer_id": "customer_human_identity_boundary",
        "project_id": "project_human_identity_boundary",
        "assessment_depth": "comprehensive",
        "report_language": "en",
    }
    canonical = {
        "identity": {
            key: identity[key]
            for key in (
                "run_id",
                "repository",
                "commit_sha",
                "evidence_ledger_id",
            )
        },
        "assessment": {
            "canonical_scanner_finding_register": {
                "artifact_schema": "nico.canonical_scanner_finding_register.v1",
                "candidate_record_count": 1,
                "findings": [
                    {
                        "candidate_id": "candidate-human-identity-boundary",
                        "cluster_id": "cluster-human-identity-boundary",
                        "cluster_size": 1,
                        "cluster_candidate_ids": [
                            "candidate-human-identity-boundary"
                        ],
                        "representative_candidate_id": (
                            "candidate-human-identity-boundary"
                        ),
                        "grouped_review_eligible": False,
                        "review_requires_individual_attention": True,
                        "homogeneous_evidence": True,
                        "homogeneous_verdict": True,
                        "review_unit_id": "candidate-human-identity-boundary",
                        "review_routing_class": "HUMAN_TECHNICAL_REVIEW",
                        "severity": "low",
                        "human_review_required": True,
                        "client_delivery_allowed": False,
                        "human_disposition": None,
                    }
                ],
                "review_workload_clusters": [
                    {
                        "cluster_id": "cluster-human-identity-boundary",
                        "candidate_ids": ["candidate-human-identity-boundary"],
                        "candidate_record_count": 1,
                        "cluster_size": 1,
                        "representative_candidate_id": (
                            "candidate-human-identity-boundary"
                        ),
                        "grouped_review_eligible": False,
                        "grouped_human_review_cluster": False,
                        "homogeneous_evidence": True,
                        "homogeneous_verdict": True,
                        "underlying_candidate_disposition_required": True,
                    }
                ],
                "technical_triage": {
                    "total_candidates": 1,
                    "human_review_work_units": 1,
                },
            }
        },
    }
    return {
        "identity": identity,
        "status": "review_required",
        "terminal": True,
        "human_review_completed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_results": {
            "immutable_repository_snapshot": {"snapshot": {"tree_sha": "b" * 40}},
            "deep_scanner_triage": {"scanner_run_id": "scan-human-identity-boundary"},
            "final_comprehensive_report_generation": {
                "report_package": {
                    "markdown": "# NICO Comprehensive\n",
                    "html": "<html><body>NICO Comprehensive</body></html>",
                    "pdf_base64": base64.b64encode(b"%PDF-1.4 identity fixture").decode(
                        "ascii"
                    ),
                    "json": canonical,
                    "canonical_truth_sha256": "c" * 64,
                }
            },
        },
    }


def _review_payload(*, reviewer: str, reviewer_role: str) -> dict[str, Any]:
    return {
        "action": "start_session",
        "reviewer": reviewer,
        "reviewer_role": reviewer_role,
        "review_authorized": True,
        "authorization_confirmed": True,
    }


@pytest.mark.parametrize(
    "apply_review_work",
    (
        pytest.param(apply_review_work_v1, id="phase2-v1"),
        pytest.param(apply_review_work_v2, id="phase2-v2"),
    ),
)
@pytest.mark.parametrize(
    ("reviewer", "reviewer_role"),
    (
        pytest.param("automation", "Security reviewer", id="automation-reviewer"),
        pytest.param("Alice", "system", id="system-role"),
    ),
)
def test_phase2_review_work_rejects_automation_identity_despite_true_authorization_flags(
    apply_review_work: ReviewWorkAction,
    reviewer: str,
    reviewer_role: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="automation_cannot_create_final_human_approval",
    ):
        apply_review_work(
            _review_required_record(),
            _review_payload(reviewer=reviewer, reviewer_role=reviewer_role),
            now=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    "apply_review_work",
    (
        pytest.param(apply_review_work_v1, id="phase2-v1"),
        pytest.param(apply_review_work_v2, id="phase2-v2"),
    ),
)
def test_phase2_review_work_accepts_authorized_human_reviewer(
    apply_review_work: ReviewWorkAction,
) -> None:
    ledger = apply_review_work(
        _review_required_record(),
        _review_payload(reviewer="Alice", reviewer_role="Security reviewer"),
        now=datetime(2026, 8, 28, 12, 0, tzinfo=UTC),
    )

    session = ledger["review_sessions"][0]
    assert session["reviewer"] == "Alice"
    assert session["reviewer_role"] == "Security reviewer"
    assert session["status"] == "running"


@pytest.mark.parametrize(
    ("reviewer", "reviewer_role"),
    (
        pytest.param("automation", "Security reviewer", id="automation-reviewer"),
        pytest.param("Alice", "system", id="system-role"),
    ),
)
def test_final_reviewed_edition_rejects_automation_identity(
    reviewer: str,
    reviewer_role: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="automation_cannot_create_final_human_approval",
    ):
        build_reviewed_edition(
            _review_required_record(),
            reviewer=reviewer,
            reviewer_role=reviewer_role,
            decision="approved",
            decision_reason="The exact retained artifacts were reviewed by a human.",
            decided_at="2026-08-28T12:05:00+00:00",
        )
