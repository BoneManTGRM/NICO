from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

from nico.full_assessment_complexity_evidence import _analyze_python


ROOT = Path(__file__).resolve().parents[1]
USES_PATTERN = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_PATTERN = re.compile(r"^[^/@]+/[^/@]+(?:/[^@]+)?@[0-9a-f]{40}$")
PYTHON_HOTSPOTS = {
    "nico/comprehensive_decision_grade_markdown_v5.py": "_build_markdown",
    "nico/comprehensive_premium_pdf_v6.py": "_build_pdf",
    "nico/comprehensive_decision_grade_report_v5.py": "build_comprehensive_report_package",
    "nico/typescript_ast_complexity_v1.py": "_build_complexity",
}
TYPESCRIPT_HOTSPOTS = {
    "apps/web/app/assessment/AssessmentWorkspace.tsx": "AssessmentWorkspace",
    "apps/web/app/operations/final-review/FinalReviewWorkspace.tsx": "FinalReviewWorkspace",
    "apps/web/app/full-run/page.tsx": "FullRunPage",
    "apps/web/app/page.tsx": "Page",
}


def test_all_repository_workflow_action_references_are_immutable() -> None:
    mutable: list[str] = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), 1):
            match = USES_PATTERN.match(line)
            if not match:
                continue
            reference = match.group(1)
            if reference.startswith("./"):
                continue
            if not FULL_SHA_PATTERN.fullmatch(reference):
                mutable.append(f"{path.relative_to(ROOT)}:{line_number}: {reference}")

    assert not mutable, "Mutable GitHub Action references remain:\n" + "\n".join(mutable)


def test_all_report_named_python_hotspots_are_below_target() -> None:
    for relative, function_name in PYTHON_HOTSPOTS.items():
        path = ROOT / relative
        analysis = _analyze_python(relative, path.read_text(encoding="utf-8"))
        functions = {
            item["name"]: item
            for item in analysis.get("functions") or []
            if isinstance(item, dict) and item.get("name")
        }
        measured = functions[function_name]
        assert measured["cyclomatic_complexity"] <= 30, measured
        assert measured["loc"] < 80, measured
        assert measured["loc_method"] == "function_residual_physical_lines_excluding_nested_definitions_v2"


def test_all_report_named_typescript_hotspots_are_below_target() -> None:
    payload = {
        "files": {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in TYPESCRIPT_HOTSPOTS
        }
    }
    completed = subprocess.run(
        ("node", str(ROOT / "scripts" / "typescript_ast_metrics.cjs")),
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        cwd=ROOT,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    artifact = json.loads(completed.stdout)
    assert artifact["status"] == "complete", artifact
    assert artifact.get("parse_failures") == [], artifact

    analyses = {item["path"]: item for item in artifact["analyses"]}
    for relative, function_name in TYPESCRIPT_HOTSPOTS.items():
        functions = {
            item["name"]: item
            for item in analyses[relative].get("functions") or []
            if isinstance(item, dict) and item.get("name")
        }
        measured = functions[function_name]
        assert measured["cyclomatic_complexity"] <= 30, measured
        assert measured["loc"] < 80, measured
        assert measured["loc_method"] == "function_residual_physical_lines_excluding_nested_functions_v2"


def test_phase5_report_truth_modules_parse_and_keep_scores_evidence_bound() -> None:
    for relative in ("nico/phase5_report_truth_v1.py", "nico/phase5_report_truth_v2.py"):
        path = ROOT / relative
        ast.parse(path.read_text(encoding="utf-8"), filename=relative)

    source = (ROOT / "nico" / "phase5_report_truth_v1.py").read_text(encoding="utf-8")
    assert '"exclude_from_maturity": True' in source
    assert '"client_delivery_allowed"] = False' in source
    assert "Only exact-SHA retained evidence changes report outcomes" in source


def test_phase5_machine_readable_delta_is_real_and_fail_closed() -> None:
    from nico.comprehensive_decision_grade_report_v5 import _phase5_outcome_csv

    assessment = {
        "phase5_verified_outcomes": {
            "scanner_status_changes": {
                "bandit": {"before": "failed", "after": "completed"},
            },
            "complexity_changes": {
                "_build_pdf": {
                    "before": 116,
                    "after": 17,
                    "delta": -99,
                    "evidence": {
                        "path": "nico/comprehensive_premium_pdf_v6.py",
                        "line": 194,
                        "method": "python_ast",
                    },
                }
            },
            "ci_history_classification_visible": True,
            "tls_verify_disabled_finding_open": False,
            "unobserved_baseline_scanners": ["eslint"],
        },
        "ci_history_classification": {
            "historical_reliability": {
                "classified_counts": {
                    "success": 8,
                    "genuine_failure": 1,
                    "superseded_cancellation": 2,
                }
            }
        },
    }
    csv_text = _phase5_outcome_csv(assessment)

    assert "scanner,bandit,failed,completed,status changed" in csv_text
    assert "complexity,_build_pdf,116,17,-99" in csv_text
    assert "ci_history,classified workflow outcomes,raw non-success count" in csv_text
    assert "code_risk,tls_verify_disabled,open in Phase 5 baseline,not present in executable exact-SHA finding ledger" in csv_text
    assert "unobserved,eslint,baseline status retained,no authoritative current exact-SHA record,not counted as improvement" in csv_text
