from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pypdf import PdfReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
EXTENDER = ROOT / "scripts" / "four_phase_completion_report_extender_v1.py"
WORKFLOW = ROOT / ".github" / "workflows" / "phase1-completion-bound-report.yml"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path))
    pdf.drawString(48, 750, "NICO Comprehensive Phase 1 and Phase 2 completion-bound source")
    pdf.save()


def _phase3() -> dict:
    return {
        "artifact_schema": "nico.phase3_completion_observation.v1",
        "phase": 3,
        "product": "NICO Comprehensive",
        "one_public_product": True,
        "one_client_report": True,
        "status": "satisfied",
        "implementation": {
            "primary_pull_request": 1174,
            "primary_head_sha": "a" * 40,
            "primary_merge_sha": "b" * 40,
            "parallel_assessment_pipeline_created": False,
            "canonical_scoring_replaced": False,
            "report_pipeline_replaced": False,
        },
        "negative_paths_proven": {
            "repository_tests_do_not_become_runtime_acceptance": True,
            "source_indicators_do_not_become_device_parity": True,
            "missing_authoritative_requirements_remain_missing": True,
            "stakeholder_notes_do_not_become_stakeholder_authority": True,
            "roadmap_remains_framework_until_authorized": True,
            "staffing_does_not_invent_commercial_values": True,
            "internal_placeholder_identity_cannot_be_client_final": True,
        },
        "positive_supplied_evidence_paths_proven": {
            "functional_qa_supplied_results_retained": True,
            "platform_scope_and_observations_ingested": True,
            "authoritative_requirements_classification_retained": True,
            "stakeholder_objectives_and_constraints_retained": True,
            "roadmap_uses_supplied_requirements_and_constraints": True,
            "staffing_role_and_effort_framework_generated_without_rates_or_budget": True,
            "existing_comprehensive_report_sections_receive_structured_evidence": True,
        },
        "human_boundaries": {
            "automation_can_create_human_disposition": False,
            "automation_can_create_final_approval": False,
            "automation_can_authorize_client_delivery": False,
        },
    }


def _phase4() -> dict:
    return {
        "artifact_schema": "nico.phase4_controlled_pilot_readiness_observation.v2",
        "phase": 4,
        "product": "NICO Comprehensive",
        "one_client_report": True,
        "engineering_status": "satisfied",
        "production_operability_durability_status": "satisfied",
        "controlled_outside_repository_pilot_status": "not_executed",
        "software_contracts": {
            "client_project_scope_identity_retained": True,
            "read_only_repository_access_required": True,
            "immutable_assessed_commit_required": True,
            "every_declared_required_scanner_requires_a_retained_execution": True,
            "required_scanner_failure_blocks_acceptance": True,
            "candidate_lineage_and_technical_triage_required": True,
            "canonical_candidate_and_disposition_ids_reconcile_exactly": True,
            "mandatory_individual_review_must_complete": True,
            "human_approval_is_explicit_and_attributable": True,
            "approval_binds_exact_artifact_digests": True,
            "material_change_invalidates_stale_approval": True,
            "cross_client_project_run_mismatch_blocks_delivery": True,
            "internal_or_test_package_cannot_be_client_final": True,
            "one_report_rule_enforced": True,
        },
        "durability_recovery_validation": {
            "postgres_restart_proof": True,
            "mobile_restart_recovery": True,
            "deployment_transition_survival": True,
            "artifact_retrievability_after_restart": True,
            "reviewer_state_durability": True,
            "approval_state_durability": True,
            "cross_tenant_recovery_isolation": True,
        },
        "security_validation": {
            "repository_authorization": True,
            "read_only_enforcement": True,
            "reviewer_authorization": True,
            "client_project_run_isolation": True,
            "artifact_download_authorization": True,
            "idor_and_identifier_manipulation": True,
            "artifact_and_approval_integrity": True,
            "automation_approval_rejected": True,
        },
        "repository_agnostic_fixtures": [
            "external Python service",
            "external Node/TypeScript application",
            "external mixed Python/TypeScript repository",
        ],
        "human_boundaries": {
            "automation_can_create_final_approval": False,
            "automation_can_authorize_client_delivery": False,
            "real_human_approval_executed": False,
        },
    }


def _status(sha: str) -> dict:
    required = [
        "Vercel",
        "successful-cat - NICO",
        "NICO Mobile Restart Production Proof",
        "NICO iOS WebKit Paint Proof",
        "NICO Spanish Comprehensive Production Proof",
        "NICO Two-Service Production Acceptance",
        "NICO Production Acceptance Green Watch",
    ]
    return {
        "artifact_schema": "nico.phase1-current-head-status.v1",
        "commit_sha": sha,
        "required_contexts": required,
        "contexts": {
            name: {
                "state": "success",
                "description": f"{name} passed",
                "target_url": f"https://github.test/actions/runs/{index + 100}",
            }
            for index, name in enumerate(required)
        },
    }


def _run(tmp_path: Path, *, phase4: dict | None = None) -> subprocess.CompletedProcess[str]:
    sha = "c" * 40
    source_pdf = tmp_path / "phase12.pdf"
    source_manifest = tmp_path / "phase12.manifest.json"
    phase3_path = tmp_path / "phase3.json"
    phase4_path = tmp_path / "phase4.json"
    status_path = tmp_path / "status.json"
    output_pdf = tmp_path / "NICO-COMPREHENSIVE-FOUR-PHASE-ENGINEERING-COMPLETE.pdf"
    output_manifest = tmp_path / "NICO-COMPREHENSIVE-FOUR-PHASE-ENGINEERING-COMPLETE.manifest.json"
    _source_pdf(source_pdf)
    _write_json(
        source_manifest,
        {
            "artifact_schema": "nico.phase1-completion-bound-report.v1",
            "status": "passed",
            "report_product": "NICO COMPREHENSIVE",
            "additional_report_product_created": False,
            "commit_sha": sha,
            "final_report_page_count": 1,
            "phase1_definition_of_done": [{"item": index, "status": "passed"} for index in range(1, 10)],
            "phase2_completion": {"software_status": "complete"},
        },
    )
    _write_json(phase3_path, _phase3())
    _write_json(phase4_path, phase4 or _phase4())
    _write_json(status_path, _status(sha))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [
            sys.executable,
            str(EXTENDER),
            "--source-pdf",
            str(source_pdf),
            "--source-manifest",
            str(source_manifest),
            "--phase3-json",
            str(phase3_path),
            "--phase4-json",
            str(phase4_path),
            "--status-json",
            str(status_path),
            "--expected-sha",
            sha,
            "--spanish-run-id",
            "201",
            "--green-watch-run-id",
            "202",
            "--output-pdf",
            str(output_pdf),
            "--output-manifest",
            str(output_manifest),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_extender_binds_phase3_and_phase4_into_the_same_comprehensive_report(tmp_path: Path) -> None:
    completed = _run(tmp_path)
    assert completed.returncode == 0, completed.stderr
    output_pdf = tmp_path / "NICO-COMPREHENSIVE-FOUR-PHASE-ENGINEERING-COMPLETE.pdf"
    manifest = json.loads(
        (tmp_path / "NICO-COMPREHENSIVE-FOUR-PHASE-ENGINEERING-COMPLETE.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["artifact_schema"] == "nico.four-phase-completion-bound-report.v1"
    assert manifest["status"] == "passed"
    assert manifest["additional_report_product_created"] is False
    assert manifest["phase3_completion"]["status"] == "satisfied"
    assert manifest["phase4_engineering_completion"]["engineering_status"] == "satisfied"
    assert manifest["production_operability_durability_status"] == "satisfied"
    assert manifest["controlled_outside_repository_pilot_status"] == "not_executed"
    assert manifest["human_approval_status"] == "pending"
    assert manifest["client_delivery_allowed"] is False
    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) >= 3
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Phase 3 Broader Professional Assessment Closure" in text
    assert "PHASE 3 ENGINEERING SATISFIED" in text
    assert "Phase 4 Production Client-Delivery Engineering Closure" in text
    assert "PHASE 4 ENGINEERING: SATISFIED" in text
    assert "REAL OUTSIDE-REPOSITORY PILOT NOT EXECUTED" in text
    assert "HUMAN APPROVAL PENDING" in text
    assert "CLIENT DELIVERY BLOCKED" in text


def test_extender_fails_closed_if_real_pilot_is_fabricated(tmp_path: Path) -> None:
    phase4 = _phase4()
    phase4["controlled_outside_repository_pilot_status"] = "executed"
    completed = _run(tmp_path, phase4=phase4)
    assert completed.returncode != 0
    assert "pilot status is not truthfully separated" in completed.stderr


def test_existing_completion_workflow_requires_all_four_phase_evidence_and_spanish_gate() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/phase1_completion_report_binder_v1.py" in source
    assert "scripts/four_phase_completion_report_extender_v1.py" in source
    assert "docs/phase3-completion-observation.json" in source
    assert "docs/phase4-controlled-pilot-readiness-observation.json" in source
    assert "NICO Spanish Comprehensive Production Proof" in source
    assert "NICO Production Acceptance Green Watch" in source
    assert "NICO-COMPREHENSIVE-FOUR-PHASE-ENGINEERING-COMPLETE.pdf" in source
    assert 'manifest["phase3_completion"]["status"] == "satisfied"' in source
    assert 'manifest["phase4_engineering_completion"]["engineering_status"] == "satisfied"' in source
    assert 'manifest["controlled_outside_repository_pilot_status"] == "not_executed"' in source
    assert 'manifest["human_approval_status"] == "pending"' in source
    assert 'manifest["client_delivery_allowed"] is False' in source
