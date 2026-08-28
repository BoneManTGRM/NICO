from __future__ import annotations

from nico import comprehensive_human_evidence_report_v1 as v1
from nico import comprehensive_human_evidence_report_v2 as v2
from nico.comprehensive_decision_grade_markdown_v5 import _stage_summaries
from nico.comprehensive_engagement_metadata_v1 import build_comprehensive_engagement_metadata
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence


def test_large_human_module_survives_decision_grade_evidence_cap_without_loss() -> None:
    cases = [f"human-case-{index:03d}" for index in range(45)]
    human_evidence = normalize_strategic_human_evidence(
        {
            "functional_qa": {
                "evidence": {
                    "test_cases": cases,
                    "observed_results": ["human-observed-result"],
                },
                "reviewer": "Human QA Reviewer",
                "observed_at": "2026-08-27T20:00:00Z",
                "source_reference": "Client QA evidence source",
            }
        }
    )
    engagement = build_comprehensive_engagement_metadata(
        client_name="Human Retention Client",
        project_name="Human Retention Project",
        human_evidence=human_evidence,
    )
    snapshot = v1._context_snapshot(
        {
            "engagement_metadata": engagement,
            "human_evidence": human_evidence,
        }
    )

    injected = v2._inject_human_review_stages({}, snapshot)
    functional_inputs = [
        payload
        for stage_id, payload in injected.items()
        if stage_id.startswith("client_human_evidence_functional_qa")
    ]
    assert len(functional_inputs) >= 3
    assert all(len(payload.get("evidence") or {}) <= 16 for payload in functional_inputs)

    summarized = _stage_summaries(injected)
    functional_outputs = [
        stage
        for stage in summarized
        if str(stage.get("stage_id") or "").startswith(
            "client_human_evidence_functional_qa"
        )
    ]
    assert len(functional_outputs) == len(functional_inputs)
    assert all(len(stage.get("evidence") or []) <= 18 for stage in functional_outputs)

    retained = "\n".join(
        line
        for stage in functional_outputs
        for line in stage.get("evidence") or []
    )
    for case in cases:
        assert case in retained
    assert "human-observed-result" in retained
    assert "Human QA Reviewer" in retained
    assert "Client QA evidence source" in retained
