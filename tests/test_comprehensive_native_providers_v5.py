from __future__ import annotations

from copy import deepcopy

from nico import comprehensive_native_providers as legacy
from nico import comprehensive_native_providers_v4 as v4
from nico import comprehensive_native_providers_v5 as scoring


COMMIT = "a" * 40
TOOLS = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)


def _context() -> dict:
    return {
        "run_id": "comprun_candidate_truth_v5",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "evidence_ledger_id": "ledger_candidate_truth_v5",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": {},
    }


def _baseline(technical: int = 93) -> dict:
    sections = [
        {"id": "code_audit", "presented_score": 96, "score": 96},
        {"id": "dependency_health", "presented_score": 96, "score": 96},
        {"id": "secrets_review", "presented_score": 96, "score": 96},
        {"id": "static_analysis", "presented_score": 96, "score": 96},
        {"id": "ci_cd", "presented_score": 100, "score": 100},
        {"id": "architecture_debt", "presented_score": 78, "score": 78},
        {"id": "velocity_complexity", "presented_score": 87, "score": 87},
    ]
    return {
        "status": "complete",
        "assessment": {
            "technical_score": technical,
            "canonical_technical_score": technical,
            "canonical_evidence_adjusted_score": 90,
            "evidence_adjusted_score": 90,
            "maturity_signal": {
                "score": technical,
                "technical_score": technical,
                "canonical_evidence_adjusted_score": 90,
                "evidence_adjusted_score": 90,
                "evidence_readiness_score": 90,
            },
            "evidence_coverage": {
                "percent": 100,
                "incomplete_analyzers": [],
            },
            "score_contract": {
                "technical_score": technical,
                "evidence_adjusted_score": 90,
                "incomplete_analyzers": [],
            },
            "sections": sections,
        },
        "evidence": {
            "technical_score": technical,
            "evidence_adjusted_score": 90,
        },
    }


def _summary() -> dict:
    return {
        tool: {
            "raw": 0,
            "material": 0,
            "review_required": 0,
            "approved_or_nonblocking": 0,
            "excluded_test_only": 0,
        }
        for tool in TOOLS
    }


def _result(tool: str, category: str, findings: list[dict]) -> dict:
    return {
        "tool": tool,
        "scanner_name": tool,
        "category": category,
        "status": "completed_with_findings" if findings else "completed",
        "completed": True,
        "verified": True,
        "exact_commit_match": True,
        "raw_artifact_retention_complete": True,
        "findings": findings,
    }


def _scan(*, static_review: int = 581, include_payload: bool = False) -> dict:
    by_tool = _summary()
    by_tool["osv-scanner"].update({"raw": 59, "review_required": 59})
    by_tool["gitleaks"].update({"raw": 6, "review_required": 6})
    by_tool["trufflehog"].update({"raw": 11, "review_required": 11})
    by_tool["semgrep"].update({"raw": static_review, "review_required": static_review})

    findings = []
    if include_payload:
        findings = [
            {
                "check_id": f"typescript.rule.{index}",
                "path": f"src/module_{index}.ts",
                "start": {"line": index + 1, "col": 1},
                "extra": {"message": f"Review candidate {index}", "severity": "INFO"},
            }
            for index in range(static_review)
        ]
    results = [
        _result(tool, (
            "dependency" if tool in {"pip-audit", "npm-audit", "osv-scanner"}
            else "secret" if tool in {"gitleaks", "trufflehog"}
            else "static"
        ), findings if tool == "semgrep" else [])
        for tool in TOOLS
    ]
    return {
        "status": "complete",
        "scanner_results": results,
        "finding_summary": {"by_tool": by_tool},
        "unavailable_data_notes": [],
    }


def _repo() -> dict:
    return {
        "workflow_evidence": {
            "successful_runs": 74,
            "non_success_runs": 9,
        }
    }


def test_canonical_register_normalizes_exact_source_and_deduplicates() -> None:
    finding = {
        "check_id": "typescript.react.rule",
        "path": "apps/web/app/page.tsx",
        "start": {"line": 44, "col": 7},
        "extra": {"message": "Candidate needs review", "severity": "INFO"},
    }
    summary = _summary()
    summary["semgrep"].update({"raw": 2, "review_required": 2})
    scan = {
        "scanner_results": [_result("semgrep", "static", [finding, deepcopy(finding)])],
        "finding_summary": {"by_tool": summary},
    }

    register = scoring.build_canonical_scanner_finding_register(scan, COMMIT)

    assert register["status"] == "complete"
    assert register["count_parity_verified"] is True
    assert register["totals"]["raw"] == 2
    assert len(register["findings"]) == 1
    record = register["findings"][0]
    assert record["source_path"] == "apps/web/app/page.tsx"
    assert record["line"] == 44
    assert record["occurrence_count"] == 2
    assert record["source_record_count"] == 2
    assert record["finding_id"].startswith("NICO-SCAN-")


def test_missing_raw_payload_is_explicit_count_only_evidence() -> None:
    register = scoring.build_canonical_scanner_finding_register(
        _scan(static_review=581, include_payload=False),
        COMMIT,
    )

    assert register["status"] == "complete"
    assert register["totals"]["raw"] == 657
    assert register["totals"]["review_required"] == 657
    assert register["totals"]["count_only"] == 657
    assert register["raw_payload_retention_complete"] is False


def test_candidate_volume_changes_evidence_adjusted_not_technical_score(monkeypatch) -> None:
    monkeypatch.setattr(v4, "canonical_scoring_provider", lambda context: _baseline())
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())

    small = _scan(static_review=1, include_payload=True)
    large = _scan(static_review=581, include_payload=True)

    monkeypatch.setattr(legacy, "_scan", lambda context: small)
    small_result = scoring.canonical_scoring_provider(_context())

    monkeypatch.setattr(legacy, "_scan", lambda context: large)
    large_result = scoring.canonical_scoring_provider(_context())

    small_assessment = small_result["assessment"]
    large_assessment = large_result["assessment"]

    assert small_assessment["technical_score"] == 93
    assert large_assessment["technical_score"] == 93
    assert large_assessment["evidence_adjusted_score"] < small_assessment["evidence_adjusted_score"]
    assert large_assessment["evidence_adjusted_score"] < 90
    assert large_assessment["score_contract"]["candidate_volume_affects_technical_score"] is False
    assert large_assessment["score_contract"]["candidate_volume_affects_evidence_adjusted_score"] is True
    assert large_assessment["canonical_scanner_finding_register"]["totals"]["raw"] == 657


def test_removing_candidates_improves_readiness_on_same_commit(monkeypatch) -> None:
    monkeypatch.setattr(v4, "canonical_scoring_provider", lambda context: _baseline())
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())

    before = _scan(static_review=581, include_payload=True)
    after = _scan(static_review=0, include_payload=True)

    monkeypatch.setattr(legacy, "_scan", lambda context: before)
    before_score = scoring.canonical_scoring_provider(_context())["assessment"]["evidence_adjusted_score"]

    monkeypatch.setattr(legacy, "_scan", lambda context: after)
    after_score = scoring.canonical_scoring_provider(_context())["assessment"]["evidence_adjusted_score"]

    assert after_score > before_score
    assert after_score <= 93


def test_ci_configuration_and_operational_health_are_separate(monkeypatch) -> None:
    monkeypatch.setattr(v4, "canonical_scoring_provider", lambda context: _baseline())
    monkeypatch.setattr(legacy, "_scan", lambda context: _scan(static_review=1, include_payload=True))
    monkeypatch.setattr(legacy, "_repo", lambda context: _repo())

    assessment = scoring.canonical_scoring_provider(_context())["assessment"]
    ci = next(item for item in assessment["sections"] if item["id"] == "ci_cd")

    assert ci["configuration_maturity_score"] == 100
    assert ci["operational_health"]["score"] == 89
    assert ci["operational_health"]["score_effect"] == "operational_context_only"
    assert assessment["ci_cd_operational_health"]["technical_configuration_score_affected"] is False


def test_scanner_triage_exposes_count_reconciled_register(monkeypatch) -> None:
    monkeypatch.setattr(legacy, "_scan", lambda context: _scan(static_review=3, include_payload=True))

    result = scoring.scanner_triage_provider(_context())
    register = result["scanner_triage"]["canonical_scanner_finding_register"]

    assert result["status"] == "complete"
    assert result["evidence"]["count_parity_verified"] is True
    assert result["evidence"]["canonical_finding_count"] == 79
    assert register["totals"]["review_required"] == 79
