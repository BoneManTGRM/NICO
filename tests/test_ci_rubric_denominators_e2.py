from __future__ import annotations

import base64
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader

from nico import comprehensive_native_providers_v3 as scoring
from nico import comprehensive_rendered_ci_boundary_producer_v79 as renderer
from nico.comprehensive_ci_operational_truth_v71 import ci_cd_boundary_lines
from nico.provider_control_objective_parity_v1 import install_provider_control_objective_parity
from tests.test_comprehensive_rendered_ci_boundary_producer_v79 import _package


def _workflow() -> dict:
    return {
        "workflow_file_count": 1,
        "workflow_configuration_snapshot_sha": "a" * 40,
        "explicit_permissions_present": True,
        "configuration_controls": {key: True for key in scoring._IMMUTABLE_CONTROL_FIELDS},
    }


def _canonical(workflow: dict, language: str) -> dict:
    install_provider_control_objective_parity()
    score, evidence, findings, contract = scoring._immutable_ci_score(workflow, "a" * 40)
    return {
        "report_language": language,
        "identity": {"report_language": language, "run_id": "comprun_e2", "repository": "fixture/authorized", "commit_sha": "a" * 40},
        "assessment": {"sections": [{"id": "ci_cd", "label": "CI/CD Analysis", "presented_score": score, "score_contract": contract, "evidence": evidence, "findings": findings}]},
    }


def test_actual_installed_scorer_does_not_award_empty_evidence_full_maturity() -> None:
    canonical = _canonical({}, "en")
    section = canonical["assessment"]["sections"][0]
    assert section["presented_score"] is None
    assert section["score_contract"]["control_objective_coverage_percent"] == 0
    assert section["score_contract"]["evaluated_control_count"] == 0
    assert section["score_contract"]["control_population"] == 14


def test_retained_rubric_reproduces_existing_score_and_coverage() -> None:
    workflow = _workflow()
    workflow["explicit_permissions_present"] = False
    canonical = _canonical(workflow, "en")
    section = canonical["assessment"]["sections"][0]
    contract = section["score_contract"]
    assert section["presented_score"] == 90
    assert contract["control_objective_coverage_percent"] == 100
    assert contract["evaluated_control_count"] == 14
    assert contract["passed_control_count"] == 13
    rubric = contract["rubric"]
    assert rubric["baseline_weight"] == 45
    assert rubric["passed_objective_weight"] == pytest.approx(45)
    assert rubric["assessed_objective_weight"] == pytest.approx(55)
    assert round(100 * rubric["score_numerator"] / rubric["score_denominator"]) == section["presented_score"]
    assert sum(row["weight"] for row in rubric["objectives"]) == pytest.approx(55)
    assert contract["excluded_control_objectives"] == []


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_actual_rendered_boundary_uses_objectives_not_empty_legacy_vector(language: str) -> None:
    canonical = _canonical(_workflow(), language)
    before = deepcopy(canonical)
    spanish = language == "es-MX"
    result = renderer.repair_rendered_ci_boundary(_package(canonical=canonical, spanish=spanish))
    pdf = base64.b64decode(result["pdf_base64"])
    surfaces = [result["markdown"], result["html"], " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)]
    for text in surfaces:
        assert "14/14" in text
        assert "0/0" not in text
        assert "100*(45+55)/(45+55)" in text
        assert "nico.ci-rubric.v1" in text
    assert canonical == before


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_missing_contract_is_unmeasured_not_inapplicable(language: str) -> None:
    canonical = {"assessment": {"sections": [{"id": "ci_cd", "presented_score": 100}]}}
    line = ci_cd_boundary_lines(canonical, spanish=language == "es-MX")[0]
    assert "0/0" not in line
    assert ("not measured" if language == "en" else "sin medición") in line


def test_reordering_and_mutable_history_do_not_change_rubric_or_maturity() -> None:
    first = _canonical(_workflow(), "en")["assessment"]["sections"][0]
    workflow = dict(reversed(list(_workflow().items())))
    workflow["configuration_controls"] = dict(reversed(list(workflow["configuration_controls"].items())))
    workflow.update(successful_runs=1, non_success_runs=99)
    second = _canonical(workflow, "en")["assessment"]["sections"][0]
    assert first["presented_score"] == second["presented_score"]
    assert first["score_contract"]["rubric"] == second["score_contract"]["rubric"]
    assert first["score_contract"]["operational_trend"] != second["score_contract"]["operational_trend"]


@pytest.mark.parametrize("language", ["en", "es-MX"])
def test_actual_v5_unmeasured_ci_reaches_canonical_publication(monkeypatch, language: str) -> None:
    from nico import comprehensive_native_providers as legacy
    from nico import comprehensive_native_providers_v5 as v5
    from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
    from tests.test_comprehensive_native_providers_v4 import _context, _repo, _scan

    install_provider_control_objective_parity()
    repo = _repo()
    repo["workflow_evidence"] = {}
    monkeypatch.setattr(legacy, "_repo", lambda context: repo)
    monkeypatch.setattr(legacy, "_scan", lambda context: _scan())
    monkeypatch.setattr(legacy, "_complexity", lambda context: {"complexity_score": 78, "files_analyzed": 795, "risk_level": "moderate"})
    scoring_result = v5.canonical_scoring_provider(_context())
    context = _context()
    context["report_language"] = language
    context["prior_stage_results"] = {"evidence_reconciliation_and_scoring": scoring_result}
    result = build_canonical_report_source(context)
    assert result["status"] == "complete"
    sections = {row["id"]: row for row in result["canonical_report"]["assessment"]["sections"]}
    for section_id in ("ci_cd", "velocity_complexity"):
        assert sections[section_id]["presented_score"] is None
        assert sections[section_id]["exclude_from_maturity"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
