from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
AUTHORITATIVE_SCRIPT = SCRIPTS / "unified_production_acceptance_authoritative.py"
OBSOLETE_REPAIR_WORKFLOW = (
    ROOT / ".github" / "workflows" / "authoritative-production-acceptance-repair.yml"
)
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

module = importlib.import_module("unified_production_acceptance_authoritative")
SHA = "a" * 40
RUN_ID = "comprun_authoritative"


class _Page:
    url = (
        "https://app.nicoaudit.com/assessment?tier=comprehensive"
        "&expected_commit_sha=" + SHA
        + f"&run_id={RUN_ID}#assessment"
    )

    def evaluate(self, script: str):
        assert 'section[data-assessment-run-state="true"]' in script
        return {
            "phase_label": "Internal review required",
            "message": "Complete",
            "run_id": "",
            "commit_sha": "",
            "scanner": "",
            "review": "",
            "report": "Complete",
            "score": "Moderate · 72/100",
            "page_url": self.url,
        }


def _canonical(status: str = "MODERATE") -> dict:
    return {
        "identity": {"run_id": RUN_ID, "commit_sha": SHA},
        "assessment": {
            "technical_score": 79,
            "canonical_evidence_adjusted_score": 78,
            "maturity_signal": {"technical_score": 79, "presented_score": 79},
            "sections": [
                {
                    "id": "dependency_health",
                    "label": "Dependency / Library Ecosystem",
                    "presented_score": 76,
                    "presented_status": "MODERATE",
                    "status": "moderate",
                    "assurance_status": "evidence_bound",
                },
                {
                    "id": "static_analysis",
                    "label": "Static Analysis",
                    "presented_score": 83,
                    "presented_status": status,
                    "status": status.casefold(),
                    "assurance_status": "review_limited",
                },
            ],
            "scanner_execution_records": [
                {
                    "scanner_name": "bandit",
                    "status": "completed",
                    "completed": True,
                    "verified_complete": True,
                    "findings": [],
                },
                {
                    "scanner_name": "eslint",
                    "status": "completed_with_findings",
                    "completed": True,
                    "verified_complete": True,
                    "findings": [{"rule_id": "no-unused-vars"}],
                },
            ],
        },
    }


def _package(status: str = "MODERATE") -> dict:
    return {
        "json": _canonical(status),
        "markdown": "# AUTOMATED DRAFT\n79/100\n78/100\n",
        "html": "<!doctype html><html><body>79/100 78/100</body></html>",
        "pdf_filename": (
            "nico-comprehensive-AUTOMATED-DRAFT-PENDING-APPROVAL.pdf"
        ),
    }


def test_authoritative_ui_state_uses_exact_url_identity_and_terminal_defaults():
    state = module.authoritative_ui_state(_Page())

    assert state["run_id"] == RUN_ID
    assert state["commit_sha"] == SHA
    assert state["scanner"] == "Complete with disclosed limitations"
    assert state["review"] == "Required"


def test_authoritative_run_service_keeps_reader_bound_for_terminal_read(monkeypatch: pytest.MonkeyPatch):
    sentinel = lambda _page: {"run_id": "legacy"}
    monkeypatch.setattr(module.production.acceptance, "ui_state", sentinel)
    observed = {}

    def fake_run_service(browser, config, pass_number, service):
        observed["reader"] = module.production.acceptance.ui_state
        observed["arguments"] = (browser, config, pass_number, service)
        return {"status": "passed"}

    monkeypatch.setattr(module, "_ORIGINAL_RUN_SERVICE", fake_run_service)

    result = module.authoritative_run_service("browser", "config", 1, "comprehensive")

    assert result == {"status": "passed"}
    assert observed["reader"] is module.authoritative_ui_state
    assert observed["arguments"] == ("browser", "config", 1, "comprehensive")
    assert module.production.acceptance.ui_state is sentinel


def test_install_binds_authoritative_reader_report_validator_and_run_wrapper(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(module.production, "validate_report", lambda *args: {})
    monkeypatch.setattr(module.production, "canonical_ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.acceptance, "ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.unified, "_current_ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.unified._impl, "_safe_ui_state", lambda _page: {})
    monkeypatch.setattr(module.production.unified, "_current_run_service", lambda *args: {})
    monkeypatch.setattr(module.production.unified._impl, "_original_run_service", lambda *args: {})

    module.install_authoritative_identity_reader()

    assert module.production.validate_report is module.authoritative_validate_report
    assert module.production.canonical_ui_state is module.authoritative_ui_state
    assert module.production.acceptance.ui_state is module.authoritative_ui_state
    assert module.production.unified._current_ui_state is module.authoritative_ui_state
    assert module.production.unified._impl._safe_ui_state is module.authoritative_ui_state
    assert module.production.unified._current_run_service is module.authoritative_run_service
    assert module.production.unified._impl._original_run_service is module.authoritative_run_service


def test_authoritative_report_retains_json_markdown_html_and_score_status_parity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package()
    monkeypatch.setattr(
        module,
        "_ORIGINAL_VALIDATE_REPORT",
        lambda _service, _payload, destination: {
            "score": "79/100",
            "canonical_truth_sha256": "c" * 64,
            "pdf": {"path": destination.as_posix(), "sha256": "d" * 64},
            "semantic_contract": {"status": "passed"},
        },
    )
    monkeypatch.setattr(module.production.acceptance, "report_package", lambda *_args: package)
    monkeypatch.setattr(module.production.acceptance, "run_id", lambda _payload: RUN_ID)
    monkeypatch.setattr(module.production.acceptance, "immutable_commit", lambda _payload: SHA)
    pdf = tmp_path / "pass-1-comprehensive.pdf"
    pdf.write_bytes(b"%PDF-test")

    result = module.authoritative_validate_report("comprehensive", {}, pdf)

    assert result["score"] == "79/100"
    assert result["evidence_adjusted_score"] == "78/100"
    assert result["semantic_contract"]["section_status_score_parity_verified"] is True
    assert result["semantic_contract"]["provisional_review_status_contract_verified"] is True
    assert result["semantic_contract"]["single_scanner_status_per_tool_verified"] is True
    assert result["semantic_contract"]["score_clamping_forbidden"] is True
    assert result["section_parity"][1]["status"] == "MODERATE"
    assert result["assessment_semantic_sha256"]
    for key in ("json", "markdown_artifact", "html_artifact"):
        assert Path(result[key]["path"]).is_file()
        assert result[key]["size_bytes"] > 0


def test_authoritative_report_fails_closed_on_scored_not_scored_status(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    package = _package("REVIEW_LIMITED_NOT_SCORED")
    monkeypatch.setattr(module, "_ORIGINAL_VALIDATE_REPORT", lambda *_args: {})
    monkeypatch.setattr(module.production.acceptance, "report_package", lambda *_args: package)
    monkeypatch.setattr(module.production.acceptance, "run_id", lambda _payload: RUN_ID)
    monkeypatch.setattr(module.production.acceptance, "immutable_commit", lambda _payload: SHA)

    with pytest.raises(AssertionError, match="Static Analysis presents 83/100"):
        module.authoritative_validate_report(
            "comprehensive",
            {},
            tmp_path / "pass-comprehensive.pdf",
        )


def test_repeat_run_output_requires_identical_scores_sections_scanners_and_semantic_hash(
    tmp_path: Path,
) -> None:
    report = {
        "score": "79/100",
        "evidence_adjusted_score": "78/100",
        "section_parity": [{"label": "Static Analysis", "score": "83/100", "status": "MODERATE"}],
        "scanner_statuses": [{"scanner_name": "bandit", "status": "completed"}],
        "assessment_semantic_sha256": "s" * 64,
        "canonical_truth_sha256": "c" * 64,
        "semantic_contract": {
            "section_status_score_parity_verified": True,
            "provisional_review_status_contract_verified": True,
            "single_scanner_status_per_tool_verified": True,
            "score_clamping_forbidden": True,
            "compact_evidence_summary_verified": True,
            "automated_draft_language_verified": True,
            "unapproved_finality_absent": True,
        },
    }
    runs = []
    for index in (1, 2):
        copied = json.loads(json.dumps(report))
        copied["canonical_truth_sha256"] = str(index) * 64
        for key, suffix in (
            ("json", ".json"),
            ("markdown_artifact", ".md"),
            ("html_artifact", ".html"),
            ("pdf", ".pdf"),
        ):
            artifact = tmp_path / f"run-{index}{suffix}"
            artifact.write_text("artifact", encoding="utf-8")
            copied[key] = {"path": artifact.as_posix(), "sha256": "a" * 64}
        runs.append({"report": copied})
    output = tmp_path / "acceptance.json"
    output.write_text(json.dumps({"status": "passed", "runs": runs, "proof": {}}), encoding="utf-8")

    module.verify_authoritative_output(output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["proof"]["deterministic_score_pair"] is True
    assert payload["proof"]["deterministic_semantic_assessment_hash"] is True
    assert payload["proof"]["identity_bound_canonical_truth_hashes_retained"] is True
    assert payload["proof"]["provisional_review_status_contract_verified"] is True
    assert payload["proof"]["score_clamping_forbidden"] is True
    assert len(payload["repeat_run_evidence"]["identity_bound_canonical_truth_sha256"]) == 2


def test_authoritative_acceptance_has_no_legacy_locator_or_status_overwrite_workflow() -> None:
    source = AUTHORITATIVE_SCRIPT.read_text(encoding="utf-8")

    assert "collapsed identity" not in source
    assert "_ORIGINAL_UI_STATE" not in source
    assert ".locator(" not in source
    assert not OBSOLETE_REPAIR_WORKFLOW.exists()
