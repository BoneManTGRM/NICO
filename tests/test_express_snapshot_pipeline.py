from __future__ import annotations

from copy import deepcopy

import nico.express_snapshot_pipeline as pipeline


def _snapshot(run_id: str = "express_run_snapshot_pipeline") -> dict:
    return {
        "status": "attached",
        "snapshot_id": "snapshot_express_pipeline",
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_pipeline",
        "project_id": "project_pipeline",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "default_branch": "main",
        "captured_at": "2026-07-16T02:45:00Z",
    }


def _scan(status: str = "complete", progress: int = 100) -> dict:
    return {
        "scan_id": "scan_snapshot_express_pipeline",
        "run_id": "express_run_snapshot_pipeline",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_pipeline",
        "project_id": "project_pipeline",
        "status": status,
        "current_stage": "complete" if status == "complete" else "scanner_suite",
        "progress_percent": progress,
        "active_tool": "" if status == "complete" else "semgrep",
        "snapshot_id": "snapshot_express_pipeline",
        "snapshot_commit_sha": "a" * 40,
        "actual_commit_sha": "a" * 40 if status == "complete" else "",
        "snapshot_match": status == "complete",
        "tools_requested": ["pip-audit", "semgrep", "trufflehog"],
        "tools_run": ["pip-audit", "semgrep", "trufflehog"] if status == "complete" else [],
        "unavailable_tools": [],
        "failed_tools": [],
        "timed_out_tools": [],
        "scanner_results": [
            {"tool": "pip-audit", "status": "completed", "category": "dependency", "findings": []},
            {"tool": "semgrep", "status": "completed", "category": "static", "findings": [{"check_id": "example"}]},
            {"tool": "trufflehog", "status": "completed", "category": "secret", "findings": []},
        ] if status == "complete" else [],
        "finding_summary": {"raw_total": 1, "material_total": 0, "review_required_total": 1},
        "heartbeat_sequence": 4,
        "heartbeat_at": "2026-07-16T02:46:00Z",
    }


def _request() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "authorized": True,
        "authorization_confirmed": True,
        "authorized_by": "requester_confirmation",
        "authorization_scope": "repository assessment only",
        "customer_id": "customer_pipeline",
        "project_id": "project_pipeline",
    }


def test_start_express_snapshot_scan_binds_exact_run_snapshot_and_authorization(monkeypatch) -> None:
    captured_payload: dict = {}
    monkeypatch.setattr(pipeline, "capture_repository_snapshot", lambda context: _snapshot(context["run_id"]))

    def start(payload: dict):
        captured_payload.update(deepcopy(payload))
        return _scan("queued", 2)

    monkeypatch.setattr(pipeline, "start_snapshot_scan", start)

    snapshot, scan = pipeline.start_express_snapshot_scan("express_run_snapshot_pipeline", _request())

    assert snapshot["commit_sha"] == "a" * 40
    assert scan["scan_id"] == "scan_snapshot_express_pipeline"
    assert captured_payload["run_id"] == "express_run_snapshot_pipeline"
    assert captured_payload["snapshot_id"] == snapshot["snapshot_id"]
    assert captured_payload["snapshot_commit_sha"] == snapshot["commit_sha"]
    assert captured_payload["authorized_by"] == "requester_confirmation"
    assert captured_payload["authorization_scope"] == "repository assessment only"


def test_wait_for_express_snapshot_scan_returns_only_verified_completion(monkeypatch) -> None:
    sequence = iter([_scan("running", 30), _scan("running", 67), _scan("complete", 100)])
    monkeypatch.setattr(pipeline, "get_scan", lambda _scan_id: next(sequence))
    monkeypatch.setattr(pipeline.time, "sleep", lambda _seconds: None)
    updates: list[dict] = []

    completed = pipeline.wait_for_express_snapshot_scan(
        "express_run_snapshot_pipeline",
        _snapshot(),
        _scan("queued", 2),
        on_update=lambda scan: updates.append(deepcopy(scan)),
    )

    assert completed["status"] == "complete"
    assert completed["snapshot_match"] is True
    assert [item["progress_percent"] for item in updates] == [30, 67, 100]


def test_wait_blocks_identity_mismatch_before_report_generation(monkeypatch) -> None:
    mismatch = _scan("running", 40)
    mismatch["run_id"] = "express_run_wrong"
    monkeypatch.setattr(pipeline, "get_scan", lambda _scan_id: mismatch)

    try:
        pipeline.wait_for_express_snapshot_scan(
            "express_run_snapshot_pipeline",
            _snapshot(),
            _scan("queued", 2),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
        assert exc.detail["code"] == "express_snapshot_scanner_identity_mismatch"
        assert exc.detail["duplicate_start_allowed"] is False
    else:
        raise AssertionError("Expected scanner identity mismatch to block Express reporting")


def test_terminal_unverified_scanner_never_allows_report_completion(monkeypatch) -> None:
    unavailable = _scan("unavailable", 100)
    unavailable["snapshot_match"] = False
    monkeypatch.setattr(pipeline, "get_scan", lambda _scan_id: unavailable)

    try:
        pipeline.wait_for_express_snapshot_scan(
            "express_run_snapshot_pipeline",
            _snapshot(),
            _scan("queued", 2),
        )
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 503
        assert exc.detail["code"] == "express_snapshot_scanner_incomplete"
        assert exc.detail["scanner"]["status"] == "unavailable"
    else:
        raise AssertionError("Expected unverified terminal scanner state to block report generation")


def test_exact_scanner_attachment_removes_false_unavailable_claims_and_maps_core_sections() -> None:
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "unavailable_data_notes": [
            "CLI scanners are marked unavailable until a sandboxed worker executes them.",
            "Stakeholder business context remains unavailable.",
        ],
        "medium_term_plan": [
            "Add a sandboxed worker that checks out authorized repositories and runs pip-audit and Semgrep.",
            "Expand human stakeholder review.",
        ],
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency Health",
                "evidence": [],
                "findings": [],
                "unavailable": ["pip-audit, npm audit, and OSV Scanner CLI execution are not yet run inside a sandboxed worker."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "evidence": [],
                "findings": [],
                "unavailable": ["Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker."],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Review",
                "evidence": [],
                "findings": [],
                "unavailable": ["Full git-history secret scanning requires a sandboxed worker."],
            },
        ],
    }

    attached = pipeline.attach_exact_express_scanner_evidence(result, _snapshot(), _scan())

    assert attached["scanner"]["status"] == "complete"
    assert attached["worker_evidence_attachment"]["mode"] == "exact_same_run_snapshot_bound"
    assert attached["evidence_readiness"]["same_run_scanner_identity_verified"] is True
    assert attached["unavailable_data_notes"] == ["Stakeholder business context remains unavailable."]
    assert attached["medium_term_plan"] == ["Expand human stakeholder review."]
    sections = {item["id"]: item for item in attached["sections"]}
    assert any("pip-audit status=completed" in item for item in sections["dependency_health"]["evidence"])
    assert any("semgrep returned 1 finding" in item for item in sections["static_analysis"]["findings"])
    assert any("trufflehog status=completed" in item for item in sections["secrets_review"]["evidence"])
    assert sections["dependency_health"]["unavailable"] == []
    assert sections["static_analysis"]["unavailable"] == []
    assert sections["secrets_review"]["unavailable"] == []
