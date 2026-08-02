from __future__ import annotations

from pathlib import Path

from nico.comprehensive_client_readiness_v59 import (
    install_comprehensive_client_readiness_v59,
    reconcile_client_readiness,
)


ROOT = Path(__file__).resolve().parents[1]


def _scanner(name: str, status: str, findings: int = 0) -> dict[str, object]:
    return {
        "scanner_name": name,
        "status": status,
        "exact_commit_match": True,
        "artifact_retained": True,
        "finding_count": findings,
    }


def test_client_readiness_reconciles_scanner_state_coverage_and_maturity() -> None:
    scanners = [
        _scanner("bandit", "completed"),
        _scanner("eslint", "completed"),
        _scanner("gitleaks", "completed_with_findings", 6),
        _scanner("npm-audit", "completed"),
        _scanner("osv-scanner", "completed_with_findings", 59),
        _scanner("pip-audit", "completed"),
        _scanner("semgrep", "completed"),
        _scanner("trufflehog", "completed_with_findings", 11),
        _scanner("typescript", "completed"),
    ]
    canonical = {
        "requested_analyzers": 9,
        "applicable_analyzers": 9,
        "assessment": {
            "technical_score": 92,
            "maturity_level": "Senior",
            "incomplete_analyzers": ["bandit", "gitleaks"],
            "analyzer_execution_coverage": 78,
        },
        "scorecard": {
            "maturity": "Exceptional",
            "analyzer_execution_coverage": 88,
        },
        "scanner_records": scanners,
        "provenance": {
            "completed_applicable_analyzers": 9,
            "incomplete_applicable_analyzers": 0,
            "analyzer_execution_coverage": 100,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    result = reconcile_client_readiness(canonical)

    assert result["assessment"]["incomplete_analyzers"] == []
    assert result["assessment"]["analyzer_execution_coverage"] == 100
    assert result["scorecard"]["analyzer_execution_coverage"] == 100
    assert result["provenance"]["analyzer_execution_coverage"] == 100
    assert result["assessment"]["maturity_level"] == "Exceptional"
    assert result["scorecard"]["maturity"] == "Exceptional"
    assert result["client_readiness_contract"]["scanner_execution_completion"] == 100
    assert len(result["client_readiness_contract"]["completed_exact_commit_scanners"]) == 9
    assert result["client_readiness_contract"]["human_review_required"] is True
    assert result["client_readiness_contract"]["client_delivery_allowed"] is False


def test_client_readiness_repairs_whitespace_corrupted_identifiers() -> None:
    canonical = {
        "requested_analyzers": 1,
        "assessment": {"technical_score": 92},
        "scanner_records": [_scanner("bandit", "completed")],
        "canonical_findings": [
            {
                "symbol": "apply_scanner_artifact_scoring",
                "recommendation": (
                    "Split responsibilities in `appy_ l scanner_artifact_scoring` "
                    "into bounded helpers."
                ),
            },
            {
                "symbol": "_spanish_pdf",
                "recommendation": "Refactor ` span ish_pdf` before release.",
            },
        ],
        "table_label": "S p ecific correction",
    }

    result = reconcile_client_readiness(canonical)
    rendered = str(result)

    assert "appy_ l scanner_artifact_scoring" not in rendered
    assert "span ish_pdf" not in rendered
    assert "S p ecific correction" not in rendered
    assert "apply_scanner_artifact_scoring" in rendered
    assert "_spanish_pdf" in rendered
    assert "Specific correction" in rendered


def test_execution_complete_is_separate_from_limited_human_evidence() -> None:
    canonical = {
        "requested_analyzers": 1,
        "assessment": {"technical_score": 92},
        "scanner_records": [_scanner("bandit", "completed")],
        "functional_qa": {
            "status": "COMPLETE",
            "human_evidence_status": "not_assessed",
        },
    }

    result = reconcile_client_readiness(canonical)
    stage = result["functional_qa"]

    assert stage["execution_status"] == "complete"
    assert stage["evidence_status"] == "limited"
    assert stage["requires_human_review"] is True


def test_runtime_installs_client_readiness_before_scoring_and_rendering() -> None:
    source = (
        ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
    ).read_text(encoding="utf-8")

    client_readiness = source.index("install_comprehensive_client_readiness_v59()")
    scoring = source.index("install_comprehensive_scoring_manifest_v54()")

    assert client_readiness < scoring
    assert '"analyzer_coverage_canonicalized": True' in source
    assert '"maturity_terminology_unified": True' in source
    assert '"identifier_integrity_repaired_before_render": True' in source


def test_client_readiness_installer_binds_real_final_register_boundary() -> None:
    from nico import client_report_completion_v2 as completion

    result = install_comprehensive_client_readiness_v59()

    assert result["status"] in {"installed", "already_installed"}
    assert result["bound"] is True
    assert getattr(
        completion._install_register,
        "_nico_comprehensive_client_readiness_v59",
        False,
    ) is True
