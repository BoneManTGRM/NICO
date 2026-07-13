from __future__ import annotations

from typing import Any

import nico.full_assessment_orchestrator as orchestrator
import nico.scanner_worker as scanner_worker


def _context(**overrides: Any) -> dict[str, Any]:
    context = {
        "run_id": "fullrun_exact",
        "scan_id": "scan_missing",
        "repository": "example/repository",
        "customer_id": "customer_one",
        "project_id": "project_one",
        "authorized_by": "authorized_operator",
        "authorization_scope": "authorized defensive repository assessment",
        "run_scanners": True,
        "tools": ["bandit", "semgrep"],
    }
    context.update(overrides)
    return context


def test_missing_scanner_is_replaced_on_same_full_run(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        scanner_worker,
        "get_scan",
        lambda scan_id: {"status": "not_found", "scan_id": scan_id},
    )

    def fake_start_scan(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload)
        return {
            "status": "queued",
            "scan_id": "scan_replacement",
            "run_id": payload["run_id"],
            "tools_requested": payload["tools"],
        }

    monkeypatch.setattr(scanner_worker, "start_scan", fake_start_scan)

    result = orchestrator._scanner_worker_handler(_context(), {})

    assert result["status"] == "queued"
    assert result["scan"]["scan_id"] == "scan_replacement"
    assert result["scan"]["run_id"] == "fullrun_exact"
    assert result["evidence"]["missing_scan_id"] == "scan_missing"
    assert result["evidence"]["replacement_scan_id"] == "scan_replacement"
    assert result["evidence"]["duplicate_full_run_started"] is False
    assert calls == [
        {
            "repository": "example/repository",
            "authorized": True,
            "customer_id": "customer_one",
            "project_id": "project_one",
            "run_id": "fullrun_exact",
            "authorized_by": "authorized_operator",
            "authorization_scope": "authorized defensive repository assessment",
            "tools": ["bandit", "semgrep"],
        }
    ]


def test_recovery_does_not_run_when_scanners_are_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        scanner_worker,
        "get_scan",
        lambda scan_id: {"status": "not_found", "scan_id": scan_id},
    )

    def forbidden_start_scan(_payload: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("replacement scanner must not start")

    monkeypatch.setattr(scanner_worker, "start_scan", forbidden_start_scan)

    result = orchestrator._scanner_worker_handler(_context(run_scanners=False), {})

    assert result["status"] == "unavailable"
    assert result["scan"]["status"] == "not_found"


def test_blocked_replacement_remains_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        scanner_worker,
        "get_scan",
        lambda scan_id: {"status": "not_found", "scan_id": scan_id},
    )
    monkeypatch.setattr(
        scanner_worker,
        "start_scan",
        lambda _payload: {"status": "blocked", "error": "worker unavailable"},
    )

    result = orchestrator._scanner_worker_handler(_context(), {})

    assert result["status"] == "unavailable"
    assert result["evidence"]["recovery_attempted"] is True
    assert "could not be started" in result["message"]
