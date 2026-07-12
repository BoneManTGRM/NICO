from __future__ import annotations

from uuid import uuid4

import pytest

from nico.mid_approval_api import (
    MidReviewDispositionRequest,
    mid_review_disposition_response,
    mid_review_dispositions_response,
)
from nico.mid_review_dispositions import (
    REVIEW_DISPOSITION_VERSION,
    get_mid_review_dispositions,
    review_disposition_summary,
    submit_mid_review_disposition,
)
from nico.storage import STORE


@pytest.fixture(autouse=True)
def admin_token(monkeypatch):
    monkeypatch.setenv("NICO_ADMIN_TOKEN", "test-admin-token")


def _approval(*, inference_score_change: bool = False) -> tuple[dict, list[dict]]:
    suffix = uuid4().hex[:12]
    approval_id = f"mid_approval_review_{suffix}"
    packet_id = f"mid_review_packet_{suffix}"
    packet_hash = "b" * 64
    items = [
        {
            "item_id": f"midreview_{suffix}_technical",
            "category": "low_confidence_or_limited_conclusion",
            "section_id": "architecture_debt",
            "title": "Limited architecture conclusion",
            "reason": "The conclusion is verified only with limitations.",
            "severity": "medium",
            "evidence": ["Repository structure was inspected."],
            "blockers": ["Architecture decision records unavailable."],
            "score_change_material": False,
            "inference_based": False,
            "requires_human_review": True,
        },
        {
            "item_id": f"midreview_{suffix}_inference",
            "category": "inference_or_external_context",
            "section_id": "stakeholder_alignment",
            "title": "Stakeholder validation required",
            "reason": "The conclusion depends on external context.",
            "severity": "medium",
            "evidence": ["Product context packet attached."],
            "blockers": ["Direct stakeholder confirmation unavailable."],
            "score_change_material": inference_score_change,
            "inference_based": True,
            "requires_human_review": True,
        },
    ]
    packet = {
        "status": "ready_for_review",
        "review_packet_id": packet_id,
        "review_packet_sha256": packet_hash,
        "exceptions": items,
    }
    STORE.put(
        "evidence_items",
        packet_id,
        {
            "evidence_id": packet_id,
            "customer_id": "customer_review",
            "project_id": "project_review",
            "run_id": f"midrun_{suffix}",
            "evidence": packet,
        },
    )
    approval = {
        "record_type": "mid_report_approval",
        "approval_id": approval_id,
        "approval_version": "mid-report-approval-v2",
        "status": "pending",
        "run_id": f"midrun_{suffix}",
        "customer_id": "customer_review",
        "project_id": "project_review",
        "snapshot_id": f"snapshot_{suffix}",
        "snapshot_commit_sha": "a" * 40,
        "truth_sha256": "c" * 64,
        "review_packet_id": packet_id,
        "review_packet_sha256": packet_hash,
        "exception_item_ids": [item["item_id"] for item in items],
        "review_item_dispositions": {},
    }
    STORE.put("approvals", approval_id, approval)
    return approval, items


def _submit(approval_id: str, item_id: str, decision: str, note: str = "Reviewed the exact item evidence and limitation.") -> dict:
    return submit_mid_review_disposition(
        approval_id,
        item_id,
        decision=decision,
        actor="Senior Technical Reviewer",
        note=note,
        admin_token="test-admin-token",
    )


def test_item_level_dispositions_are_hash_bound_and_all_items_are_required():
    approval, items = _approval()

    initial = review_disposition_summary(approval)
    first = _submit(approval["approval_id"], items[0]["item_id"], "accepted")
    second = _submit(approval["approval_id"], items[1]["item_id"], "accepted_inference_only")

    assert initial["approval_ready"] is False
    assert initial["pending_item_count"] == 2
    assert first["status"] == "recorded"
    assert first["disposition"]["version"] == REVIEW_DISPOSITION_VERSION
    assert len(first["disposition"]["item_sha256"]) == 64
    assert len(first["disposition"]["disposition_sha256"]) == 64
    assert first["review_dispositions"]["approval_ready"] is False
    assert second["review_dispositions"]["approval_ready"] is True
    assert second["review_dispositions"]["accepted_item_count"] == 2
    assert len(second["review_dispositions"]["disposition_set_sha256"]) == 64


def test_inference_only_is_limited_to_non_score_changing_inference_items():
    approval, items = _approval(inference_score_change=True)

    non_inference = _submit(approval["approval_id"], items[0]["item_id"], "accepted_inference_only")
    score_changing = _submit(approval["approval_id"], items[1]["item_id"], "accepted_inference_only")

    assert non_inference["status"] == "blocked"
    assert "inference-based" in non_inference["error"]
    assert score_changing["status"] == "blocked"
    assert "score-changing inference" in score_changing["error"]


def test_needs_more_evidence_and_rejection_block_structured_approval_until_replaced():
    approval, items = _approval()

    needs = _submit(
        approval["approval_id"],
        items[0]["item_id"],
        "needs_more_evidence",
        note="Direct architecture decision evidence is required before approval.",
    )
    rejected = _submit(
        approval["approval_id"],
        items[1]["item_id"],
        "rejected",
        note="The supplied stakeholder context does not support this conclusion.",
    )
    repaired_first = _submit(approval["approval_id"], items[0]["item_id"], "accepted")
    repaired_second = _submit(approval["approval_id"], items[1]["item_id"], "accepted_inference_only")

    assert needs["review_dispositions"]["blocking_item_count"] == 1
    assert rejected["review_dispositions"]["blocking_item_count"] == 2
    assert rejected["review_dispositions"]["approval_ready"] is False
    assert repaired_first["review_dispositions"]["approval_ready"] is False
    assert repaired_second["review_dispositions"]["approval_ready"] is True


def test_dispositions_require_admin_authentication_and_cannot_change_terminal_approval():
    approval, items = _approval()

    unauthorized = submit_mid_review_disposition(
        approval["approval_id"],
        items[0]["item_id"],
        decision="accepted",
        actor="Reviewer",
        note="Reviewed exact evidence.",
        admin_token="wrong",
    )
    terminal = STORE.get("approvals", approval["approval_id"])
    terminal["status"] = "approved"
    STORE.put("approvals", approval["approval_id"], terminal)
    blocked = _submit(approval["approval_id"], items[0]["item_id"], "accepted")

    assert unauthorized["status"] == "blocked"
    assert unauthorized["admin_write"]["configured"] is True
    assert blocked["status"] == "blocked"
    assert "terminal approval" in blocked["error"]


def test_disposition_api_returns_reviewable_item_details_without_raw_capability_data():
    approval, items = _approval()

    recorded = mid_review_disposition_response(
        approval["approval_id"],
        items[0]["item_id"],
        MidReviewDispositionRequest(
            decision="accepted",
            actor="Reviewer",
            note="Reviewed the exact technical limitation and accepted it as represented.",
        ),
        x_nico_admin_token="test-admin-token",
    )
    listed = mid_review_dispositions_response(
        approval["approval_id"],
        x_nico_admin_token="test-admin-token",
    )
    direct = get_mid_review_dispositions(approval["approval_id"], admin_token="test-admin-token")

    assert recorded["status"] == "recorded"
    assert listed["status"] == "ready"
    assert direct["review_dispositions"]["expected_item_count"] == 2
    assert direct["review_dispositions"]["items"][0]["title"]
    assert "token" not in repr(direct).lower()
