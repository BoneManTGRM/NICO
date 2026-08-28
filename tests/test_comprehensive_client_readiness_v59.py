from __future__ import annotations

from pathlib import Path

from nico.comprehensive_client_readiness_v59 import (
    install_comprehensive_client_readiness_v59,
    reconcile_client_readiness,
)
from nico.comprehensive_engagement_metadata_v1 import (
    build_comprehensive_engagement_metadata,
    verify_comprehensive_engagement_metadata,
)


ROOT = Path(__file__).resolve().parents[1]


def _scanner(
    name: str,
    status: str,
    findings: int = 0,
    *,
    completed: bool | None = None,
    verified: bool | None = None,
    reason: str = "",
) -> dict[str, object]:
    result: dict[str, object] = {
        "scanner_name": name,
        "status": status,
        "exact_commit_match": True,
        "artifact_retained": True,
        "finding_count": findings,
        "failure_reason": reason,
    }
    if completed is not None:
        result["completed"] = completed
    if verified is not None:
        result["verified"] = verified
    return result


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
            "sections": [
                {
                    "label": "Static Analysis",
                    "summary": (
                        "Analyzer execution coverage is 88%; remaining failed or "
                        "partial tools are shown separately."
                    ),
                }
            ],
        },
        "scorecard": {
            "maturity": "Exceptional",
            "analyzer_execution_coverage": 88,
        },
        "scanner_execution_records": scanners,
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
    assert "coverage is 100%" in result["assessment"]["sections"][0]["summary"]
    assert result["assessment"]["maturity_level"] == "Exceptional"
    assert result["scorecard"]["maturity"] == "Exceptional"
    assert result["client_readiness_contract"]["scanner_execution_completion"] == 100
    assert len(result["client_readiness_contract"]["completed_exact_commit_scanners"]) == 9
    assert result["client_readiness_contract"]["incomplete_analyzers"] == []
    assert result["client_readiness_contract"]["human_review_required"] is True
    assert result["client_readiness_contract"]["client_delivery_allowed"] is False


def test_client_readiness_does_not_promote_failed_bandit_from_stale_nested_text() -> None:
    scanners = [
        _scanner("bandit", "failed", completed=False, verified=False, reason="parse failed"),
        *[
            _scanner(name, "completed", completed=True, verified=True)
            for name in (
                "eslint",
                "gitleaks",
                "npm-audit",
                "osv-scanner",
                "pip-audit",
                "semgrep",
                "trufflehog",
                "typescript",
            )
        ],
    ]
    canonical = {
        "requested_analyzers": 9,
        "applicable_analyzers": 9,
        "assessment": {
            "technical_score": 92,
            "incomplete_analyzers": ["bandit", "gitleaks"],
            "analyzer_execution_coverage": 78,
            "stale_projection": {
                "scanner_name": "bandit",
                "status": "completed",
                "exact_commit_match": True,
            },
        },
        "scanner_execution_records": scanners,
    }

    result = reconcile_client_readiness(canonical)

    assert result["analyzer_execution_coverage"] == 89
    assert result["assessment"]["incomplete_analyzers"] == ["bandit"]
    assert result["client_readiness_contract"]["incomplete_analyzers"] == ["bandit"]
    assert result["client_readiness_contract"]["coverage_numerator"] == 8
    assert result["client_readiness_contract"]["coverage_denominator"] == 9
    assert result["client_readiness_contract"]["scanner_states"]["bandit"]["completed"] is False


def test_client_readiness_repairs_whitespace_corrupted_identifiers() -> None:
    canonical = {
        "requested_analyzers": 1,
        "assessment": {"technical_score": 92},
        "scanner_execution_records": [_scanner("bandit", "completed")],
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


def test_client_readiness_repairs_only_narrative_and_preserves_exact_literals() -> None:
    metadata = build_comprehensive_engagement_metadata(
        client_name="Cody Jenkins",
        project_name="NICO Audit",
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "primary_technical_contact": [
                        "Cody — Repository owner / project lead"
                    ],
                    "access_method": [
                        "Public GitHub repository via HTTPS/API — read-only access"
                    ],
                    "authorized_scope": [
                        "BoneManTGRM/NICO — entire repository, current main branch, "
                        "including source code, configuration, CI/CD workflows, "
                        "dependency manifests, documentation, and repository metadata. "
                        "Read-only technical and security assessment."
                    ],
                }
            }
        },
    )
    identity = {
        "customer_name": metadata["client_name"],
        "project_name": metadata["project_name"],
        "primary_technical_contact": metadata["primary_technical_contact"],
        "access_method": metadata["access_method"],
        "authorized_scope": metadata["authorized_scope"],
        "repository": "Org/Audit",
        "commit_sha": "a" * 40,
        "run_id": "comprun_Audit_001",
        "evidence_ledger_id": "ledger_Audit_001",
    }
    canonical = {
        "engagement_metadata": metadata,
        "identity": identity,
        "canonical_findings": [
            {
                "finding_id": "NICO-Audit-001",
                "candidate_id": "candidate_Audit_001",
                "symbol": "audit",
                "exact_source": "Org/Audit/audit.py:12",
                "recommendation": (
                    "For NICO Audit, refactor `a u d i t` without rewriting "
                    "Cody — Repository owner / project lead."
                ),
            }
        ],
    }

    result = reconcile_client_readiness(canonical)

    assert result["engagement_metadata"] == metadata
    assert verify_comprehensive_engagement_metadata(result["engagement_metadata"])
    assert result["identity"] == identity
    finding = result["canonical_findings"][0]
    assert finding["finding_id"] == "NICO-Audit-001"
    assert finding["candidate_id"] == "candidate_Audit_001"
    assert finding["exact_source"] == "Org/Audit/audit.py:12"
    assert finding["symbol"] == "audit"
    assert "NICO Audit" in finding["recommendation"]
    assert "Cody — Repository owner / project lead" in finding["recommendation"]
    assert "`audit`" in finding["recommendation"]
    assert "a u d i t" not in finding["recommendation"]


def test_client_readiness_never_repairs_raw_or_human_evidence_strings() -> None:
    canonical = {
        "executive_summary": "The Security Audit remains pending.",
        "canonical_findings": [
            {
                "symbol": "safe_handler",
                "recommendation": "Refactor `s a f e _ h a n d l e r` safely.",
                "evidence": {
                    "summary": "Audit/file.py is exact retained source evidence."
                },
            }
        ],
        "raw_evidence": {
            "summary": "Audit/file.py must remain byte-faithful.",
            "content": "span ish_pdf is client-retained evidence.",
            "scanner_name": "bandit",
            "status": "failed",
            "completed": False,
            "verified": False,
            "exact_commit_match": False,
            "failure_reason": "literal client evidence",
            "analyzer_execution_coverage": 17,
            "maturity": "Client Literal",
        },
        "human_evidence": {
            "notes": ["production_ app was supplied literally by the client."],
            "scanner_observation": {
                "symbol": "audit",
                "scanner_name": "bandit",
                "status": "failed",
                "completed": False,
                "verified": False,
                "exact_commit_match": False,
                "failure_reason": "reported by the client",
                "analyzer_execution_coverage": 17,
                "maturity": "Client Literal",
            },
        },
    }

    result = reconcile_client_readiness(canonical)

    finding = result["canonical_findings"][0]
    assert finding["recommendation"] == "Refactor `safe_handler` safely."
    assert finding["evidence"] == canonical["canonical_findings"][0]["evidence"]
    assert result["raw_evidence"] == canonical["raw_evidence"]
    assert result["human_evidence"] == canonical["human_evidence"]
    assert result["executive_summary"] == "The Security Audit remains pending."


def test_execution_complete_is_separate_from_limited_human_evidence() -> None:
    canonical = {
        "requested_analyzers": 1,
        "assessment": {"technical_score": 92},
        "scanner_execution_records": [_scanner("bandit", "completed")],
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

    bandit = source.index("install_bandit_json_execution_v61()")
    client_readiness = source.index("install_comprehensive_client_readiness_v59()")
    scoring = source.index("install_comprehensive_scoring_manifest_v54()")

    assert bandit < client_readiness < scoring
    assert '"bandit_json_artifact_required": True' in source
    assert '"authoritative_scanner_records_only": True' in source
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
