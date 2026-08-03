from __future__ import annotations

from nico import comprehensive_canonical_report_source_v1 as source


def test_canonical_package_carries_explicit_comprehensive_service_identity(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        source,
        "synchronize_maturity_label_truth",
        lambda stages: (dict(stages), {"status": "synchronized"}),
    )
    monkeypatch.setattr(
        source,
        "_stage_summary",
        lambda stage_id, result: {
            "stage_id": stage_id,
            "status": result.get("status", "complete"),
        },
    )
    monkeypatch.setattr(
        source,
        "_assessment",
        lambda stages: {
            "sections": [],
            "maturity_signal": {"presented_score": 93, "level": "Exceptional"},
        },
    )
    monkeypatch.setattr(
        source,
        "_decision_summary",
        lambda identity, assessment, ordered: "Evidence-bound decision summary.",
    )
    monkeypatch.setattr(source, "_now", lambda: "2026-08-03T00:00:00Z")
    monkeypatch.setattr(source, "_canonical_hash", lambda value: "a" * 64)

    result = source.build_canonical_report_source(
        {
            "run_id": "comprun_service_identity",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "0" * 40,
            "evidence_ledger_id": "ledger_service_identity",
            "customer_id": "customer_service_identity",
            "project_id": "project_service_identity",
            "prior_stage_results": {
                "authorization_and_scope": {"status": "complete"},
            },
        }
    )

    package = result["report_package"]
    canonical = package["json"]

    assert result["status"] == "complete"
    assert result["artifact_schema"] == "nico.comprehensive_canonical_report_source.v6"
    assert result["service_id"] == "comprehensive"
    assert package["service_id"] == "comprehensive"
    assert canonical["service_id"] == "comprehensive"
    assert package["human_review_required"] is True
    assert package["client_delivery_allowed"] is False
    assert canonical["human_review_required"] is True
    assert canonical["client_delivery_allowed"] is False
