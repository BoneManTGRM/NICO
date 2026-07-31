from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from nico import comprehensive_assessment_hardening_v1 as hardening
from nico.comprehensive_native_providers_v3 import (
    HARDENING_STATUS,
    _immutable_ci_score,
    _immutable_delivery_score,
)


def test_blocked_report_contract_cannot_publish_complete() -> None:
    result = {
        "status": "complete",
        "reason": "",
        "assessment": {
            "report_contract_status": "blocked",
            "report_contract_reason": "canonical_score_truth_mismatch",
        },
        "stage_summaries": [],
        "report_package": {
            "report_quality_contract": {},
            "client_delivery_allowed": False,
        },
    }

    hardened = hardening.enforce_report_contract_gate(result)

    assert hardened["status"] == "blocked"
    assert hardened["reason"] == (
        "report_contract_blocked:canonical_score_truth_mismatch"
    )
    assert hardened["report_quality_contract"]["report_contracts_clear"] is False
    assert hardened["report_quality_contract"]["report_contract_blocked_count"] == 1
    assert hardened["report_package"]["publication_allowed"] is False
    assert hardened["report_package"]["complete"] is False
    assert hardened["client_delivery_allowed"] is False


def test_clear_report_contract_preserves_complete_status() -> None:
    result = {
        "status": "complete",
        "assessment": {"report_contract_status": "reconciled"},
        "stage_summaries": [],
        "report_package": {},
    }

    hardened = hardening.enforce_report_contract_gate(result)

    assert hardened["status"] == "complete"
    assert hardened["report_quality_contract"]["report_contracts_clear"] is True
    assert hardened["report_package"]["publication_allowed"] is True


def _score_contract_fixture(*, mismatch: bool) -> dict:
    technical = 90
    maturity = 89 if mismatch else technical
    return {
        "assessment": {
            "technical_score": technical,
            "canonical_evidence_adjusted_score": 88,
            "evidence_adjusted_score": 88,
            "final_report_input_scores_synchronized": True,
            "report_contract_status": "blocked",
            "report_contract_reason": "canonical_score_truth_mismatch",
            "maturity_signal": {
                "score": maturity,
                "source_score": technical,
                "presented_score": technical,
                "technical_score": technical,
                "canonical_evidence_adjusted_score": 88,
                "evidence_adjusted_score": 88,
            },
            "score_contract": {
                "technical_score": technical,
                "evidence_adjusted_score": 88,
            },
            "sections": [
                {
                    "id": "code_audit",
                    "score": 91,
                    "presented_score": 91,
                    "score_value": 91,
                }
            ],
        },
        "stage_summaries": [
            {
                "stage_id": "decision_report_generation",
                "report_contract_status": "blocked",
                "report_contract_reason": "canonical_score_truth_mismatch",
            }
        ],
    }


def test_score_contract_reconciles_only_after_value_equality() -> None:
    canonical = _score_contract_fixture(mismatch=False)

    repaired = hardening._repair_stale_report_contracts_hardened(canonical)

    assert repaired == 2
    assert canonical["assessment"]["report_contract_status"] == "reconciled"
    assert canonical["stage_summaries"][0]["report_contract_status"] == "reconciled"
    assert canonical["score_truth_consistency"]["consistent"] is True


def test_score_contract_mismatch_remains_blocked() -> None:
    canonical = _score_contract_fixture(mismatch=True)

    repaired = hardening._repair_stale_report_contracts_hardened(canonical)

    assert repaired == 0
    assert canonical["assessment"]["report_contract_status"] == "blocked"
    assert canonical["stage_summaries"][0]["report_contract_status"] == "blocked"
    assert canonical["score_truth_consistency"]["consistent"] is False


def _candidate(
    identifier: str,
    *,
    category: str,
    scanner: str,
    material: bool = False,
) -> dict:
    return {
        "finding_id": identifier,
        "id": identifier,
        "priority": "P1" if material else "P2",
        "category": category,
        "scanner_name": scanner,
        "status": "open" if material else "review_required",
        "title": (
            "Confirmed material finding"
            if material
            else f"{category.title()} candidate requires review"
        ),
        "location": f"{category}/{identifier}.txt:1",
        "evidence": "verified=true" if material else "verified=false",
        "fact": "verified exact evidence" if material else "unverified candidate",
        "interpretation": "review",
        "business_impact": "bounded impact",
        "recommendation": "review exact evidence",
        "confidence": "high" if material else "moderate",
        "material": material,
        "review_required": not material,
        "acceptance_criteria": ["Record a binary disposition."],
    }


def test_candidate_volume_is_grouped_without_hiding_raw_records() -> None:
    dependency = [
        _candidate(
            f"DEP-{index}",
            category="dependency",
            scanner="osv-scanner",
        )
        for index in range(59)
    ]
    secrets = [
        _candidate(
            f"SECRET-{index}",
            category="secret",
            scanner="trufflehog",
        )
        for index in range(36)
    ]
    material = _candidate(
        "MATERIAL-1",
        category="dependency",
        scanner="pip-audit",
        material=True,
    )

    compressed = hardening.compress_review_candidates(
        {"findings_register": [*dependency, *secrets, material]}
    )

    assert len(compressed["review_candidate_evidence_register"]) == 95
    assert compressed["candidate_presentation_summary"][
        "raw_review_candidate_count"
    ] == 95
    assert compressed["candidate_presentation_summary"][
        "client_candidate_group_count"
    ] == 2
    assert compressed["candidate_presentation_summary"][
        "individual_candidate_remediation_pages_suppressed"
    ] == 93
    assert len(compressed["findings_register"]) == 3
    assert any(
        item.get("finding_id") == "MATERIAL-1"
        for item in compressed["findings_register"]
    )
    groups = [
        item
        for item in compressed["findings_register"]
        if item.get("grouped_review_candidate") is True
    ]
    assert sorted(item["candidate_count"] for item in groups) == [36, 59]
    assert all(item["technical_score_impact"] == "assurance_only" for item in groups)


def test_confirmed_p2_record_is_not_hidden_by_candidate_grouping() -> None:
    confirmed = {
        "finding_id": "STATIC-CONFIRMED-1",
        "id": "STATIC-CONFIRMED-1",
        "priority": "P2",
        "category": "static",
        "status": "open",
        "title": "Confirmed input-validation defect",
        "evidence": "verified exact source finding",
        "fact": "The exact source branch is reachable and verified.",
        "confidence": "moderate",
        "material": False,
        "review_required": False,
    }

    compressed = hardening.compress_review_candidates(
        {"findings_register": [confirmed]}
    )

    assert compressed["findings_register"] == [confirmed]
    assert compressed["candidate_presentation_summary"][
        "raw_review_candidate_count"
    ] == 0
    assert compressed["candidate_presentation_summary"][
        "client_candidate_group_count"
    ] == 0


def test_authoritative_manifest_filter_excludes_non_production_trees(
    tmp_path: Path,
) -> None:
    (tmp_path / "requirements.txt").write_text(
        "requests==2.34.2\n",
        encoding="utf-8",
    )
    web = tmp_path / "apps" / "web"
    web.mkdir(parents=True)
    (web / "package.json").write_text("{}\n", encoding="utf-8")
    (web / "package-lock.json").write_text("{}\n", encoding="utf-8")

    for directory in (
        tmp_path / "tests" / "fixtures",
        tmp_path / "examples",
        tmp_path / "docs",
        tmp_path / ".github",
        tmp_path / "audit-results",
    ):
        directory.mkdir(parents=True)
        (directory / "requirements.txt").write_text(
            "Pillow==1.0\n",
            encoding="utf-8",
        )

    manifests = hardening._strict_authoritative_manifests(tmp_path)

    assert manifests == {"requirements.txt", "apps/web/package-lock.json"}


class _FakeGitHubClient:
    def repo_url(self, repository: str, path: str) -> str:
        return f"https://api.github.test/repos/{repository}{path}"

    def get_json(self, url: str, params: dict | None = None):
        if url.endswith("/actions/runs/1/jobs"):
            return {
                "jobs": [
                    {
                        "id": 11,
                        "name": "complete-before-cutoff",
                        "conclusion": "success",
                        "started_at": "2026-07-31T12:00:00Z",
                        "completed_at": "2026-07-31T12:05:00Z",
                    },
                    {
                        "id": 12,
                        "name": "fails-after-cutoff",
                        "conclusion": "failure",
                        "started_at": "2026-07-31T12:10:00Z",
                        "completed_at": "2026-07-31T13:10:00Z",
                    },
                    {
                        "id": 13,
                        "name": "starts-after-cutoff",
                        "conclusion": "success",
                        "started_at": "2026-07-31T13:05:00Z",
                        "completed_at": "2026-07-31T13:06:00Z",
                    },
                ]
            }, None
        if url.endswith("/deployments"):
            return [
                {
                    "id": 21,
                    "environment": "production",
                    "ref": "a" * 40,
                    "created_at": "2026-07-31T11:00:00Z",
                },
                {
                    "id": 22,
                    "environment": "production",
                    "ref": "b" * 40,
                    "created_at": "2026-07-31T14:00:00Z",
                },
            ], None
        if url.endswith("/deployments/21/statuses"):
            return [
                {
                    "state": "failure",
                    "created_at": "2026-07-31T13:30:00Z",
                },
                {
                    "state": "success",
                    "created_at": "2026-07-31T12:20:00Z",
                },
            ], None
        raise AssertionError(url)


def test_operational_evidence_is_reconstructed_at_capture_time() -> None:
    captured_at = datetime(2026, 7, 31, 13, 0, tzinfo=timezone.utc)
    token = hardening._CAPTURED_AT.set(captured_at)
    try:
        result = hardening._collect_ci_runtime_evidence_frozen(
            _FakeGitHubClient(),
            "example/repository",
            {
                ".github/workflows/ci.yml": (
                    "permissions:\n  contents: read\njobs:\n  test:\n"
                    "    timeout-minutes: 10\n    steps:\n"
                    "      - run: pytest\n"
                )
            },
            [
                {
                    "id": 1,
                    "name": "Production Acceptance",
                    "head_sha": "a" * 40,
                    "created_at": "2026-07-31T11:55:00Z",
                }
            ],
        )
    finally:
        hardening._CAPTURED_AT.reset(token)

    jobs = result["job_evidence"]
    assert jobs["jobs_observed"] == 2
    assert jobs["successful_jobs"] == 1
    assert jobs["non_success_jobs"] == 0
    assert jobs["pending_or_unknown_jobs"] == 1
    assert jobs["job_success_rate"] == 1.0
    assert jobs["pending_job_samples"][0]["current_conclusion_observed_later"] == (
        "failure"
    )

    deployments = result["deployment_evidence"]
    assert deployments["deployments_observed"] == 1
    assert deployments["successful_deployments"] == 1
    assert deployments["non_success_deployments"] == 0
    assert deployments["latest_states"][0]["latest_state_at_capture"] == "success"
    assert result["state_frozen_at_assessment_start"] is True


def _workflow(*, successful: int, failed: int, job_rate: float) -> dict:
    return {
        "workflow_file_count": 4,
        "workflow_configuration_snapshot_sha": "a" * 40,
        "explicit_permissions_present": True,
        "configuration_controls": {
            "cache": True,
            "concurrency": True,
            "timeout": True,
            "matrix": True,
            "artifact_upload": True,
            "environment_gate": True,
            "test_command": True,
            "lint_command": True,
            "build_command": True,
            "security_command": True,
            "deployment_command": True,
        },
        "successful_runs": successful,
        "non_success_runs": failed,
        "jobs_observed": successful + failed,
        "job_success_rate": job_rate,
        "deployments_observed": successful,
        "successful_deployments": successful,
    }


def test_mutable_history_cannot_change_immutable_scores() -> None:
    earlier = _workflow(successful=83, failed=12, job_rate=1.0)
    later = _workflow(successful=75, failed=25, job_rate=0.8)

    earlier_ci = _immutable_ci_score(earlier, "a" * 40)
    later_ci = _immutable_ci_score(later, "a" * 40)

    assert earlier_ci[0] == later_ci[0]
    assert earlier_ci[3]["score_inputs"] == later_ci[3]["score_inputs"]
    assert earlier_ci[3]["operational_trend"] != later_ci[3]["operational_trend"]

    earlier_delivery = _immutable_delivery_score(
        78,
        earlier_ci[0],
        {
            "commits_returned": 100,
            "pull_requests_returned": 100,
            "merged_pull_requests": 90,
        },
        earlier,
    )
    later_delivery = _immutable_delivery_score(
        78,
        later_ci[0],
        {
            "commits_returned": 1,
            "pull_requests_returned": 0,
            "merged_pull_requests": 0,
        },
        later,
    )

    assert earlier_delivery[0] == later_delivery[0]
    assert earlier_delivery[3]["operational_trend"] != later_delivery[3][
        "operational_trend"
    ]


def test_import_time_hardening_restores_source_signal_binding() -> None:
    from nico import snapshot_repository_evidence as snapshot

    status = HARDENING_STATUS

    assert callable(snapshot.analyze_source_signals)
    assert callable(snapshot.scan_files)
    assert status["source_signal_binding_compatible"] is True
    assert status["frozen_operational_evidence_bound"] is True
    assert status["production_manifest_scope_filter_bound"] is True
    assert status["review_candidate_summary_bound"] is True
