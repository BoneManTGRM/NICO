from copy import deepcopy
from types import SimpleNamespace

import pytest

from nico import comprehensive_report_content_render_v66 as content
from nico.comprehensive_review_report_truth_v1 import build_review_truth
from tests.test_phase2_full_coverage_v2 import _complete_review, _record


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_current_candidate_summary_uses_completed_ledger_without_rewriting_scanner_history(language):
    record = _complete_review(_record())
    canonical = deepcopy(record["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"])
    canonical["human_review_truth"] = build_review_truth(record)
    canonical["report_language"] = language
    canonical["review_candidate_summary"] = {"raw_total": 3, "review_required_total": 3}
    canonical["review_candidate_register"] = [{"candidate_id": "A", "title": "Pending remediation stays pending", "disposition": "review_required"}]
    original = deepcopy(canonical)
    renderer = SimpleNamespace(_stage=lambda *args, **kwargs: {"summary": args[2], **kwargs})
    stage = content._candidate_stage(canonical, renderer)
    rendered = repr(stage)
    assert "authorized human disposition remains pending" not in rendered
    assert "Human review required; assurance-only until triaged" not in rendered
    assert "Pending remediation stays pending" in rendered
    assert stage["status"] == "complete"
    assert canonical == original


def test_incomplete_candidate_summary_does_not_claim_disposition_completion():
    record = _record()
    canonical = deepcopy(record["stage_results"]["final_comprehensive_report_generation"]["report_package"]["json"])
    canonical["human_review_truth"] = build_review_truth(record)
    canonical["review_candidate_summary"] = {"raw_total": 3, "review_required_total": 3}
    renderer = SimpleNamespace(_stage=lambda *args, **kwargs: {"summary": args[2], **kwargs})
    stage = content._candidate_stage(canonical, renderer)
    assert stage["status"] == "review_required"
    assert any("disposition remains pending" in value for value in stage["evidence"])


@pytest.mark.parametrize("spanish", [False, True])
def test_completed_ledger_changes_only_current_briefing_disposition_status(spanish):
    from nico.comprehensive_client_review_companion_v5 import substantive_review_sections
    from tests.test_comprehensive_client_review_companion_v5 import _canonical

    canonical = _canonical()
    before = {item["id"]: item for item in substantive_review_sections(canonical, spanish=spanish)}
    canonical["human_review_truth"] = build_review_truth(_complete_review(_record()))
    original = deepcopy(canonical)
    after = {item["id"]: item for item in substantive_review_sections(canonical, spanish=spanish)}
    status = after["risk_reduction_and_executive_briefing"]["status"].casefold()
    assert "disposition pending" not in status
    assert "disposición humana pendiente" not in status
    assert after["stakeholder_and_business_alignment"] == before["stakeholder_and_business_alignment"]
    assert after["six_month_roadmap"] == before["six_month_roadmap"]
    assert canonical == original


def test_completed_lineage_projection_preserves_quoted_source_language():
    from nico.candidate_lineage_runtime_patch_v1 import _rewrite_candidate_language

    source = "Source quote: NICO automated technical triage completed; authorized human disposition remains pending. in fixture.txt"
    assert _rewrite_candidate_language(source, recorded_text="Dispositions recorded.") == source
    generated = "Candidate A · NICO automated technical triage completed; authorized human disposition remains pending."
    assert _rewrite_candidate_language(generated, recorded_text="Dispositions recorded.") == "Candidate A · Dispositions recorded."
