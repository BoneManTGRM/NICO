from __future__ import annotations

import sys
from types import SimpleNamespace

from nico.express_review_target import attach_express_review_target, install_express_storage_compatibility


def test_express_route_compatibility_persists_safe_final_payload_once(monkeypatch) -> None:
    fallback_calls: list[str] = []

    def fallback_storage(_request):
        fallback_calls.append("fallback")
        return "legacy", {"status": "legacy"}

    def acceptance_gate(result):
        return {
            **result,
            "client_acceptance": {"status": "ready_for_human_signoff"},
            "human_review_required": True,
            "client_ready": False,
        }

    fake_api_main = SimpleNamespace(
        hosted_assessment_storage_record=fallback_storage,
        attach_client_acceptance_gate=acceptance_gate,
        safe_assessment_response_payload=lambda payload: dict(payload),
    )
    monkeypatch.setitem(sys.modules, "nico.api.main", fake_api_main)

    initial = attach_express_review_target(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "generated_at": "2026-07-14T17:00:00Z",
            "reports": {"markdown": "# Draft"},
        },
        {"customer_id": "customer_exact", "project_id": "project_exact"},
    )
    status = install_express_storage_compatibility()
    final = fake_api_main.attach_client_acceptance_gate(initial)
    request = SimpleNamespace(customer_id="customer_exact", project_id="project_exact")

    record_id, record = fake_api_main.hosted_assessment_storage_record(request)

    assert status["exact_run_storage"] is True
    assert status["request_local_final_payload"] is True
    assert record_id == final["run_id"]
    assert record["run_id"] == final["run_id"]
    assert record["report_id"] == final["report_id"]
    assert record["payload"]["client_acceptance"]["status"] == "ready_for_human_signoff"
    assert record["payload"]["human_review_required"] is True
    assert record["payload"]["client_ready"] is False
    assert fallback_calls == []

    assert fake_api_main.hosted_assessment_storage_record(request) == ("legacy", {"status": "legacy"})
    assert fallback_calls == ["fallback"]


def test_express_identity_attachment_preserves_explicit_report_identity(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "nico.api.main", raising=False)
    updated = attach_express_review_target(
        {
            "status": "complete",
            "run_id": "express_run_existing",
            "report_id": "express_report_existing",
            "reports": {"report_id": "express_report_existing", "markdown": "# Draft"},
        },
        {"customer_id": "customer_a", "project_id": "project_b"},
    )

    assert updated["run_id"] == "express_run_existing"
    assert updated["report_id"] == "express_report_existing"
    assert updated["reports"]["report_id"] == "express_report_existing"
    assert "report_id=express_report_existing" in updated["final_review"]["url"]
