from __future__ import annotations

from copy import deepcopy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.phase1_completion_report_contract_v1 import dod_rows, extract_report, validate_external

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "phase1-completion-bound-report.yml"
BINDER = ROOT / "scripts" / "phase1_completion_report_binder_v1.py"
PHASE2_OBSERVATION = ROOT / "docs" / "phase2-completion-observation.json"


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
    Only an authorized human reviewer may approve the exact immutable PDF, canonical JSON, and detached evidence manifest digests.
    Automation cannot change this package to APPROVED FINAL or CLIENT DELIVERY AUTHORIZED.
    """


def evidence(release_sha: str, assessed_sha: str | None = None):
    assessed_sha = assessed_sha or release_sha
    acceptance = {
        "artifact_schema": "nico.unified_live_acceptance.v1",
        "status": "passed",
        "expected_deployed_sha": release_sha,
        "assessed_commit_sha": assessed_sha,
        "passes_required": 2,
        "passes_completed": 2,
        "proof": {"exact_sha_bound": True, "two_passes": True},
    }
    audit = {
        "artifact_schema": "nico.phase1-structured-artifact-audit.v1",
        "status": "passed",
        "commit_sha": assessed_sha,
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
        "expected_sha": release_sha,
        "final_release_observation": {"release_sha": release_sha},
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
        "commit_sha": release_sha,
        "required_contexts": required,
        "contexts": {
            name: {"state": "success", "description": f"{name} passed"}
            for name in required
        },
    }
    return acceptance, audit, release, status


_V2_PROOF_FIELDS = (
    "exact_release_sha", "exact_ui_contract", "production_environment",
    "cache_busted_no_store_requests", "english_copy_contract",
    "spanish_copy_contract", "workspace_contract",
    "specialist_authentication_gate", "preview_deployment_rejected",
)


def frontend_v2_evidence(sha: str) -> dict:
    """Shape emitted after both locale routes prove the specialist sign-in gate."""
    return {
        "artifact_schema": "nico.frontend_production_release_identity.v2",
        "status": "passed", "expected_sha": sha,
        "expected_deployment_environment": "production",
        "expected_ui_contract": "expert-engagement-v2",
        "final_release_observation": {
            "release_sha": sha, "deployment_environment": "production",
            "http_status": 200, "ui_contract": "expert-engagement-v2",
        },
        "proof": {key: True for key in _V2_PROOF_FIELDS},
        "pages": {locale: {
            "verified": True, "authentication_gate_verified": True,
            "workspace_markers_verified": False,
            "presentation_mode": "specialist_authentication_gate",
        } for locale in ("en", "es-MX")},
    }


def test_external_evidence_accepts_v2_authenticated_gate_without_mutating_proof():
    release_sha, assessed_sha = "a" * 40, "b" * 40
    acceptance, audit, _, status = evidence(release_sha, assessed_sha)
    release = frontend_v2_evidence(release_sha)
    before = deepcopy((acceptance, audit, release, status))
    validate_external(acceptance, audit, release, status, release_sha, assessed_sha)
    assert (acceptance, audit, release, status) == before


@pytest.mark.parametrize("field", _V2_PROOF_FIELDS)
@pytest.mark.parametrize("invalid_value", [False, "true", None])
def test_v2_frontend_evidence_requires_each_proven_boundary(field, invalid_value):
    sha = "a" * 40
    acceptance, audit, _, status = evidence(sha)
    release = frontend_v2_evidence(sha)
    if invalid_value is None:
        release["proof"].pop(field)
    else:
        release["proof"][field] = invalid_value
    with pytest.raises(ValueError):
        validate_external(acceptance, audit, release, status, sha, sha)


@pytest.mark.parametrize("defect", [
    "unknown_schema", "failed_status", "wrong_expected_sha", "wrong_observed_sha",
    "missing_observation", "malformed_observation", "missing_proof",
    "preview_expected", "preview_observed", "wrong_ui_contract", "failed_http",
])
def test_v2_frontend_evidence_rejects_unproven_release_identity(defect):
    sha = "a" * 40
    acceptance, audit, _, status = evidence(sha)
    release = frontend_v2_evidence(sha)
    if defect == "unknown_schema":
        release["artifact_schema"] = "nico.frontend_production_release_identity.v3"
    elif defect == "failed_status":
        release["status"] = "failed"
    elif defect == "wrong_expected_sha":
        release["expected_sha"] = "b" * 40
    elif defect == "wrong_observed_sha":
        release["final_release_observation"]["release_sha"] = "b" * 40
    elif defect == "missing_observation":
        release.pop("final_release_observation")
    elif defect == "malformed_observation":
        release["final_release_observation"] = ["not an observation"]
    elif defect == "missing_proof":
        release.pop("proof")
    elif defect == "preview_expected":
        release["expected_deployment_environment"] = "preview"
    elif defect == "preview_observed":
        release["final_release_observation"]["deployment_environment"] = "preview"
    elif defect == "wrong_ui_contract":
        release["final_release_observation"]["ui_contract"] = "old-contract"
    else:
        release["final_release_observation"]["http_status"] = 503
    with pytest.raises(ValueError):
        validate_external(acceptance, audit, release, status, sha, sha)


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


def test_report_contract_requires_an_explicit_authorized_human_approval_boundary() -> None:
    sha = "4" * 40
    source = report_text(sha).replace(
        "Only an authorized human reviewer may approve the exact immutable PDF, canonical JSON, and detached evidence manifest digests.",
        "Human approval is pending.",
    )

    try:
        extract_report(source, sha)
    except ValueError as exc:
        assert "missing explicit approval" in str(exc)
    else:
        raise AssertionError("A generic pending label must not satisfy the authorized-human approval boundary")


def test_external_evidence_closes_item_nine_fail_closed() -> None:
    sha = "2" * 40
    acceptance, audit, release, status = evidence(sha)
    validate_external(acceptance, audit, release, status, sha, sha)
    status["contexts"]["NICO iOS WebKit Paint Proof"]["state"] = "pending"
    try:
        validate_external(acceptance, audit, release, status, sha, sha)
    except ValueError as exc:
        assert "not successful" in str(exc)
    else:
        raise AssertionError("A pending exact-current-head context must fail closed")


def test_external_evidence_accepts_current_completed_run_two_pass_schema() -> None:
    sha = "5" * 40
    acceptance, audit, release, status = evidence(sha)
    acceptance["artifact_schema"] = (
        "nico.completed-run-two-pass-production-acceptance.v1"
    )

    validate_external(acceptance, audit, release, status, sha, sha)


def test_external_evidence_rejects_unknown_unified_acceptance_schema() -> None:
    sha = "6" * 40
    acceptance, audit, release, status = evidence(sha)
    acceptance["artifact_schema"] = "nico.unknown-production-acceptance.v1"

    try:
        validate_external(acceptance, audit, release, status, sha, sha)
    except ValueError as exc:
        assert "Unified Production Acceptance did not pass" in str(exc)
    else:
        raise AssertionError("An unknown Unified acceptance schema must fail closed")


def test_external_evidence_preserves_distinct_release_and_assessed_commits() -> None:
    release_sha = "7" * 40
    assessed_sha = "8" * 40
    acceptance, audit, release, status = evidence(release_sha, assessed_sha)

    validate_external(
        acceptance,
        audit,
        release,
        status,
        release_sha,
        assessed_sha,
    )

    audit["commit_sha"] = release_sha
    try:
        validate_external(
            acceptance,
            audit,
            release,
            status,
            release_sha,
            assessed_sha,
        )
    except ValueError as exc:
        assert "expected assessed commit" in str(exc)
    else:
        raise AssertionError("The assessed repository identity must fail closed")


def test_workflow_creates_one_post_acceptance_comprehensive_report_with_phase2_truth() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'workflows: ["Unified Production Acceptance"]' in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "SOURCE_RUN_ATTEMPT: ${{ github.event.workflow_run.run_attempt }}" in source
    assert (
        "SOURCE_ARTIFACT_NAME: unified-production-acceptance-${{ github.event.workflow_run.head_sha }}-${{ github.event.workflow_run.id }}-${{ github.event.workflow_run.run_attempt }}"
        in source
    )
    assert "source-acceptance/two-service-live-acceptance.json" in source
    assert 'acceptance["source_workflow_run_attempt"]' in source
    assert 'description.startswith(source_marker + " ")' in source
    assert '"spanish_source_binding": source_marker.removeprefix("source:")' in source
    assert "scripts/phase1_completion_report_binder_v1.py" in source
    assert "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.pdf" in source
    assert 'manifest["release_sha"]' in source
    assert 'manifest["assessed_commit_sha"]' in source
    assert 'manifest["source_report_commit_sha"]' in source
    assert 'manifest["phase1_definition_of_done"][8]["status"] == "passed"' in source
    assert 'phase2 = manifest["phase2_completion"]' in source
    assert 'phase2["software_status"] == "complete"' in source
    assert 'phase2["empirical_specialist_effort_status"] == "not_yet_measured"' in source
    assert 'phase2["empirical_specialist_effort_tracking_issue"] == 1169' in source
    assert 'manifest["additional_report_product_created"] is False' in source
    assert 'manifest["human_approval_status"] == "pending"' in source
    assert 'manifest["client_delivery_allowed"] is False' in source
    assert "docs/phase2-completion-observation.json" in source


def test_phase2_completion_observation_is_truthful_and_does_not_fake_human_time() -> None:
    observation = json.loads(PHASE2_OBSERVATION.read_text(encoding="utf-8"))
    assert observation["artifact_schema"] == "nico.phase2-completion-observation.v1"
    assert observation["software_status"] == "complete"
    assert observation["empirical_efficiency_status"] == "not_yet_measured"
    assert observation["product_boundary"]["one_public_product"] == "NICO Comprehensive"
    assert observation["product_boundary"]["one_client_report"] is True
    assert observation["implementation"]["primary_pull_request"]["number"] == 1166
    assert observation["implementation"]["closure_pull_request"]["number"] == 1170
    assert observation["human_labor_target"]["tracking_issue"] == 1169
    assert observation["human_labor_target"]["synthetic_or_ci_measurement_accepted"] is False
    assert observation["truth_and_approval"]["automation_can_create_human_disposition"] is False
    assert observation["truth_and_approval"]["automation_can_approve_final"] is False
    assert observation["truth_and_approval"]["automation_can_authorize_client_delivery"] is False
    assert observation["phase3_start_authorized_by_this_observation"] is False


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
    assert "Phase 2 software-completion evidence" in completed.stdout
    assert "application requests dependency imported" not in completed.stderr


@pytest.mark.parametrize("release_schema", ["v1", "v2"])
def test_binder_end_to_end_produces_phase1_and_phase2_completion_truth_without_application_startup(tmp_path: Path, release_schema: str) -> None:
    release_sha = "3" * 40
    assessed_sha = "9" * 40
    source_pdf = tmp_path / "source.pdf"
    output_pdf = tmp_path / "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.pdf"
    output_manifest = tmp_path / "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.manifest.json"
    acceptance_path = tmp_path / "acceptance.json"
    audit_path = tmp_path / "audit.json"
    release_path = tmp_path / "release.json"
    status_path = tmp_path / "status.json"

    _write_source_pdf(source_pdf, assessed_sha)
    acceptance, audit, release, status = evidence(release_sha, assessed_sha)
    if release_schema == "v2":
        release = frontend_v2_evidence(release_sha)
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
            "--expected-sha", release_sha,
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
    assert manifest["commit_sha"] == release_sha
    assert manifest["release_sha"] == release_sha
    assert manifest["assessed_commit_sha"] == assessed_sha
    assert manifest["source_report_commit_sha"] == assessed_sha
    assert manifest["structured_audit"]["commit_sha"] == assessed_sha
    assert len(manifest["phase1_definition_of_done"]) == 9
    assert manifest["phase1_definition_of_done"][8]["status"] == "passed"
    phase2 = manifest["phase2_completion"]
    assert phase2["software_status"] == "complete"
    assert phase2["empirical_specialist_effort_status"] == "not_yet_measured"
    assert phase2["empirical_specialist_effort_tracking_issue"] == 1169
    assert [item["pull_request"] for item in phase2["implementation_pull_requests"]] == [1166, 1170]
    assert phase2["source_report_workload"]["human_review_work_units"] == 50
    assert manifest["human_approval_status"] == "pending"
    assert manifest["client_delivery_allowed"] is False

    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) >= 4
    appended = len(reader.pages) - manifest["source_report_page_count"]
    assert appended >= 3
    closure_text = "\n".join(page.extract_text() or "" for page in reader.pages[-appended:])
    assert "9. Required current-head checks pass" in closure_text
    assert "PHASE 1 COMPLETE" in closure_text
    assert "Phase 2 Human Review by Exception Closure" in closure_text
    assert "#1166" in closure_text
    assert "#1170" in closure_text
    assert "Issue #1169" in closure_text
    assert "not_yet_measured" in closure_text
    assert "PHASE 2 SOFTWARE COMPLETE" in closure_text
    assert "HUMAN APPROVAL PENDING" in closure_text
    assert "CLIENT DELIVERY BLOCKED" in closure_text
    assert "application requests dependency imported" not in completed.stderr
