from types import SimpleNamespace

from nico.express_review_target import (
    _exact_storage_record,
    attach_express_review_target,
    express_report_id,
    express_run_id,
    final_review_url,
)


def test_express_run_id_uses_generated_at_when_no_explicit_id():
    assert express_run_id({"generated_at": "2026-07-07T16:15:00Z"}) == "2026-07-07T16_15_00Z"


def test_express_report_id_is_deterministic_and_bound_to_run():
    result = {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T16:15:00Z",
    }

    first = express_report_id(result, "express_run_1")
    second = express_report_id(result, "express_run_1")
    changed = express_report_id(result, "express_run_2")

    assert first == second
    assert first.startswith("express_report_")
    assert len(first) == len("express_report_") + 24
    assert changed != first


def test_final_review_url_includes_scope():
    url = final_review_url("run_1", "customer_a", "project_b")

    assert url == "/final-review?run_id=run_1&customer_id=customer_a&project_id=project_b"


def test_attach_express_review_target_sets_exact_run_report_and_scope_before_scoring():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T16:15:00Z",
        "reports": {"markdown": "# Draft"},
    }
    request_payload = {"customer_id": "customer_a", "project_id": "project_b"}

    updated = attach_express_review_target(result, request_payload)

    assert updated["customer_id"] == "customer_a"
    assert updated["project_id"] == "project_b"
    assert updated["run_id"] == "2026-07-07T16_15_00Z"
    assert updated["report_id"].startswith("express_report_")
    assert updated["reports"]["report_id"] == updated["report_id"]
    assert updated["final_review"]["report_id"] == updated["report_id"]
    assert updated["final_review"]["url"].endswith(
        f"run_id=2026-07-07T16_15_00Z&customer_id=customer_a&project_id=project_b&report_id={updated['report_id']}"
    )
    assert "Final review target:" in updated["next_steps"][0]
    assert f"report_id={updated['report_id']}" in updated["next_steps"][0]


def test_exact_storage_record_uses_returned_run_and_preserves_final_payload():
    response = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T16:15:00Z",
        "run_id": "express_run_exact_1",
        "report_id": "express_report_exact_1",
        "client_acceptance": {"status": "ready_for_human_signoff"},
        "human_review_required": True,
        "client_ready": False,
    }
    request = SimpleNamespace(customer_id="customer_a", project_id="project_b")

    record_id, record = _exact_storage_record(request, response, lambda _req: ("fallback", {}))

    assert record_id == "express_run_exact_1"
    assert record["run_id"] == "express_run_exact_1"
    assert record["report_id"] == "express_report_exact_1"
    assert record["customer_id"] == "customer_a"
    assert record["project_id"] == "project_b"
    assert record["payload"] == response
    assert record["payload"] is not response


def test_exact_storage_record_falls_back_without_final_response():
    request = SimpleNamespace(customer_id="customer_a", project_id="project_b")

    assert _exact_storage_record(request, {}, lambda _req: ("fallback", {"status": "fallback"})) == (
        "fallback",
        {"status": "fallback"},
    )
