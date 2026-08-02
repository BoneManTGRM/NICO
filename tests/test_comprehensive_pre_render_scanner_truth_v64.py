from __future__ import annotations

import base64
import io

from pypdf import PdfReader

from nico import comprehensive_report_package as report_module
from nico.comprehensive_pre_render_scanner_truth_v64 import (
    canonicalize_stage_results_before_render,
    derive_authoritative_scanner_truth,
    install_pre_render_authoritative_scanner_truth,
)

TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
]


def _identity() -> dict[str, str]:
    return {
        "run_id": "comprun_pre_render_truth",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_pre_render_truth",
        "customer_id": "customer_pre_render_truth",
        "project_id": "project_pre_render_truth",
    }


def _assessment() -> dict:
    return {
        "status": "complete",
        "technical_score": 92,
        "maturity_signal": {
            "level": "Exceptional",
            "score": 92,
            "presented_score": 92,
            "evidence_readiness_score": 100,
        },
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 92,
                "presented_score": 92,
                "status": "green",
                "presented_status": "green",
                "summary": "Exact-run scanner evidence was retained.",
                "evidence": ["Nine exact-run analyzer records were retained."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "unavailable_data_notes": [],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _stages(*, failed: list[str] | None = None) -> dict:
    failed = failed or []
    tools_run = [tool for tool in TOOLS if tool not in failed]
    return {
        "authorization_and_scope": {
            "status": "complete",
            "summary": "Authorized defensive assessment.",
            "evidence": {"authorized": True},
        },
        "dependency_security_static_analysis": {
            "status": "complete",
            "summary": "Scanner execution completed.",
            "scanner": {
                "status": "complete",
                "tools_requested": list(TOOLS),
                "tools_run": tools_run,
                "failed_tools": failed,
                "unavailable_tools": [],
                "timed_out_tools": [],
                "snapshot_match": True,
            },
            "evidence": {
                "analyzer_execution_coverage": 78,
                "incomplete_applicable_analyzers": 2,
                "incomplete_analyzers": ["pip-audit", *(failed or ["bandit"])],
                "nested_projection": [
                    "client_readiness_contract.incomplete_analyzers[0]: pip-audit",
                    *(
                        ["client_readiness_contract.incomplete_analyzers[1]: semgrep"]
                        if "semgrep" in failed
                        else []
                    ),
                ],
            },
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "summary": "Canonical scoring completed.",
            "assessment": _assessment(),
            "client_readiness_contract": {
                "authoritative_source": "direct_exact_run_records_plus_live_scanner_manifest",
                "coverage_numerator": len(tools_run),
                "coverage_denominator": len(TOOLS),
                "requested_exact_run_scanners": list(TOOLS),
                "completed_exact_commit_scanners": tools_run,
                # Deliberately stale copied alias from the previous report pass.
                "incomplete_analyzers": ["pip-audit", *(failed or ["bandit"])],
            },
            "evidence": {
                "incomplete_analyzers": ["pip-audit", *(failed or ["bandit"])],
            },
        },
        "decision_report_generation": {
            "status": "complete",
            "summary": "Core decision report generated.",
            "evidence": {
                "legacy_lines": [
                    "assessment.incomplete_analyzers[0]: pip-audit",
                    *(
                        ["assessment.incomplete_analyzers[1]: semgrep"]
                        if "semgrep" in failed
                        else []
                    ),
                ]
            },
        },
    }


def _pdf_text(encoded: str) -> str:
    raw = base64.b64decode(encoded)
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)


def test_all_completed_tools_remove_every_stale_incomplete_alias_before_flattening() -> None:
    original = _stages()
    cleaned, manifest = canonicalize_stage_results_before_render(original)

    assert manifest["requested"] == sorted(TOOLS)
    assert manifest["completed"] == sorted(TOOLS)
    assert manifest["incomplete"] == []
    assert manifest["coverage"] == 100
    assert manifest["removed_stale_alias_count"] >= 5
    assert cleaned["dependency_security_static_analysis"]["evidence"]["incomplete_analyzers"] == []
    assert cleaned["dependency_security_static_analysis"]["evidence"]["incomplete_applicable_analyzers"] == 0
    assert cleaned["dependency_security_static_analysis"]["evidence"]["analyzer_execution_coverage"] == 100
    assert cleaned["decision_report_generation"]["evidence"]["legacy_lines"] == []

    # The input is evidence and remains immutable.
    assert original["dependency_security_static_analysis"]["evidence"]["incomplete_analyzers"]


def test_a_genuinely_failed_tool_remains_incomplete_while_completed_aliases_are_removed() -> None:
    cleaned, manifest = canonicalize_stage_results_before_render(
        _stages(failed=["semgrep"])
    )

    assert manifest["coverage"] == 89
    assert manifest["incomplete"] == ["semgrep"]
    evidence = cleaned["dependency_security_static_analysis"]["evidence"]
    assert evidence["incomplete_analyzers"] == ["semgrep"]
    assert evidence["nested_projection"] == [
        "client_readiness_contract.incomplete_analyzers[1]: semgrep"
    ]
    assert cleaned["decision_report_generation"]["evidence"]["legacy_lines"] == [
        "assessment.incomplete_analyzers[1]: semgrep"
    ]


def test_pre_render_builder_produces_markdown_html_and_pdf_without_false_incomplete_paths() -> None:
    install_pre_render_authoritative_scanner_truth()
    package = report_module.build_comprehensive_report_package(
        identity=_identity(),
        stage_results=_stages(),
    )

    assert package["status"] == "complete"
    report = package["report_package"]
    combined = "\n".join(
        (str(report["markdown"]), str(report["html"]), _pdf_text(str(report["pdf_base64"])))
    )
    assert "incomplete_analyzers[" not in combined.casefold()
    assert "incomplete_scanners[" not in combined.casefold()
    assert "analyzer_execution_coverage: 100" in combined.casefold()
    manifest = package["pre_render_scanner_truth"]
    assert manifest["pre_flatten_truth_enforced"] is True
    assert manifest["scanner_results_changed"] is False
    assert manifest["scores_changed"] is False
    assert report["json"]["pre_render_scanner_truth"]["incomplete"] == []
    assert report["human_review_required"] is True
    assert report["client_delivery_allowed"] is False


def test_no_authoritative_population_preserves_stage_evidence_fail_closed() -> None:
    stages = {
        "authorization_and_scope": {
            "status": "complete",
            "evidence": {"incomplete_analyzers": ["unknown-tool"]},
        }
    }
    cleaned, manifest = canonicalize_stage_results_before_render(stages)

    assert cleaned == stages
    assert manifest["status"] == "not_applied_no_authoritative_scanner_population"
    assert manifest["removed_stale_alias_count"] == 0


def test_truth_derivation_prefers_live_failures_over_stale_completed_contract() -> None:
    stages = _stages(failed=["semgrep"])
    stages["evidence_reconciliation_and_scoring"]["client_readiness_contract"][
        "completed_exact_commit_scanners"
    ] = list(TOOLS)

    truth = derive_authoritative_scanner_truth(stages)

    assert "semgrep" not in truth["completed"]
    assert truth["incomplete"] == ["semgrep"]
    assert truth["coverage"] == 89
