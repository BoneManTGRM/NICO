from __future__ import annotations

import base64
import io
from pathlib import Path

from pypdf import PdfReader

from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from nico.v2_canonical_premium_truth import repair_canonical_premium_truth


SHA = "9" * 40
ROOT = Path(__file__).resolve().parents[1]


def _scanner(name: str, *, findings: list[dict] | None = None, failed: bool = False) -> dict:
    return {
        "scanner_name": name,
        "tool": name,
        "state": "failed" if failed else ("completed_with_findings" if findings else "completed"),
        "status": "failed" if failed else ("completed_with_findings" if findings else "completed"),
        "completed": not failed,
        "verified": not failed,
        "verified_complete": not failed,
        "verified_for_this_report": not failed,
        "exact_commit_match": True,
        "commit_sha": SHA,
        "snapshot_commit_sha": SHA,
        "artifact_hash": (name[0] if name else "a") * 64,
        "required": True,
        "category": "secret" if name in {"gitleaks", "trufflehog"} else ("dependency" if name in {"npm-audit", "pip-audit", "osv-scanner"} else "static"),
        "findings": list(findings or []),
        "failure_reason": "partial clone object unavailable" if failed else "",
    }


def _canonical() -> dict:
    osv = [
        {
            "id": "GHSA-COMPLETE",
            "package": "production-package",
            "installed_version": "1.0.0",
            "fixed_versions": ["1.2.0"],
            "severity": "high",
            "dependency_path": "apps/web/package-lock.json",
            "reachable": True,
        },
        {
            "id": "GHSA-INCOMPLETE",
            "severity": "high",
            "summary": "Package and installed version were not retained.",
        },
    ]
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "commit_sha": SHA,
            "run_id": "comprun_truth_repair",
            "evidence_ledger_id": "ledger-truth-repair",
            "customer_id": "customer-truth-repair",
            "project_id": "project-truth-repair",
            "report_language": "en",
        },
        "report_language": "en",
        "assessment": {
            "repository": "BoneManTGRM/NICO",
            "technical_score": 74,
            "canonical_evidence_adjusted_score": 73,
            "maturity_signal": {"score": 74, "presented_score": 74, "level": "Moderate"},
            "sections": [
                {"id": "code_audit", "label": "Code Audit", "score_value": 78, "assurance_label": "VERIFIED", "evidence": [], "findings": []},
                {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score_value": 31, "assurance_label": "VERIFIED", "evidence": ["raw=59; material=16; review_required=43"], "findings": []},
                {"id": "secrets_review", "label": "Secrets Exposure Review", "score_value": 91, "assurance_label": "REVIEW LIMITED", "evidence": ["gitleaks: status=missing"], "unavailable": ["gitleaks missing"]},
                {"id": "static_analysis", "label": "Static Analysis", "score_value": 83, "assurance_label": "REVIEW LIMITED", "evidence": ["bandit: status=failed", "eslint: status=missing"], "unavailable": ["bandit failed", "eslint missing"]},
                {"id": "ci_cd", "label": "CI/CD Analysis", "score_value": 78, "assurance_label": "VERIFIED", "evidence": [], "findings": []},
                {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score_value": 78, "assurance_label": "VERIFIED", "evidence": [], "findings": []},
                {"id": "velocity_complexity", "label": "Velocity / Complexity", "score_value": 84, "assurance_label": "VERIFIED", "evidence": [], "findings": []},
            ],
            "findings_register": [],
            "unavailable_data_notes": [],
            "decision_postures": {},
            "how_to_use_report": ["Complete exact-package human review before client delivery."],
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-TEST-EVAL",
                "priority": "P1",
                "category": "code",
                "title": "python_eval_exec",
                "location": "tests/test_express_safe_trace_diagnostics.py:12",
                "status": "open",
                "recommendation": "Review dynamic execution.",
            },
            {
                "finding_id": "RISK-PROD-COMPLEXITY",
                "priority": "P1",
                "category": "architecture",
                "title": "Reduce complexity in page.tsx",
                "location": "apps/web/app/operations/page.tsx:177",
                "fact": "cyclomatic_complexity=52",
                "business_impact": "Regression risk is concentrated.",
                "recommendation": "Split the module into bounded components.",
                "status": "open",
                "acceptance_criteria": ["Complexity is at most 30."],
            },
        ],
        "scanner_execution_records": [
            _scanner("bandit"),
            _scanner("eslint", findings=[{"ruleId": "complexity", "filePath": "apps/web/app/page.tsx"}]),
            _scanner("gitleaks"),
            _scanner("npm-audit"),
            _scanner("osv-scanner", findings=osv),
            _scanner("pip-audit"),
            _scanner("semgrep"),
            _scanner("trufflehog", failed=True),
            _scanner("typescript"),
        ],
        "stage_summaries": [
            {
                "stage_id": "dependency_security_static_analysis",
                "title": "Dependency, Security, and Static Analysis",
                "status": "review_required",
                "summary": "Stale scanner summary.",
                "evidence": ["bandit failed", "eslint missing", "gitleaks missing"],
                "unavailable": ["stale"],
            },
            {
                "stage_id": "evidence_reconciliation_and_scoring",
                "title": "Evidence Reconciliation and Scoring",
                "status": "complete",
                "summary": "Legacy scoring result.",
                "evidence": ["technical_score: 72", "evidence_adjusted_score: 73"],
                "technical_score": 72,
                "canonical_evidence_adjusted_score": 73,
                "final_report_input_scores_synchronized": True,
            },
        ],
        "roadmap": [],
    }


def test_repair_replaces_stale_scanner_truth_and_excludes_test_only_risk():
    repaired = repair_canonical_premium_truth(_canonical())
    assessment = repaired["assessment"]
    sections = {item["id"]: item for item in assessment["sections"]}

    assert "bandit: status=completed" in " ".join(sections["static_analysis"]["evidence"])
    assert "eslint: status=completed_with_findings" in " ".join(sections["static_analysis"]["evidence"])
    assert "gitleaks: status=completed" in " ".join(sections["secrets_review"]["evidence"])
    assert "bandit failed" not in " ".join(sections["static_analysis"].get("unavailable") or []).casefold()
    assert sections["dependency_health"]["score_value"] is None
    assert sections["dependency_health"]["exclude_from_maturity"] is True
    assert len(repaired["dependency_dispositions"]) == 2
    assert sum(item["disposition"] == "verified_material" for item in repaired["dependency_dispositions"]) == 1
    assert sum(item["disposition"] == "review_required" for item in repaired["dependency_dispositions"]) == 1

    ids = [item["finding_id"] for item in repaired["canonical_findings"]]
    assert ids == ["RISK-PROD-COMPLEXITY"]
    observations = repaired["non_production_observations"]
    assert observations[0]["finding_id"] == "RISK-TEST-EVAL"
    assert observations[0]["score_impact"] is False

    assert assessment["technical_score"] == 82
    assert assessment["maturity_signal"]["score"] == 82
    assert assessment["maturity_signal"]["presented_score"] == 82
    assert assessment["canonical_evidence_adjusted_score"] == 73
    assert repaired["technical_score"] == 82
    assert repaired["canonical_evidence_adjusted_score"] == 73
    assert repaired["report_finality"] == "final"
    assert repaired["approval_status"] == "pending_human_approval"


def test_premium_report_restores_dark_cover_and_uses_only_repaired_truth():
    result = rebuild_client_artifacts({"json": _canonical()})
    canonical = result["json"]
    markdown = result["markdown"]
    normalized_markdown = markdown.casefold()
    pdf = base64.b64decode(result["pdf_base64"])
    reader = PdfReader(io.BytesIO(pdf))
    first_page = reader.pages[0].extract_text() or ""
    all_text = "\n".join((page.extract_text() or "") for page in reader.pages)

    assert result["premium_report_renderer"]["old_dark_premium_front_matter_restored"] is True
    assert result["premium_report_renderer"]["plain_canonical_score_cover_removed"] is True
    assert "NICO / EVIDENCE-BOUND ENGINEERING INTELLIGENCE" in first_page
    assert "NICO COMPREHENSIVE" in first_page
    assert "Canonical Score Summary" not in first_page
    assert "Dependency Disposition Register" in markdown
    assert "Non-Production Observations" in markdown
    assert "RISK-TEST-EVAL" not in markdown.split("## Detailed Canonical Findings", 1)[1].split("## Non-Production Observations", 1)[0]
    assert "RISK-TEST-EVAL" in markdown.split("## Non-Production Observations", 1)[1]
    assert "bandit: completed" in normalized_markdown
    assert "eslint: completed_with_findings" in normalized_markdown
    assert "gitleaks: completed" in normalized_markdown
    assert "bandit failed" not in normalized_markdown
    assert "eslint missing" not in normalized_markdown
    assert "gitleaks missing" not in normalized_markdown
    assert "FINAL REPORT" in markdown
    assert "CLIENT DELIVERY NOT AUTHORIZED" in markdown
    assert "canonical_score_truth_mismatch" not in markdown
    assert "· DRAFT" not in all_text
    assert canonical["assessment"]["technical_score"] == canonical["assessment"]["maturity_signal"]["presented_score"]


def test_scanner_authority_materializes_partial_clone_and_enriches_osv_context():
    source = (ROOT / "nico/v2_snapshot_scanner_authority.py").read_text(encoding="utf-8")
    assert '"--refetch"' in source
    assert '"remote.origin.promisor"' in source
    assert '"remote.origin.partialclonefilter"' in source
    assert '"fsck", "--full", "--no-dangling"' in source
    assert "_enrich_osv_findings(payload" in source
    assert "package_context_retained" in source
