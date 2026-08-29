from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "unified_production_acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"


def _module():
    spec = importlib.util.spec_from_file_location("unified_production_acceptance_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class _MissingSelector:
    @property
    def first(self):
        return self

    def count(self) -> int:
        return 0


class _HiddenButtons:
    def count(self) -> int:
        return 2

    def nth(self, index: int):
        assert index in {0, 1}
        return self

    def is_hidden(self) -> bool:
        return True


class _HiddenSelector:
    @property
    def first(self):
        return self

    def count(self) -> int:
        return 1

    def get_attribute(self, name: str) -> str | None:
        return "true" if name == "aria-hidden" else None

    def is_hidden(self) -> bool:
        return True

    def locator(self, selector: str):
        assert selector == "button"
        return _HiddenButtons()


class _Workspace:
    def __init__(self, selector) -> None:
        self.selector = selector

    def locator(self, selector: str):
        assert selector == '[aria-label="Assessment type"]'
        return self.selector


def test_report_identity_accepts_legacy_and_polished_titles() -> None:
    module = _module()

    assert module.has_comprehensive_report_identity(
        "NICO Comprehensive Technical Assessment"
    )
    assert module.has_comprehensive_report_identity(
        "NICO COMPREHENSIVE\nDecision-Grade Technical Assessment"
    )


def test_report_identity_requires_complete_semantic_identity() -> None:
    module = _module()

    assert not module.has_comprehensive_report_identity("NICO Comprehensive")
    assert not module.has_comprehensive_report_identity("Decision-Grade Technical Assessment")
    assert not module.has_comprehensive_report_identity("NICO Express Technical Assessment")


def test_draft_only_cover_label_is_valid_only_for_blocked_preapproval_delivery() -> None:
    module = _module()
    text = "FINAL REPORT · PENDING HUMAN APPROVAL · DELIVERY · Draft only"

    result = module.validate_preapproval_delivery_posture(
        text,
        text,
        {"client_delivery_allowed": False},
        {"client_delivery_allowed": False},
    )

    assert result["stale_draft_language_absent"] is True
    assert result["preapproval_delivery_posture_verified"] is True
    assert result["draft_only_delivery_label_present"] is True


def test_draft_only_cover_label_fails_closed_when_delivery_is_authorized() -> None:
    module = _module()
    text = "FINAL REPORT · PENDING HUMAN APPROVAL · DELIVERY · Draft only"

    with pytest.raises(AssertionError):
        module.validate_preapproval_delivery_posture(
            text,
            text,
            {"client_delivery_allowed": True},
            {"client_delivery_allowed": False},
        )


def test_legacy_draft_status_language_remains_rejected() -> None:
    module = _module()
    text = "FINAL REPORT · PENDING HUMAN APPROVAL"

    with pytest.raises(AssertionError, match="stale status"):
        module.validate_preapproval_delivery_posture(
            f"{text} · DRAFT - HUMAN REVIEW REQUIRED",
            text,
            {"client_delivery_allowed": False},
            {"client_delivery_allowed": False},
        )


def test_retired_tier_selector_may_be_completely_removed() -> None:
    module = _module()

    evidence = module.verify_retired_tier_selector(
        _Workspace(_MissingSelector()),
        "en",
    )

    assert evidence == {
        "legacy_selector_hidden": True,
        "legacy_selector_removed": True,
    }


def test_retired_tier_selector_may_remain_fully_hidden() -> None:
    module = _module()

    evidence = module.verify_retired_tier_selector(
        _Workspace(_HiddenSelector()),
        "es-MX",
    )

    assert evidence == {
        "legacy_selector_hidden": True,
        "legacy_selector_removed": False,
    }


def test_workflow_uses_semantic_identity_runner_and_requires_proof() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    completed_runner = Path(
        "scripts/completed_run_two_pass_acceptance_v1.py"
    ).read_text(encoding="utf-8")

    assert "scripts/unified_production_acceptance.py" in source
    assert "scripts/unified_production_acceptance_authoritative.py" in source
    assert "python scripts/completed_run_two_pass_acceptance_v1.py" in source
    assert "same_immutable_completed_run" in completed_runner
    assert 'proof["visible_pdf_action_count"] = 2' in completed_runner
    assert 'item["ui_review_pdf_user_gesture_anchor_click_count"] == 1' in completed_runner
    assert 'item["ui_review_pdf_anchor_click_observation_verified"] is True' in completed_runner
    assert 'item["ui_review_pdf_source_artifact_reused"] is True' in completed_runner
    assert 'item["ui_review_pdf_artifact_hash_header_verified"] is True' in completed_runner
    assert 'item["ui_review_pdf_canonical_truth_digest_verified"] is True' in completed_runner
    assert 'item["ui_review_pdf_lifecycle_contract_verified"] is True' in completed_runner
    assert 'item["ui_review_pdf_network_path"]' in completed_runner
    assert 'proof["pdf_ui_action_anchor_click_count"] = pdf_anchor_click_count' in completed_runner
    assert 'first_pdf["ui_review_pdf_download_sha256"]' in completed_runner
    assert 'second_pdf["ui_review_pdf_download_sha256"]' in completed_runner
    assert "_review_locale_surface(page, locale, run_id)" in completed_runner
    assert 'assert not posts, posts' in completed_runner
    assert 'assert not unexpected, unexpected' in completed_runner
    assert 'proof["legacy_markdown_get_count"] == 0' in completed_runner
    assert 'proof["markdown_action_success_count"] == 2' in completed_runner
    assert "--passes 2" in source
    assert "--observation-seconds 90" in source
    assert 'item["observation"]["visible_pdf_action_count"] == 2' in source
    assert 'item["observation"]["pdf_ui_action_anchor_click_count"] == 2' in source
    assert 'len(item["observation"]["pdf_ui_action_proofs"]) == 2' in source
    assert 'item["professional_review_locale_preserved"] is True' in source
    assert "--source-proof source-proof/spanish-comprehensive-live-proof.json" in source
    assert '--source-workflow-run-attempt "${SOURCE_RUN_ATTEMPT}"' in source
    assert "unified-production-acceptance-${{ github.event.workflow_run.head_sha }}-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "Wait for exact frontend and backend deployments" in source


def test_runner_patches_validation_and_selector_proof_before_execution() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "acceptance.validate_report = validate_report" in source
    assert "unified._verify_unified_language_parity = verify_unified_language_parity" in source
    assert "legacy_selector_removed" in source
    assert "return unified.main(argv)" in source
    assert '"human_review_required": True' not in source
    assert '"client_delivery_allowed": True' not in source
    assert 'preapproval_delivery_posture_verified' in source
