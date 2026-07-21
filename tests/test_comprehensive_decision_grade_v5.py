from __future__ import annotations

import base64
import io
import re
from pathlib import Path

from pypdf import PdfReader

from nico.comprehensive_decision_grade_assessment_v5 import build_decision_grade_assessment
from nico.comprehensive_decision_grade_report_v5 import build_comprehensive_report_package
from nico.comprehensive_decision_grade_roadmap_v5 import build_roadmap
from nico.comprehensive_decision_grade_v5 import install_decision_grade_binding

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "nico" / "api" / "comprehensive_production_bootstrap.py"


IDENTITY = {
    "run_id": "comprun_decision_grade_v5",
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "evidence_ledger_id": "ledger_decision_grade_v5",
    "customer_id": "customer_decision_grade",
    "project_id": "project_decision_grade",
}


def _assessment() -> dict:
    repository = {
        "architecture_evidence": {"source_file_count": 569, "test_path_count": 578},
        "dependency_evidence": {"dependency_entries": 21, "lockfile_paths": ["apps/web/package-lock.json"]},
        "activity_evidence": {"commits_returned": 100, "pull_requests_returned": 100, "merged_pull_requests": 84},
        "workflow_evidence": {
            "workflow_file_count": 17,
            "successful_runs": 76,
            "non_success_runs": 23,
            "explicit_permissions_present": True,
            "jobs_observed": 24,
            "job_success_rate": 1.0,
        },
        "code_signal_evidence": {
            "risk_pattern_hits": 2,
            "risk_pattern_samples": [
                "nico/example.py:10: python_eval_exec — Dynamic code execution should be reviewed.",
                "apps/web/app/example.tsx:20: react_dangerous_html — requires sanitization evidence.",
            ],
            "potential_secret_pattern_hits": 0,
        },
        "unavailable_data_notes": [],
    }
    complexity = {
        "complexity_score": 78,
        "files_analyzed": 54,
        "functions_measured": 247,
        "high_complexity_functions": 53,
        "high_complexity_ratio": 0.2146,
        "deep_nesting_functions": 18,
        "duplicate_evidence": {"duplicate_line_ratio": 0.0401},
        "hotspots": [
            {
                "path": "apps/web/app/assessment/MidSectionReview.tsx",
                "line": 1,
                "name": "<module-logic>",
                "cyclomatic_complexity": 148,
                "loc": 340,
                "grade": "F",
                "language": "javascript-typescript",
                "method": "module_residual_lexical_v2",
            }
        ],
        "unavailable_data_notes": [
            "JavaScript and TypeScript complexity uses bounded lexical extraction rather than a full parser."
        ],
    }
    scan = {
        "status": "complete",
        "tools_run": ["osv-scanner", "pip-audit", "npm-audit"],
        "unavailable_tools": ["gitleaks", "trufflehog"],
        "failed_tools": ["bandit", "semgrep"],
        "timed_out_tools": [],
        "finding_summary": {
            "by_category": {
                "dependency": {"raw": 3, "material": 0, "review_required": 3},
                "static": {"raw": 2, "material": 0, "review_required": 2},
                "secret": {"raw": 0, "material": 0, "review_required": 0},
            }
        },
        "scanner_results": [],
        "unavailable_data_notes": [
            "snapshot-bound git clone failed in /tmp/nico-snapshot: cannot fork() for index-pack"
        ],
    }
    return build_decision_grade_assessment(
        repository=IDENTITY["repository"],
        commit_sha=IDENTITY["commit_sha"],
        run_id=IDENTITY["run_id"],
        repo=repository,
        complexity=complexity,
        scan=scan,
    )


def _stages() -> dict[str, dict]:
    assessment = _assessment()
    stages: dict[str, dict] = {
        "authorization_and_scope": {
            "status": "complete",
            "summary": "Authorization and scope were verified.",
            "evidence": {"authorization_confirmed": True, "scope": "authorized_read_only_assessment"},
        },
        "immutable_repository_snapshot": {
            "status": "complete",
            "summary": "One immutable commit was captured.",
            "evidence": {"snapshot_commit_sha": IDENTITY["commit_sha"], "snapshot_id": "snapshot_v5"},
        },
        "evidence_reconciliation_and_scoring": {
            "status": "complete",
            "summary": "Decision-grade score and assurance were reconciled.",
            "assessment": assessment,
            "evidence": {"technical_score": assessment["maturity_signal"]["score"]},
        },
        "six_month_roadmap": {
            "status": "complete",
            "summary": "Owned work packages were sequenced.",
            "roadmap": build_roadmap(assessment),
            "evidence": {"roadmap_window_count": 3},
        },
        "staffing_sequencing_and_cost": {
            "status": "complete",
            "summary": "Role sequencing was retained.",
            "staffing_plan": [
                {"sequence": 1, "role": "Product Engineering Architect", "focus": "Architecture and governance", "estimated_load": "0.5 FTE"},
                {"sequence": 2, "role": "Product Quality Engineer", "focus": "Evidence and acceptance", "estimated_load": "0.5 FTE"},
            ],
            "evidence": {"recommended_role_count": 2},
        },
    }
    for index in range(16):
        stages[f"decision_grade_stage_{index}"] = {
            "status": "complete",
            "summary": f"Bounded stage {index} completed.",
            "evidence": {"retained_record": index},
            "unavailable_data_notes": ["One bounded evidence limitation remains."] if index % 4 == 0 else [],
        }
    return stages


def test_scanner_categories_are_not_misclassified_as_secrets() -> None:
    assessment = _assessment()
    sections = {item["id"]: item for item in assessment["sections"]}
    secrets = sections["secrets_review"]
    dependency = sections["dependency_health"]
    static = sections["static_analysis"]

    assert "raw=0" in " ".join(secrets["evidence"])
    assert not any("5 scanner candidate" in item for item in secrets["findings"])
    assert "gitleaks" in " ".join(secrets["unavailable"]).lower()
    assert "raw=3" in " ".join(dependency["evidence"])
    assert "raw=2" in " ".join(static["evidence"])
    assert secrets["score_band_label"] == "STRONG"
    assert secrets["assurance_label"] == "REVIEW LIMITED"


def test_architecture_hotspots_and_exact_code_locations_are_promoted() -> None:
    assessment = _assessment()
    architecture = next(item for item in assessment["sections"] if item["id"] == "architecture_debt")
    evidence = " ".join(architecture["evidence"])
    register = assessment["findings_register"]

    assert "247" in evidence
    assert "53" in evidence
    assert "21.5%" in evidence
    assert any(item["location"].startswith("apps/web/app/assessment/MidSectionReview.tsx:1") for item in register)
    assert any(item["location"].startswith("nico/example.py:10") for item in register)


def test_report_package_is_decision_grade_and_page_truth_matches() -> None:
    result = build_comprehensive_report_package(identity=IDENTITY, stage_results=_stages())
    assert result["status"] == "complete", result.get("reason")
    report = result["report_package"]
    raw = base64.b64decode(report["pdf_base64"], validate=True)
    reader = PdfReader(io.BytesIO(raw))
    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert report["pdf_page_count"] == len(reader.pages)
    assert 0 < report["core_report_page_count"] < report["final_package_page_count"]
    assert report["final_package_page_count"] >= 25
    assert len(reader.outline) > 0
    assert "Executive Risk Register" in pdf_text
    assert "Architecture and Complexity" in pdf_text
    assert "REVIEW LIMITED" in pdf_text
    assert not re.search(r"\b(?:GREEN|YELLOW|RED)\s*[·•-]\s*\d{1,3}/100", pdf_text)
    assert "/tmp/" not in pdf_text
    assert "Cannot fork" not in pdf_text

    assert "| Control | Technical score | Band | Evidence assurance |" in report["markdown"]
    assert "<h2>Executive Risk Register</h2>" in report["html"]
    assert report["findings_csv"].startswith("id,priority,category,title,location")
    assert report["evidence_ledger_csv"].startswith("stage_id,stage_title,stage_status")
    quality = report["report_quality_contract"]
    assert quality["score_band_separated_from_assurance"] is True
    assert quality["secret_category_isolated"] is True
    assert quality["named_architecture_hotspots"] is True
    assert quality["structured_findings_register"] is True
    assert quality["executable_roadmap"] is True
    assert quality["limitation_accounting_explicit"] is True
    assert quality["human_review_required"] is True
    assert quality["client_delivery_allowed"] is False


def test_decision_grade_binding_is_the_production_bootstrap_path() -> None:
    source = BOOTSTRAP.read_text(encoding="utf-8")
    assert "install_decision_grade_binding" in source
    assert source.index("report_binding = install_decision_grade_binding()") < source.index(
        "native_providers = install_native_comprehensive_providers(target)"
    )


def test_binding_installs_all_decision_grade_controls() -> None:
    status = install_decision_grade_binding()
    assert status["bound"] is True
    assert status["canonical_scoring_bound"] is True
    assert status["repository_evidence_samples_bound"] is True
    assert status["secret_category_isolated"] is True
    assert status["score_band_separated_from_assurance"] is True
    assert status["structured_findings_register"] is True
    assert status["named_architecture_hotspots"] is True
    assert status["executable_roadmap"] is True
    assert status["machine_readable_csv_exports"] is True
    assert status["pdf_outline_bookmarks"] is True
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False
