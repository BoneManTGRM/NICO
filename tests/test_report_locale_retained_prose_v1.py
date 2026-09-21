from copy import deepcopy

import pytest

from nico.comprehensive_finding_roadmap_v1 import bind_final_finding_roadmap
from nico.comprehensive_human_evidence_report_v1 import (
    _client_summary_stage,
    _human_module_stage_specs,
    _localize_retained_stage,
)
from nico.comprehensive_same_run_locale_report_v1 import _localized_draft_view


def _report(locale, *, empty=False):
    canonical = {
        "report_language": locale,
        "identity": {"run_id": "synthetic-locale-run", "repository": "owned/control",
                     "commit_sha": "a" * 40, "evidence_ledger_id": "synthetic-ledger"},
        "assessment": {"maturity_signal": {"score": 71}},
        "canonical_findings": [] if empty else [{
            "finding_id": "F-1", "severity": "medium", "disposition": "unconfirmed",
            "recommendation": "Preserve this literal: Obtener el insumo faltante.",
            "verification": ["Retain the exact-source test."],
        }],
        "review_candidate_summary": {} if empty else {"review_required_total": 2},
        "stage_summaries": [{"stage_id": stage, "evidence": ["constraints: literal client input"]}
                            for stage in ("six_month_roadmap", "staffing_sequencing_and_cost",
                                          "risk_reduction_and_executive_briefing")],
    }
    stages = {} if empty else {"functional_qa": {"missing_evidence": [{
        "evidence_type": "runtime_functional_qa", "state": "not_supplied",
        "evidence_to_resolve": "Authorized objectives, constraints, success measures, decision owners, and authority records.",
        "why_it_matters": "Technical evidence cannot establish stakeholder intent or business authority.",
    }]}}
    output = bind_final_finding_roadmap(canonical, raw_stages=stages)
    output["assessment"]["stage_summaries"] = deepcopy(output["stage_summaries"])
    return output


@pytest.mark.parametrize("source,target", [("es-MX", "en"), ("en", "es-MX")])
@pytest.mark.parametrize("empty", [False, True])
def test_locale_draft_matches_native_generated_prose_without_rebuilding_population(source, target, empty):
    canonical = _report(source, empty=empty)
    before = deepcopy(canonical)
    native = _report(target, empty=empty)
    localized = _localized_draft_view(canonical, target)
    for container in (localized, localized["assessment"]):
        assert container["roadmap"] == native["roadmap"]
        assert container["roadmap_truth"] == before["roadmap_truth"]
        assert container["stage_summaries"] == native["stage_summaries"]
    assert canonical == before
    assert localized["canonical_findings"] == before["canonical_findings"]
    assert localized["assessment"]["maturity_signal"] == before["assessment"]["maturity_signal"]
    assert localized["approval_status"] == "pending_human_approval"
    assert localized["client_delivery_allowed"] is False
    assert _localized_draft_view(localized, target) == localized


@pytest.mark.parametrize("source,target", [(False, True), (True, False)])
def test_retained_human_stage_localizes_wrappers_without_changing_supplied_values(source, target):
    literal = "Dato aportado por el cliente · Objetivos:   Client text: Sí / Yes"
    snapshot = {"human_evidence": {"provided_module_ids": ["functional_qa", "stakeholder_context"],
        "modules": {
            "functional_qa": {"label": "Functional QA", "status": "partial",
                              "evidence": {"test_cases": literal}, "reviewer": literal},
            "stakeholder_context": {"label": "Stakeholder context", "status": "partial",
                                    "missing_fields": ["objectives", "constraints"],
                                    "evidence": {"repository_identity": literal}},
        }}}
    retained = _human_module_stage_specs(snapshot, spanish=source)
    before = deepcopy(retained)
    native = _human_module_stage_specs(snapshot, spanish=target)
    assert [_localize_retained_stage(s, spanish=target) for s in retained] == native
    assert retained == before
    assert all(literal in "\n".join(s["evidence"]) for s in native)


@pytest.mark.parametrize("source,target", [(False, True), (True, False)])
def test_retained_client_summary_missing_fields_keep_unknown_and_localize_labels(source, target):
    retained = _client_summary_stage({}, spanish=source)
    # Without a retained absence classification, even a placeholder-looking
    # client value is literal. Only its wrapper is known to be NICO's copy.
    expected = _client_summary_stage({}, spanish=target)
    for index, line in enumerate(expected["evidence"]):
        expected["evidence"][index] = line.partition(": ")[0] + ": " + retained["evidence"][index].partition(": ")[2]
    assert _localize_retained_stage(retained, spanish=target) == expected


@pytest.mark.parametrize("source,target", [(False, True), (True, False)])
def test_explicit_absence_classification_allows_generated_placeholder_translation(source, target):
    retained = _client_summary_stage({}, spanish=source)
    native = _client_summary_stage({}, spanish=target)
    retained["unavailable"] = [line.partition(" · ")[2] for line in retained["evidence"]]
    native["unavailable"] = [line.partition(" · ")[2] for line in native["evidence"]]
    assert _localize_retained_stage(retained, spanish=target) == native


def test_locale_projection_does_not_rewrite_unknown_or_client_prose():
    canonical = _report("es-MX")
    custom = "Dato aportado por el cliente · Objetivos: keep this literal"
    canonical["roadmap"][0]["action"] = custom
    canonical["assessment"]["roadmap"][0]["action"] = custom
    for container in (canonical, canonical["assessment"]):
        container["stage_summaries"][0]["evidence"].append(custom)
    result = _localized_draft_view(canonical, "en")
    assert result["roadmap"][0]["action"] == custom
    assert result["assessment"]["roadmap"][0]["action"] == custom
    assert result["stage_summaries"][0]["evidence"][-1] == custom


def test_locale_projection_cannot_rebind_foreign_roadmap():
    canonical = _report("es-MX")
    canonical["identity"]["run_id"] = "another-run"
    result = _localized_draft_view(canonical, "en")
    assert result["roadmap"] == canonical["roadmap"]
    assert result["stage_summaries"] == canonical["stage_summaries"]


def test_english_retained_finding_does_not_require_a_spanish_translation():
    canonical = _report("en")
    literal = "The retained gizmo must remain unchanged while the operator reviews it."
    canonical["canonical_findings"][0]["recommendation"] = literal
    canonical = bind_final_finding_roadmap(canonical, raw_stages={})
    before = deepcopy(canonical)
    localized = _localized_draft_view(canonical, "en")
    assert localized["roadmap"] == before["roadmap"]
    assert localized["stage_summaries"] == before["stage_summaries"]
    assert literal in "\n".join(localized["stage_summaries"][0]["evidence"])
    assert canonical == before


def test_locale_draft_localizes_human_wrappers_before_downstream_stage_restoration():
    canonical = _report("es-MX")
    stage = _client_summary_stage({"display_values": {"customer_name": "Keep  this: literal"}}, spanish=True)
    for container in (canonical, canonical["assessment"]):
        container["stage_summaries"].append(deepcopy(stage))
    before = deepcopy(canonical)
    localized = _localized_draft_view(canonical, "en")
    for container in (localized, localized["assessment"]):
        line = container["stage_summaries"][-1]["evidence"][0]
        assert line == "Client-supplied data · Client display name: Keep  this: literal"
    assert canonical == before
