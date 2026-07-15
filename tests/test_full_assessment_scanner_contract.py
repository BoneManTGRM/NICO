from __future__ import annotations

from nico.full_assessment_idempotent_handlers import idempotent_full_assessment_handlers
from nico.full_assessment_scanner_contract import (
    DEFAULT_FULL_SCANNERS,
    _finding_summary,
    _requested_tools,
    _truthful_execution_state,
    apply_scanner_finding_truth,
)


def test_full_requested_tool_contract_keeps_every_requested_name_visible() -> None:
    requested = list(DEFAULT_FULL_SCANNERS) + ["future-scanner"]

    assert _requested_tools({"tools": requested}) == requested
    assert _requested_tools({}) == list(DEFAULT_FULL_SCANNERS)
    assert "gitleaks" in requested
    assert "trufflehog" in requested
    assert "typescript" in requested


def test_nonzero_exit_without_parseable_findings_is_not_called_completed() -> None:
    result = _truthful_execution_state(
        {"tool": "semgrep", "status": "completed", "returncode": 2, "findings": []}
    )

    assert result["status"] == "failed"
    assert result["completion_state"] == "failed"
    assert "non-zero exit code" in result["reason"]


def test_nonzero_exit_with_findings_remains_completed_with_findings() -> None:
    result = _truthful_execution_state(
        {
            "tool": "pip-audit",
            "status": "completed",
            "returncode": 1,
            "findings": [{"severity": "high", "id": "TEST-1"}],
        }
    )

    assert result["status"] == "completed"
    assert result["completion_state"] == "completed_with_findings"
    assert result["finding_count"] == 1


def test_finding_summary_preserves_tool_category_and_severity_counts() -> None:
    summary = _finding_summary(
        [
            {
                "tool": "pip-audit",
                "category": "dependency",
                "findings": [{"severity": "high"}, {"severity": "low"}],
            },
            {
                "tool": "gitleaks",
                "category": "secret",
                "findings": [{"confidence": "verified"}],
            },
        ]
    )

    assert summary["total"] == 3
    assert summary["by_tool"] == {"gitleaks": 1, "pip-audit": 2}
    assert summary["by_category"] == {"dependency": 2, "secret": 1}
    assert summary["severity_by_category"]["dependency"] == {"high": 1, "low": 1}
    assert summary["severity_by_category"]["secret"] == {"critical": 1}


def test_only_material_scanner_findings_cap_sections() -> None:
    assessment = {
        "sections": [
            {"id": "dependency_health", "score": 88, "status": "green", "evidence": [], "findings": []},
            {"id": "secrets_review", "score": 88, "status": "green", "evidence": [], "findings": []},
            {"id": "static_analysis", "score": 84, "status": "green", "evidence": [], "findings": []},
        ],
        "maturity_signal": {"score": 88, "level": "Senior"},
        "scorecard": {},
        "findings": [],
    }
    scanner = {
        "finding_summary": {
            "total": 4,
            "by_tool": {"pip-audit": 2, "gitleaks": 1, "eslint": 1},
            "by_category": {"dependency": 2, "secret": 1, "static": 1},
            "severity_by_category": {
                "dependency": {"high": 1, "low": 1},
                "secret": {"critical": 1},
                "static": {"unknown": 1},
            },
        }
    }

    result = apply_scanner_finding_truth(assessment, scanner)
    sections = {item["id"]: item for item in result["sections"]}

    assert sections["dependency_health"]["score"] == 54
    assert sections["dependency_health"]["status"] == "red"
    assert sections["secrets_review"]["score"] == 54
    assert sections["static_analysis"]["score"] == 84
    assert sections["static_analysis"]["status"] == "green"
    assert sections["static_analysis"]["confidence"] == "scanner-review-items-disclosed"
    assert result["scorecard"]["scanner_finding_truth_applied"] is True
    assert result["scorecard"]["raw_scanner_counts_used_as_material"] is False
    assert result["scorecard"]["scanner_material_finding_count"] == 2
    assert result["scorecard"]["scanner_review_required_count"] == 2
    assert "material item(s) requiring human triage" in result["findings"][0]


def test_idempotent_full_pipeline_uses_scanner_truth_handlers() -> None:
    handlers = idempotent_full_assessment_handlers()

    assert handlers["scanner_worker"].__name__ == "full_assessment_scanner_handler"
    assert handlers["evidence_attachment"].__name__ == "full_assessment_evidence_attachment_handler"
    assert handlers["scoring"].__name__ == "full_assessment_scoring_with_scanner_truth_handler"
