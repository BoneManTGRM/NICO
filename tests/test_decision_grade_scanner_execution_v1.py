from __future__ import annotations

from nico.decision_grade_contract_v1 import EvidenceStatus, build_decision_grade_contract
from nico.decision_grade_scanner_execution_v1 import (
    install_decision_grade_scanner_execution,
    normalize_scanner_stage_summaries,
    scanner_results_from_stage,
    wrap_contract_builder,
)

COMMIT = "a" * 40


def _identity() -> dict[str, object]:
    return {
        "run_id": "comprun_scanner_execution",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": COMMIT,
        "assessment_type": "comprehensive",
        "branch": "main",
        "nico_version": "0.1.1",
        "scanner_configuration_version": "test-v1",
    }


def _assessment() -> dict[str, object]:
    return {
        "technical_score": 82,
        "canonical_evidence_adjusted_score": 71,
        "findings_register": [],
        "sections": [],
        "scoring_weights": [],
    }


def _stage() -> dict[str, object]:
    return {
        "stage": "dependency_security_static_analysis",
        "scanner": {
            "tools_requested": ["semgrep", "bandit", "osv-scanner", "gitleaks"],
            "tools_run": ["semgrep"],
            "failed_tools": ["bandit"],
            "timed_out_tools": ["osv-scanner"],
            "unavailable_tools": ["gitleaks"],
            "required_tools": ["semgrep", "bandit", "osv-scanner"],
            "optional_tools": ["gitleaks"],
            "tool_messages": {"bandit": "bounded output was incomplete"},
        },
    }


def test_scanner_arrays_generate_complete_failed_timeout_and_partial_records() -> None:
    records = scanner_results_from_stage(_stage())
    by_tool = {item["tool"]: item for item in records}

    assert by_tool["semgrep"]["status"] == "complete"
    assert by_tool["bandit"]["status"] == "failed"
    assert by_tool["bandit"]["reason"] == "bounded output was incomplete"
    assert by_tool["osv-scanner"]["status"] == "timed_out"
    assert by_tool["gitleaks"]["status"] == "partial"
    assert by_tool["gitleaks"]["required"] is False


def test_existing_execution_records_are_preserved_without_duplicates() -> None:
    stage = _stage()
    stage["scanner_results"] = [{"tool": "bandit", "status": "failed", "required": True, "category": "static"}]
    normalized = normalize_scanner_stage_summaries([stage])
    bandit = [item for item in normalized[0]["scanner_results"] if item["tool"] == "bandit"]

    assert len(bandit) == 1


def test_wrapper_populates_canonical_scanner_executions_and_readiness() -> None:
    wrapped = wrap_contract_builder(build_decision_grade_contract)
    contract = wrapped(
        identity=_identity(),
        assessment=_assessment(),
        stage_summaries=[_stage()],
        roadmap=[],
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=10,
        core_page_count=7,
    )
    by_tool = {item.scanner_name: item for item in contract.scanner_executions}

    assert by_tool["semgrep"].status == EvidenceStatus.COMPLETE
    assert by_tool["bandit"].status == EvidenceStatus.FAILED
    assert by_tool["osv-scanner"].status == EvidenceStatus.TIMED_OUT
    assert by_tool["gitleaks"].status == EvidenceStatus.PARTIAL
    assert any(item.code == "required_scanner_evidence_incomplete" for item in contract.validation_issues)


def test_installer_is_idempotent() -> None:
    class ReportModule:
        build_decision_grade_contract = staticmethod(build_decision_grade_contract)

    first = install_decision_grade_scanner_execution(ReportModule)
    second = install_decision_grade_scanner_execution(ReportModule)

    assert first["bound"] is True
    assert second["bound"] is True
