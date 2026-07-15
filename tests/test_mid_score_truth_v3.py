from __future__ import annotations

from copy import deepcopy

import nico.full_assessment_scorecard as scorecard
import nico.mid_score_truth_v3 as v3


def _section(section_id: str, score: int, *, unavailable: list[str] | None = None) -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": "green" if score >= 80 else "yellow",
        "summary": f"{section_id} summary",
        "evidence": [f"{section_id} evidence"],
        "findings": [],
        "unavailable": unavailable or [],
    }


def test_final_triage_replaces_raw_match_caps_and_recomputes_weighted_score(monkeypatch) -> None:
    def dependency(_repo: dict, _scanner: dict) -> dict:
        value = _section("dependency_health", 86)
        value["dependency_scanner_triage"] = {
            "material_finding_count": 0,
            "review_finding_count": 4,
            "structured_scanners_completed": 3,
        }
        return value

    def secrets(_repo: dict, _scanner: dict) -> dict:
        value = _section("secrets_review", 88)
        value["secret_history_triage"] = {
            "history_scanners_completed": 2,
            "material_finding_count": 0,
        }
        return value

    def static(_repo: dict, _scanner: dict) -> dict:
        value = _section("static_analysis", 84)
        value["static_triage"] = {
            "structured_analyzers_completed": 2,
            "material_finding_count": 0,
            "review_finding_count": 8,
        }
        return value

    monkeypatch.setattr(scorecard, "_dependency_section", dependency)
    monkeypatch.setattr(scorecard, "_secrets_section", secrets)
    monkeypatch.setattr(scorecard, "_static_section", static)

    raw_assessment = {
        "run_id": "midrun_test",
        "repository": "owner/repo",
        "maturity_signal": {"score": 75, "level": "Mid"},
        "sections": [
            _section("code_audit", 80),
            _section("dependency_health", 55),
            _section("secrets_review", 62),
            _section("static_analysis", 64),
            _section("ci_cd", 95),
            _section("architecture_debt", 85, unavailable=["Call-graph, coupling, duplication, and cyclomatic-complexity conclusions require language-specific analyzer output."]),
            _section("velocity_complexity", 76),
        ],
    }

    def original(_context: dict, _outputs: dict) -> dict:
        return {"status": "complete", "assessment": deepcopy(raw_assessment), "evidence": {}}

    outputs = {
        "repo_evidence": {
            "repository_evidence": {"status": "attached"},
            "complexity_evidence": {
                "status": "attached",
                "files_analyzed": 59,
                "total_source_loc": 7482,
                "functions_measured": 296,
                "maximum_cyclomatic_complexity": 95,
            },
        },
        "scanner_worker": {
            "scan": {
                "status": "complete",
                "scanner_results": [
                    {"scanner": "pip-audit", "execution_completed": True, "material_finding_count": 0},
                    {"scanner": "npm-audit", "execution_completed": True, "material_finding_count": 0},
                    {"scanner": "osv-scanner", "execution_completed": True, "material_finding_count": 0, "review_finding_count": 4},
                    {"scanner": "gitleaks", "execution_completed": True, "full_history_covered": True, "material_finding_count": 0},
                    {"scanner": "trufflehog", "execution_completed": True, "full_history_covered": True, "material_finding_count": 0},
                    {"scanner": "bandit", "execution_completed": True, "material_finding_count": 0, "review_finding_count": 8},
                    {"scanner": "semgrep", "execution_completed": True, "material_finding_count": 0, "review_finding_count": 0},
                ],
            }
        },
        "evidence_attachment": {"scanner_evidence": {"status": "attached", "scanner_results": []}},
    }

    result = v3.reconcile_mid_scoring({}, outputs, original)
    assessment = result["assessment"]
    sections = {item["id"]: item for item in assessment["sections"]}

    assert sections["dependency_health"]["score"] == 86
    assert sections["secrets_review"]["score"] == 88
    assert sections["static_analysis"]["score"] == 84
    assert sections["architecture_debt"]["score"] == 88
    assert not sections["architecture_debt"]["unavailable"]
    assert assessment["maturity_signal"]["score"] > 75
    assert assessment["mid_score_explanation"]["target_score_hardcoded"] is False
    assert assessment["mid_score_explanation"]["weights_changed"] is False
    assert result["evidence"]["mid_final_score_reconciliation"]["raw_scanner_finding_caps_carried_forward"] is False


def test_material_final_triage_remains_a_score_constraint(monkeypatch) -> None:
    def dependency(_repo: dict, _scanner: dict) -> dict:
        value = _section("dependency_health", 55)
        value["dependency_scanner_triage"] = {
            "material_finding_count": 2,
            "review_finding_count": 3,
            "structured_scanners_completed": 3,
        }
        value["findings"] = ["Remediate 2 corroborated dependency vulnerability records before approval."]
        return value

    monkeypatch.setattr(scorecard, "_dependency_section", dependency)
    monkeypatch.setattr(scorecard, "_secrets_section", lambda _repo, _scanner: _section("secrets_review", 88))
    monkeypatch.setattr(scorecard, "_static_section", lambda _repo, _scanner: _section("static_analysis", 88))

    assessment = {
        "run_id": "midrun_material",
        "maturity_signal": {"score": 80},
        "sections": [
            _section("code_audit", 80),
            _section("dependency_health", 55),
            _section("secrets_review", 88),
            _section("static_analysis", 88),
            _section("ci_cd", 95),
            _section("architecture_debt", 85),
            _section("velocity_complexity", 76),
        ],
    }
    outputs = {
        "repo_evidence": {"repository_evidence": {"status": "attached"}},
        "scanner_worker": {"scan": {"status": "complete", "scanner_results": []}},
        "evidence_attachment": {"scanner_evidence": {"status": "attached", "scanner_results": []}},
    }
    result = v3.reconcile_mid_scoring({}, outputs, lambda _c, _o: {"status": "complete", "assessment": assessment})

    constraints = result["assessment"]["mid_score_explanation"]["primary_score_constraints"]
    assert "Dependency: 2 corroborated material record(s)." in constraints
    assert next(item for item in result["assessment"]["sections"] if item["id"] == "dependency_health")["score"] == 55


def test_generic_scope_disclosure_is_presented_separately_without_identity_change() -> None:
    original_truth = v3._ORIGINAL_BUILD_TRUTH
    try:
        v3._ORIGINAL_BUILD_TRUTH = lambda _result: {
            "version": "mid-truth-status-v1",
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code Audit",
                    "truth_status": "Verified with limitations",
                    "score": 80,
                    "direct_repository_proof": True,
                    "evidence": ["Exact snapshot evidence attached."],
                    "unavailable": ["This score does not replace line-by-line semantic code review."],
                    "missing_evidence_sources": [],
                    "failed_evidence_tools": [],
                }
            ],
            "evidence_coverage": {
                "units": [{"id": "evidence_ledger", "available": False, "status": "Unavailable"}],
            },
            "summary": {},
        }
        truth = v3.build_mid_truth_status_v3(
            {
                "assessment": {
                    "evidence_artifact_bundle": {
                        "evidence_ledger": {"entry_count": 42, "entries": [{"id": "one"}]}
                    }
                }
            }
        )
    finally:
        v3._ORIGINAL_BUILD_TRUTH = original_truth

    section = truth["sections"][0]
    coverage = truth["evidence_coverage"]
    assert truth["version"] == "mid-truth-status-v1"
    assert section["truth_status"] == "Verified with limitations"
    assert section["presentation_truth_status"] == "Verified"
    assert section["scope_disclosures"] == ["This score does not replace line-by-line semantic code review."]
    assert coverage["presentation_units"][0]["available"] is True
    assert coverage["presentation_percent"] == 100


def test_review_packet_consolidates_for_display_without_mutating_source_identity() -> None:
    packet = {
        "status": "ready_for_review",
        "packet_version": "mid-review-by-exception-v1",
        "review_packet_id": "packet_one",
        "review_packet_sha256": "abc123",
        "exceptions": [
            {
                "item_id": "one",
                "category": "low_confidence_or_limited_conclusion",
                "section_id": "static_analysis",
                "title": "Limited conclusion in Static Analysis",
                "reason": "Limited.",
                "severity": "medium",
                "evidence": ["evidence one"],
                "blockers": ["blocker one"],
                "score_change_material": True,
            },
            {
                "item_id": "two",
                "category": "score_changing_claim",
                "section_id": "static_analysis",
                "title": "Score-affecting claim in Static Analysis",
                "reason": "Score claim.",
                "severity": "medium",
                "evidence": ["evidence two"],
                "blockers": ["blocker two"],
                "score_change_material": True,
            },
        ],
        "summary": {"items_requiring_review": 2},
    }

    consolidated = v3._consolidate_review_packet(packet)

    assert consolidated["packet_version"] == "mid-review-by-exception-v1"
    assert consolidated["review_packet_id"] == "packet_one"
    assert consolidated["review_packet_sha256"] == "abc123"
    assert len(consolidated["exceptions"]) == 2
    assert len(consolidated["display_exceptions"]) == 1
    item = consolidated["display_exceptions"][0]
    assert item["categories"] == ["low_confidence_or_limited_conclusion", "score_changing_claim"]
    assert item["blockers"] == ["blocker one", "blocker two"]
    assert item["source_item_ids"] == ["one", "two"]
    assert consolidated["display_summary"]["consolidated_duplicate_items_removed"] == 1
