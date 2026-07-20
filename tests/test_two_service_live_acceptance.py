from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"


def _module():
    spec = importlib.util.spec_from_file_location("two_service_live_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_acceptance_has_exactly_two_public_services() -> None:
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


def test_live_proof_checks_language_parity_formats_depth_and_review_boundary() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for required in (
        'main[data-assessment-service-count="2"]',
        '["Express", "Comprehensive"]',
        '["Express", "Integral"]',
        '"markdown_html_pdf_json_parity": True',
        '"comprehensive_depth_verified": True',
        '"post_run_reconnect_identity_preserved": True',
        '"human_review_required": True',
        '"client_delivery_blocked": True',
        'assert pdf["page_count"] >= 30',
        'assert commit == config.expected_sha',
        'assert observed_run_ids == {rid}',
    ):
        assert required in source


def test_post_merge_workflow_waits_for_deployments_and_publishes_status() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in source
    assert "push:" in source
    assert "- main" in source
    assert "statuses: write" in source
    assert "Wait for exact frontend and backend deployments" in source
    assert "--passes 2" in source
    assert "NICO Two-Service Production Acceptance" in source
    assert '"state": "success"' in source
    assert '"state": "failure"' in source
