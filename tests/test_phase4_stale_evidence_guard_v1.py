from __future__ import annotations

import pytest

import nico.comprehensive_approved_delivery_v4 as delivery_module


def test_phase4_restores_request_more_evidence_regeneration_guard(monkeypatch) -> None:
    calls: list[tuple[dict, dict]] = []

    def reject_stale(record: dict, manifest: dict) -> None:
        calls.append((record, manifest))
        raise ValueError(
            "approval_requires_new_evidence_bound_report_after_request_more_evidence"
        )

    monkeypatch.setattr(
        delivery_module,
        "require_new_report_after_evidence_request",
        reject_stale,
    )
    record = {
        "client_delivery_allowed": False,
        "approved_delivery_package": {"stale": True},
    }
    manifest = {"review": {"decision": "approved"}}
    with pytest.raises(
        ValueError,
        match="approval_requires_new_evidence_bound_report_after_request_more_evidence",
    ):
        delivery_module.attach_approved_delivery_package(record, manifest)
    assert calls == [(record, manifest)]


def test_nonapproval_clears_delivery_authorization() -> None:
    record = {
        "client_delivery_allowed": True,
        "approved_delivery_package": {"stale": True},
    }
    rejected = delivery_module.attach_approved_delivery_package(
        record,
        {"review": {"decision": "rejected"}},
    )
    assert rejected["client_delivery_allowed"] is False
    assert "approved_delivery_package" not in rejected
