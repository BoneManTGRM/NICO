from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.phase1_completion_report_contract_v1 import dod_rows, extract_report, validate_external

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "phase1-completion-bound-report.yml"
BINDER = ROOT / "scripts" / "phase1_completion_report_binder_v1.py"


def report_text(sha: str) -> str:
    return f"""
    NICO Comprehensive Immutable commit: {sha}
    Current-evidence candidates requiring new technical triage: 62; fresh automated triage completed=62.
    Technical triage coverage: 629/629 (100.0%).
    Exact carry-forward: 567; location-changed: 0; evidence-changed: 28.
    Technical triage outcome totals: not_actionable=567, needs_review=62, confirmed=0.
    Individual human attention: 47; grouped-review eligible candidates: 15; grouped human-review clusters: 3; quality-control pool: 214.
    Human review work units: 50 from 62 observations.
    Technical triage remains proposal-only. Authorized human approval remains pending and client delivery remains blocked.
    Candidate workload has no numeric technical-maturity or Evidence-Adjusted score effect.
    Only an authorized reviewer may change the status to APPROVED FINAL and CLIENT DELIVERY AUTHORIZED.
    """


def evidence(sha: str):
    acceptance = {
        "artifact_schema": "nico.unified_live_acceptance.v1",
        "status": "passed",
        "expected_deployed_sha": sha,
        "passes_required": 2,
        "passes_completed": 2,
        "proof": {"exact_sha_bound": True, "two_passes": True},
    }
    audit = {
        "artifact_schema": "nico.phase1-structured-artifact-audit.v1",
        "status": "passed",
        "commit_sha": sha,
        "candidate_count": 629,
        "candidate_register_sha256_expected": "a" * 64,
        "candidate_register_sha256_observed": "a" * 64,
        "cluster_integrity_error_count": 0,
        "score_effect": "none",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "errors": [],
    }
    release = {
        "artifact_schema": "nico.frontend_production_release_identity.v1",
        "status": "passed",
        "expected_sha": sha,
        "final_release_observation": {"release_sha": sha},
    }
    required = [
        "Vercel",
        "successful-cat - NICO",
        "NICO Mobile Restart Production Proof",
        "NICO iOS WebKit Paint Proof",
        "NICO Two-Service Production Acceptance",
    ]
    status = {
        "artifact_schema": "nico.phase1-current-head-status.v1",
        "commit_sha": sha,
        "required_contexts": required,
        "contexts": {
            name: {"state": "success", "description": f"{name} passed"}
            for name in required
        },
    }
    return acceptance, audit, release, status


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_source_pdf(path: Path, sha: str) -> None:
    pdf = canvas.Canvas(str(path))
    text = pdf.beginText(48, 760)
    text.setFont("Helvetica", 8)
    for line in report_text(sha).splitlines():
        if line.strip():
            text.textLine(line.strip())
    pdf.drawText(text)
    pdf.save()


def test_report_contract_covers_items_one_through_eight() -> None:
    sha = "1" * 40
    report = extract_report(report_text(sha), sha)
    assert report["fresh_completed"] == 62
    assert report["coverage_done"] == report["coverage_total"] == 629
    assert report["carry_forward"] == 567
    assert report["work_units"] == 50
    rows = dod_rows(report)
    assert len(rows) == 9
    assert rows[-1][0] == "9. Required current-head checks pass"


def test_external_evidence_closes_item_nine_fail_closed() -> None:
    sha = "2" * 40
    acceptance, audit, release, status = evidence(sha)
    validate_external(acceptance, audit, release, status, sha)
    status["contexts"]["NICO iOS WebKit Paint Proof"]["state"] = "pending"
    try:
        validate_external(acceptance, audit, release, status, sha)
    except ValueError as exc:
        assert "not successful" in str(exc)
    else:
        raise AssertionError("A pending exact-current-head context must fail closed")


def test_workflow_creates_one_post_acceptance_comprehensive_report() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'workflows: ["Unified Production Acceptance"]' in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "scripts/phase1_completion_report_binder_v1.py" in source
    assert "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.pdf" in source
    assert 'manifest["phase1_definition_of_done"][8]["status"] == "passed"' in source
    assert 'manifest["additional_report_product_created"] is False' in source
    assert 'manifest["human_approval_status"] == "pending"' in source
    assert 'manifest["client_delivery_allowed"] is False' in source


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    (tmp_path / "requests.py").write_text(
        'raise RuntimeError("application requests dependency imported")\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path)
    return env


def test_binder_script_isolated_from_application_runtime_dependencies(tmp_path: Path) -> None:
    source = BINDER.read_text(encoding="utf-8")
    assert 'types.ModuleType("nico")' in source
    assert 'sys.modules["nico"] = _nico_package' in source
    assert "_load_support_module(" in source
    assert "from nico." not in source

    completed = subprocess.run(
        [sys.executable, str(BINDER), "--help"],
        cwd=ROOT,
        env=_isolated_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Bind successful Phase 1 acceptance evidence" in completed.stdout
    assert "application requests dependency imported" not in completed.stderr


def test_binder_end_to_end_produces_item_nine_report_without_application_startup(tmp_path: Path) -> None:
    sha = "3" * 40
    source_pdf = tmp_path / "source.pdf"
    output_pdf = tmp_path / "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.pdf"
    output_manifest = tmp_path / "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.manifest.json"
    acceptance_path = tmp_path / "acceptance.json"
    audit_path = tmp_path / "audit.json"
    release_path = tmp_path / "release.json"
    status_path = tmp_path / "status.json"

    _write_source_pdf(source_pdf, sha)
    acceptance, audit, release, status = evidence(sha)
    _write_json(acceptance_path, acceptance)
    _write_json(audit_path, audit)
    _write_json(release_path, release)
    _write_json(status_path, status)

    completed = subprocess.run(
        [
            sys.executable,
            str(BINDER),
            "--source-pdf", str(source_pdf),
            "--acceptance-json", str(acceptance_path),
            "--audit-json", str(audit_path),
            "--release-json", str(release_path),
            "--status-json", str(status_path),
            "--expected-sha", sha,
            "--workflow-run-id", "1001",
            "--mobile-run-id", "1002",
            "--ios-run-id", "1003",
            "--artifact-id", "1004",
            "--artifact-name", "unified-production-acceptance-test",
            "--artifact-digest", "sha256:" + "b" * 64,
            "--acceptance-completed-at", "2026-08-10T00:00:00Z",
            "--output-pdf", str(output_pdf),
            "--output-manifest", str(output_manifest),
        ],
        cwd=ROOT,
        env=_isolated_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert output_pdf.is_file()
    manifest = json.loads(output_manifest.read_text(encoding="utf-8"))
    assert manifest["status"] == "passed"
    assert manifest["commit_sha"] == sha
    assert len(manifest["phase1_definition_of_done"]) == 9
    assert manifest["phase1_definition_of_done"][8]["status"] == "passed"
    assert manifest["human_approval_status"] == "pending"
    assert manifest["client_delivery_allowed"] is False

    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) == 3
    closure_text = "\n".join(page.extract_text() or "" for page in reader.pages[-2:])
    assert "9. Required current-head checks pass" in closure_text
    assert "PHASE 1 COMPLETE" in closure_text
    assert "HUMAN APPROVAL PENDING" in closure_text
    assert "CLIENT DELIVERY BLOCKED" in closure_text
    assert "application requests dependency imported" not in completed.stderr
