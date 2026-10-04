import ast
import hashlib
import json
from pathlib import Path

from scripts.comprehensive_production_run_handoff_v1 import (
    retain_unified_english_pdf,
)


def test_unified_waits_for_review_pdf_reentry_guard_between_real_clicks() -> None:
    source = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    settlement_ms = next(
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name)
            and target.id == "REVIEW_PDF_REENTRY_SETTLEMENT_MS"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, int)
    )
    assert settlement_ms > 1_500
    assert "page.wait_for_timeout(REVIEW_PDF_REENTRY_SETTLEMENT_MS)" in source

    first = source.index("first_pdf = recovery._verify_manifest_and_pdf")
    settlement = source.index("_settle_review_pdf_reentry_guard(page)", first)
    second = source.index("second_pdf = recovery._verify_manifest_and_pdf", settlement)
    assert first < settlement < second


def test_unified_final_canonical_read_avoids_playwright_socket_idle_timeout() -> None:
    source = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    timeout_seconds = next(
        (
            node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "FINAL_CANONICAL_READ_TIMEOUT_SECONDS"
                for target in node.targets
            )
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, int)
        ),
        None,
    )

    assert timeout_seconds is not None
    assert timeout_seconds >= 300
    assert "open_request = open_request or urllib.request.urlopen" in source
    assert "with open_request(" in source
    assert "timeout=FINAL_CANONICAL_READ_TIMEOUT_SECONDS" in source
    assert '"Cache-Control": "no-store"' in source
    assert "response.read()" in source
    assert "require_canonical_json_digest(" in source
    assert "playwright.request.new_context" not in source


def test_unified_reuses_verified_first_pass_truth_before_fresh_final_read() -> None:
    source = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )

    first_pass = source.index("first_pass = _run_pass(")
    second_pass = source.index("second_pass = _run_pass(", first_pass)
    reuse = source.index(
        'verified_canonical_truth=first_pass["canonical_truth"]', second_pass
    )
    fresh_final_read = source.index(
        "canonical, canonical_digest = _read_final_canonical(", reuse
    )

    assert "def _reuse_verified_canonical_truth(" in source
    assert "canonical_truth_digest_computed_from_json" in source
    assert "canonical_truth_reused_from_pass" in source
    assert first_pass < second_pass < reuse < fresh_final_read


def test_unified_retains_exact_source_bound_english_pdf_for_phase1_binder(
    tmp_path: Path,
) -> None:
    pdf_bytes = b"%PDF-1.4\n" + (b"verified-source-pdf\n" * 80)
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    source_dir = tmp_path / "source-proof"
    source_dir.mkdir()
    source_pdf = source_dir / "nico-comprehensive-en-automated-draft.pdf"
    source_pdf.write_bytes(pdf_bytes)
    source_proof = source_dir / "spanish-comprehensive-live-proof.json"
    source_proof.write_text(
        json.dumps(
            {
                "run_id": "comprun_exact_source_pdf",
                "expected_sha": "a" * 40,
                "assessed_commit_sha": "b" * 40,
                "repository": "BoneManTGRM/NICO",
                "same_run_bilingual_pdf_verified": True,
                "same_run_bilingual_assessment_rerun": False,
                "localized_pdf_artifact_hash_headers_verified": True,
                "human_review_required": True,
                "client_delivery_allowed": False,
                "english_pdf_path": f"audit-results/{source_pdf.name}",
                "english_pdf_sha256": pdf_sha256,
            }
        ),
        encoding="utf-8",
    )

    retained = retain_unified_english_pdf(
        source_proof,
        tmp_path / "unified-artifacts",
        run_id="comprun_exact_source_pdf",
        expected_sha="a" * 40,
        repository="BoneManTGRM/NICO",
        expected_download_sha256=pdf_sha256,
    )

    retained_path = Path(retained["path"])
    assert retained_path.name == "pass-2-comprehensive.pdf"
    assert retained_path.read_bytes() == pdf_bytes
    assert retained["sha256"] == pdf_sha256
    assert retained["commit_sha"] == "b" * 40
    assert retained["size_bytes"] == len(pdf_bytes)
    assert retained["human_review_required"] is True
    assert retained["client_delivery_allowed"] is False


# Actual Unified consumer regression for run37170339577/job111341989611.
# Isolated fixtures execute the complete _observe_terminal function; no live
# session, network, assessment creation or report approval is involved.
import types
from copy import deepcopy
from typing import Any

import pytest


_UI_BOOLEAN_FIELDS = (
    "ui_review_pdf_anchor_click_observation_verified",
    "ui_review_pdf_source_artifact_reused",
    "ui_review_pdf_signature_verified",
    "ui_review_pdf_exact_run_response_verified",
    "ui_review_pdf_artifact_hash_header_verified",
    "ui_review_pdf_canonical_truth_digest_verified",
    "ui_review_pdf_original_page_visible_after_action",
    "ui_review_pdf_lifecycle_contract_verified",
    "ui_review_pdf_actual_blob_bytes_verified",
    "ui_review_pdf_response_sha256_verified",
    "ui_review_pdf_single_dispatch_verified",
    "ui_review_pdf_exact_run_filename_verified",
    "ui_review_pdf_exact_run_href_verified",
    "ui_review_pdf_original_assessment_page_preserved",
)


def _observed_ui_fixture() -> dict:
    # Current collector's production contract; values are isolated fixtures.
    return {
        **{field: True for field in _UI_BOOLEAN_FIELDS},
        "ui_review_pdf_user_gesture_anchor_click_count": 1,
        "ui_review_pdf_artifact_evidence_source": "observed-ui-response-and-verified-blob",
        "ui_review_pdf_actual_response_count": 1,
        "ui_review_pdf_target_contract": "same-page-validated-blob-download",
        "ui_review_pdf_download_sha256": "a" * 64,
        "ui_review_pdf_canonical_truth_sha256": "b" * 64,
        "ui_review_pdf_report_language": "es-MX",
        "ui_review_pdf_requested_report_language": "es-MX",
        "ui_review_pdf_action_kind": "localized-draft-pending-approval",
        "ui_review_pdf_network_path": "/api/nico/assessment/comprehensive-run/comprun_fixture/localized-report/es-MX/pdf",
        # A direct Spanish PDF and an English UI download may legitimately differ.
        "ui_review_pdf_matches_preverified_artifact": False,
    }


def _execute_actual_unified_observation(first: dict, second: dict | None = None) -> dict:
    source_path = Path("scripts/completed_run_two_pass_acceptance_v1.py")
    parsed = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(
        node for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name == "_observe_terminal"
    )
    clock = iter((0.0, 91.0))
    downloads = iter((deepcopy(first), deepcopy(second if second is not None else first)))
    namespace = {
        "Page": Any,
        "Any": Any,
        "time": types.SimpleNamespace(monotonic=lambda: next(clock)),
        "recovery": types.SimpleNamespace(
            _observe_terminal_stability=lambda *args, **kwargs: {
                "markdown_report_language": "es-MX",
                "legacy_markdown_get_count": 0,
                "markdown_action_success_count": 2,
            },
            _verify_manifest_and_pdf=lambda *args: next(downloads),
        ),
        "_settle_review_pdf_reentry_guard": lambda page: None,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["_observe_terminal"](
        object(), run_id="comprun_fixture", expected_sha="c" * 40,
        expected_canonical_digest="b" * 64, seconds=90.0,
        requests=[], frontend_origin="https://isolated.invalid",
    )


def test_unified_accepts_real_response_and_blob_contract():
    result = _execute_actual_unified_observation(_observed_ui_fixture())
    assert result["visible_pdf_action_count"] == 2
    assert result["pdf_ui_action_anchor_click_count"] == 2
    assert result["pdf_ui_action_digests_stable"] is True
    assert result["unexpected_request_count_including_pdf_actions"] == 0


@pytest.mark.parametrize("field", _UI_BOOLEAN_FIELDS)
def test_unified_rejects_unverified_ui_observation(field):
    fixture = _observed_ui_fixture()
    fixture[field] = False
    with pytest.raises(AssertionError):
        _execute_actual_unified_observation(fixture)


@pytest.mark.parametrize(
    "field,invalid",
    (
        ("ui_review_pdf_artifact_evidence_source", "exact-sha-spanish-source-proof"),
        ("ui_review_pdf_artifact_evidence_source", "live-exact-artifact-response"),
        ("ui_review_pdf_actual_response_count", 0),
        ("ui_review_pdf_actual_response_count", 2),
        ("ui_review_pdf_actual_response_count", True),
        ("ui_review_pdf_actual_response_count", "1"),
        ("ui_review_pdf_target_contract", "blank-noopener-noreferrer"),
        ("ui_review_pdf_canonical_truth_sha256", "d" * 64),
        ("ui_review_pdf_report_language", "en"),
        ("ui_review_pdf_requested_report_language", "en"),
        ("ui_review_pdf_user_gesture_anchor_click_count", 2),
        ("ui_review_pdf_network_path", ""),
        ("ui_review_pdf_network_path", "/api/nico/assessment/comprehensive-run/comprun_other/localized-report/es-MX/pdf"),
        ("ui_review_pdf_network_path", "/api/nico/assessment/comprehensive-run/comprun_fixture/localized-report/en/pdf"),
        ("ui_review_pdf_action_kind", "approved-pdf"),
    ),
)
def test_unified_rejects_source_only_duplicate_or_wrong_identity(field, invalid):
    fixture = _observed_ui_fixture()
    fixture[field] = invalid
    with pytest.raises(AssertionError):
        _execute_actual_unified_observation(fixture)


@pytest.mark.parametrize(
    "field",
    _UI_BOOLEAN_FIELDS + (
        "ui_review_pdf_artifact_evidence_source",
        "ui_review_pdf_actual_response_count",
        "ui_review_pdf_target_contract",
        "ui_review_pdf_canonical_truth_sha256",
        "ui_review_pdf_report_language",
        "ui_review_pdf_requested_report_language",
        "ui_review_pdf_action_kind",
        "ui_review_pdf_network_path",
    ),
)
def test_unified_rejects_missing_ui_evidence(field):
    fixture = _observed_ui_fixture()
    del fixture[field]
    with pytest.raises(KeyError):
        _execute_actual_unified_observation(fixture)


@pytest.mark.parametrize(
    "field,invalid",
    (
        ("ui_review_pdf_download_sha256", "d" * 64),
        ("ui_review_pdf_canonical_truth_sha256", "d" * 64),
        ("ui_review_pdf_action_kind", "other-action"),
        ("ui_review_pdf_network_path", "/api/nico/assessment/comprehensive-run/comprun_fixture/report/pdf"),
    ),
)
def test_unified_rejects_changed_repeat_observation(field, invalid):
    first = _observed_ui_fixture()
    second = deepcopy(first)
    second[field] = invalid
    with pytest.raises(AssertionError):
        _execute_actual_unified_observation(first, second)
