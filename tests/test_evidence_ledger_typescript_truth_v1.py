from __future__ import annotations

from copy import deepcopy

from nico.evidence_ledger import build_evidence_ledger
from nico.evidence_ledger_typescript_truth_v1 import (
    install_evidence_ledger_typescript_truth_v1,
)


def _result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-08-01T16:00:00Z",
        "report_run_id": "run-typescript-ledger",
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 80,
                "status": "green",
                "summary": "Static analysis is evidence-bound.",
                "evidence": [
                    "bandit scanner execution completed for this exact report run.",
                    "semgrep scanner execution completed for this exact report run.",
                    "eslint scanner execution completed for this exact report run.",
                    "TypeScript compiler AST analysis measured JavaScript and TypeScript metrics for complexity review.",
                ],
                "findings": [],
                "unavailable": [],
            }
        ],
        "quick_wins": [],
        "medium_term_plan": [],
    }


def test_typescript_ast_complexity_does_not_verify_static_analyzer() -> None:
    install_evidence_ledger_typescript_truth_v1()
    coverage = build_evidence_ledger(_result())["coverage_by_section"]["static_analysis"]

    assert coverage["verified_required_tools"] == ["bandit", "semgrep", "eslint"]
    assert coverage["missing_required_tools"] == ["typescript"]
    assert coverage["complete"] is False


def test_explicit_typescript_scanner_execution_receives_credit() -> None:
    install_evidence_ledger_typescript_truth_v1()
    result = deepcopy(_result())
    result["sections"][0]["evidence"].append(
        "typescript scanner execution completed for this exact report run."
    )

    coverage = build_evidence_ledger(result)["coverage_by_section"]["static_analysis"]

    assert coverage["verified_required_tools"] == [
        "bandit",
        "semgrep",
        "eslint",
        "typescript",
    ]
    assert coverage["missing_required_tools"] == []
    assert coverage["complete"] is True


def test_structured_typescript_scanner_artifact_remains_authoritative() -> None:
    install_evidence_ledger_typescript_truth_v1()
    result = deepcopy(_result())
    result["scanner_worker_artifact"] = {
        "tools": {
            "typescript": {
                "tool": "typescript",
                "category": "static",
                "status": "completed",
                "returncode": 0,
                "findings": [],
                "verified_for_this_report": True,
                "command_intent": "tsc --noEmit",
            }
        }
    }

    coverage = build_evidence_ledger(result)["coverage_by_section"]["static_analysis"]

    assert "typescript" in coverage["verified_required_tools"]
    assert coverage["missing_required_tools"] == []


def test_installer_is_idempotent() -> None:
    first = install_evidence_ledger_typescript_truth_v1()
    second = install_evidence_ledger_typescript_truth_v1()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
