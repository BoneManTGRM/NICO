from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LEGACY_SCRIPT = SCRIPTS / "two_service_live_acceptance.py"
CANONICAL_SCRIPT = SCRIPTS / "two_service_live_acceptance_v3.py"
PRODUCTION_SCRIPT = SCRIPTS / "unified_production_acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
WORKSPACE = ASSESSMENT / "AssessmentWorkspace.tsx"
EVIDENCE = ASSESSMENT / "assessmentEvidence.ts"
TERMINAL_CSS = ROOT / "apps" / "web" / "styles" / "assessment-terminal-mobile.css"


def _module():
    spec = importlib.util.spec_from_file_location("two_service_live_acceptance", LEGACY_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _production_module():
    sys.path.insert(0, str(SCRIPTS))
    try:
        for name in (
            "unified_production_acceptance",
            "two_service_live_acceptance_v3",
            "two_service_live_acceptance_v2",
            "two_service_live_acceptance",
        ):
            sys.modules.pop(name, None)
        return __import__("unified_production_acceptance")
    finally:
        sys.path.remove(str(SCRIPTS))


def test_legacy_runner_retains_backend_tier_compatibility() -> None:
    module = _module()

    assert module.SERVICE_LABELS == {
        "express": "Express",
        "comprehensive": "Comprehensive",
    }
    assert module.START_PATHS == {
        "express": "/api/nico/assessment/express-run",
        "comprehensive": "/api/nico/assessment/comprehensive-intake",
    }
    assert set(module.CONTINUATION_PATTERNS) == {"express", "comprehensive"}


def test_parser_requires_two_consecutive_passes_and_exact_sha(tmp_path: Path) -> None:
    module = _module()
    sha = "a" * 40
    config = module.parse(
        [
            "--frontend-url",
            "https://app.nicoaudit.com",
            "--repository",
            "BoneManTGRM/NICO",
            "--expected-sha",
            sha,
            "--passes",
            "2",
            "--output",
            str(tmp_path / "proof.json"),
        ]
    )

    assert config.frontend_origin == "https://app.nicoaudit.com"
    assert config.expected_sha == sha
    assert config.passes == 2
    with pytest.raises(ValueError, match="two or three"):
        module.parse(
            [
                "--frontend-url",
                "https://app.nicoaudit.com",
                "--repository",
                "BoneManTGRM/NICO",
                "--expected-sha",
                sha,
                "--passes",
                "1",
            ]
        )


def test_report_and_assessment_extractors_use_native_comprehensive_stage() -> None:
    module = _module()
    payload = {
        "record": {
            "stage_results": {
                "final_comprehensive_report_generation": {
                    "assessment": {"maturity_signal": {"level": "Senior", "score": 90}},
                    "report_package": {
                        "service_id": "comprehensive",
                        "report_id": "comprehensive_report_001",
                        "markdown": "# NICO Comprehensive Technical Assessment",
                    },
                }
            }
        }
    }

    assert module.report_package("comprehensive", payload)["report_id"] == "comprehensive_report_001"
    assert module.assessment_payload("comprehensive", payload)["maturity_signal"]["score"] == 90


def test_production_acceptance_prefers_canonical_report_assessment() -> None:
    module = _production_module()
    payload = {
        "record": {
            "stage_results": {
                "evidence_reconciliation_and_scoring": {
                    "assessment": {"maturity_signal": {"level": "Strong", "score": 84}},
                },
                "final_comprehensive_report_generation": {
                    "assessment": {"status": "complete"},
                    "report_package": {
                        "service_id": "comprehensive",
                        "json": {
                            "assessment": {
                                "maturity_signal": {"level": "Strong", "score": 86},
                                "sections": [{"id": "code_audit", "score": 92}],
                            }
                        },
                    },
                },
            }
        }
    }

    selected = module.canonical_assessment_payload("comprehensive", payload)

    assert selected["maturity_signal"]["score"] == 86
    assert selected["sections"][0]["id"] == "code_audit"


def test_terminal_mobile_workspace_surfaces_report_before_long_history() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    evidence = EVIDENCE.read_text(encoding="utf-8")
    css = TERMINAL_CSS.read_text(encoding="utf-8")
    production = PRODUCTION_SCRIPT.read_text(encoding="utf-8")

    action_index = workspace.index('data-assessment-report-actions="true"')
    history_index = workspace.index("stageHistoryLabel")
    assert action_index < workspace.rindex("<ProgressTimeline")
    assert action_index < workspace.rindex("<Scorecard")
    assert history_index < workspace.rindex("<ProgressTimeline")
    assert 'data-assessment-report-ready={reportReady ? "true" : "false"}' in workspace
    assert "canonicalReportAssessment" in evidence
    assert "assessmentCompleteness" in evidence
    assert 'overflow: visible !important' in css
    assert 'data-assessment-report-actions="true"' in css
    assert "canonical_assessment_payload" in production
    assert "report_actions_visible" in production
    assert "canonical_score_verified" in production


def test_canonical_live_proof_matches_semantic_engagement_workspace() -> None:
    legacy_source = CANONICAL_SCRIPT.read_text(encoding="utf-8")
    production = PRODUCTION_SCRIPT.read_text(encoding="utf-8")

    assert "LEGACY_WORKSPACE_SELECTOR" in legacy_source
    for required in (
        'data-workspace="assessment"',
        'data-engagement-type="comprehensive"',
        'data-canonical-assessment="strategic"',
        'data-assessment-primary-action',
        'data-assessment-authorization',
        "Create engagement and capture repository snapshot",
        "Crear encargo y capturar instantánea del repositorio",
        "install_unified_workspace_contract",
        "unified._ExpectedCommitPage.get_by_role = _canonical_get_by_role",
        "acceptance.assessment_payload = canonical_assessment_payload",
        "acceptance.ui_state = canonical_ui_state",
    ):
        assert required in production

    for required in (
        '"public_assessment": "strategic"',
        '"services": ["comprehensive"]',
        '"one_public_assessment": True',
        '"legacy_tier_selector_hidden": True',
        '"markdown_html_pdf_json_parity": True',
        '"comprehensive_depth_verified": True',
        '"post_run_reconnect_identity_preserved": True',
        '"human_review_required": True',
        '"client_delivery_blocked": True',
        'assert all(item["service"] == "comprehensive" for item in runs)',
    ):
        assert required in legacy_source


def test_legacy_report_validation_keeps_depth_and_review_boundaries() -> None:
    source = LEGACY_SCRIPT.read_text(encoding="utf-8")

    for required in (
        '"semantic_contract": {',
        'assert commit == config.expected_sha',
        'assert observed_run_ids == {rid}',
        'assert first_bool(final, "human_review_required") is True',
        'assert first_bool(final, "client_delivery_allowed") is not True',
    ):
        assert required in source


def test_post_merge_workflow_consumes_the_single_run_after_deployment_readiness() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in source
    assert "workflow_run:" in source
    assert "Spanish Comprehensive Production Proof" in source
    assert "github.event.workflow_run.head_branch == 'main'" in source
    assert "statuses: write" in source
    assert "Wait for exact frontend and backend deployments" in source
    assert "Verify production assessment readiness" in source
    assert "/api/nico/diagnostics/comprehensive-runtime" in source
    assert "survives_container_replacement_verified" in source
    assert "Production assessment is not safe to start" in source
    assert "--passes 2" in source
    assert "NICO Two-Service Production Acceptance" in source
    assert 'payload["artifact_schema"] == "nico.completed-run-two-pass-production-acceptance.v1"' in source
    assert 'payload["fresh_assessment_count"] == 0' in source
    assert 'payload["start_request_count"] == 0' in source
    assert 'payload["continuation_post_count"] == 0' in source
    assert 'len(payload["runs"]) == 2' in source
    assert '"state": "success"' in source
    assert '"state": "failure"' in source
