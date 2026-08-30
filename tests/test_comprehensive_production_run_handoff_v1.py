from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.comprehensive_production_run_handoff_v1 import (
    RECOVERED_SOURCE_SCHEMA,
    canonical_json_sha256,
    require_canonical_json_digest,
    require_matching_canonical_truth_digest,
    load_source_proof,
    select_source_bound_status,
    source_binding_marker,
)


SHA = "a" * 40
PROOF_TOOL_SHA = "b" * 40
REPOSITORY = "BoneManTGRM/NICO"
SOURCE_RUN_ID = "123456"
SOURCE_RUN_ATTEMPT = "2"
CANONICAL_TRUTH_SHA256 = "c" * 64


def test_canonical_json_digest_uses_server_serialization_and_fails_on_tampering() -> None:
    canonical = {"unicode": "Proyecto Ñandú", "nested": {"b": 2, "a": 1}}
    digest = canonical_json_sha256(canonical)

    assert require_canonical_json_digest(canonical, digest) == digest
    with pytest.raises(ValueError, match="canonical_truth_digest_mismatch"):
        require_canonical_json_digest(
            {**canonical, "nested": {"b": 3, "a": 1}},
            digest,
        )


def _proof() -> dict:
    return {
        "artifact_schema": "nico.spanish_comprehensive_live_acceptance.v3.2",
        "status": "passed",
        "expected_sha": SHA,
        "repository": REPOSITORY,
        "source_workflow_run_id": SOURCE_RUN_ID,
        "source_workflow_run_attempt": SOURCE_RUN_ATTEMPT,
        "source_binding": f"{SOURCE_RUN_ID}:{SOURCE_RUN_ATTEMPT}",
        "run_id": "comprun_handoff_exact",
        "canonical_truth_sha256": CANONICAL_TRUTH_SHA256,
        "canonical_truth_digest_computed_from_json": True,
        "localized_pdf_artifact_hash_headers_verified": True,
        "terminal_state_unchanged_after_localized_reads": True,
        "localized_report_mutation_request_count": 0,
        "start_request_count": 1,
        "duplicate_intake_absent": True,
        "same_run_bilingual_pdf_verified": True,
        "same_run_bilingual_assessment_rerun": False,
        "human_review_required": True,
        "human_review_completed": False,
        "approval_status": "pending_human_approval",
        "review_decision_absent": True,
        "approved_final_absent": True,
        "client_delivery_allowed": False,
        "delivery_status": "blocked",
        "delivery_authorization_absent": True,
        "approved_delivery_package_absent": True,
        "accepted_edition_absent": True,
        "terminal": {
            "run_id": "comprun_handoff_exact",
            "commit_sha": SHA,
            "phase": "Se requiere revisión experta",
        },
    }


def _recovered_proof() -> dict:
    run_id = "comprun_" + "1" * 32
    evidence_ledger_id = "ledger_exact_recovered_run"
    return {
        "artifact_schema": RECOVERED_SOURCE_SCHEMA,
        "status": "passed",
        "expected_sha": SHA,
        "proof_tool_sha": PROOF_TOOL_SHA,
        "repository": REPOSITORY,
        "source_workflow_run_id": SOURCE_RUN_ID,
        "source_workflow_run_attempt": SOURCE_RUN_ATTEMPT,
        "source_binding": f"{SOURCE_RUN_ID}:{SOURCE_RUN_ATTEMPT}",
        "source_artifact_digest": "d" * 64,
        "failed_source_proof_sha256": "e" * 64,
        "failed_source_job_log_sha256": "f" * 64,
        "source_script_sha256": "1" * 64,
        "source_script_control_flow_order_verified": True,
        "failed_source_control_flow_reached_running_visibility": True,
        "failed_source_prior_intake_assertions_completed": True,
        "failed_source_running_reload_completed_before_visibility": True,
        "source_failure_classified_as_proof_harness_visibility_only": True,
        "source_producer_lineage_start_request_count": 1,
        "recovery_start_request_count": 0,
        "fresh_assessment_count_during_recovery": 0,
        "duplicate_intake_absent": True,
        "intake_route_guard_verified": True,
        "uncontrolled_continuation_route_guard_verified": True,
        "blocked_ui_continuation_attempt_count": 0,
        "blocked_ui_continuation_attempt_paths": [],
        "explicit_same_run_continuation_count": 0,
        "explicit_same_run_continuation_paths": [],
        "terminal_ui_mutation_attempt_count": 0,
        "no_client_mutation_terminal_observation": True,
        "same_run_recovery_verified": True,
        "same_commit_recovery_verified": True,
        "same_evidence_ledger_verified": True,
        "exact_run_identity_preserved": True,
        "evidence_ledger_id": evidence_ledger_id,
        "run_id": run_id,
        "canonical_truth_sha256": CANONICAL_TRUTH_SHA256,
        "canonical_truth_digest_computed_from_json": True,
        "localized_pdf_artifact_hash_headers_verified": True,
        "terminal_state_unchanged_after_localized_reads": True,
        "localized_report_mutation_request_count": 0,
        "same_run_bilingual_pdf_verified": True,
        "same_run_bilingual_assessment_rerun": False,
        "spanish_pdf_sha256": "2" * 64,
        "english_pdf_sha256": "3" * 64,
        "five_field_literals_verified_in_both_pdfs": True,
        "five_fields_consolidated_in_both_client_evidence_summaries": True,
        "source_intake_evidence_class": (
            "immutable_source_control_flow_plus_durable_exact_run_state"
        ),
        "terminal_background_foreground_recovery_verified": True,
        "human_review_required": True,
        "human_review_completed": False,
        "approval_status": "pending_human_approval",
        "review_decision_absent": True,
        "approved_final_absent": True,
        "client_delivery_allowed": False,
        "delivery_status": "blocked",
        "delivery_authorization_absent": True,
        "approved_delivery_package_absent": True,
        "accepted_edition_absent": True,
        "initial_canonical_state": {
            "run_id": run_id,
            "repository": REPOSITORY,
            "commit_sha": SHA,
            "evidence_ledger_id": evidence_ledger_id,
            "report_language": "es-MX",
            "terminal": False,
            "human_review_required": True,
            "human_review_completed": False,
            "approval_status": "pending_human_approval",
            "review_decision_absent": True,
            "client_delivery_allowed": False,
            "delivery_status": "blocked",
            "delivery_authorization_absent": True,
            "approved_delivery_package_absent": True,
            "accepted_edition_absent": True,
        },
        "terminal_canonical_state": {
            "run_id": run_id,
            "repository": REPOSITORY,
            "commit_sha": SHA,
            "evidence_ledger_id": evidence_ledger_id,
            "terminal": True,
            "status": "review_required",
            "human_review_required": True,
            "human_review_completed": False,
            "approval_status": "pending_human_approval",
            "review_decision_absent": True,
            "client_delivery_allowed": False,
            "delivery_status": "blocked",
            "delivery_authorization_absent": True,
            "approved_delivery_package_absent": True,
            "accepted_edition_absent": True,
        },
        "terminal": {
            "run_id": run_id,
            "commit_sha": SHA,
            "phase": "Se requiere revisión experta",
        },
    }


def _write(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "spanish-comprehensive-live-proof.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_source_proof_binds_exact_run_sha_and_workflow(tmp_path: Path) -> None:
    path = _write(tmp_path, _proof())

    result = load_source_proof(
        path,
        expected_sha=SHA,
        repository=REPOSITORY,
        source_workflow_run_id=SOURCE_RUN_ID,
        source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
        expected_proof_tool_sha=PROOF_TOOL_SHA,
    )

    assert result["status"] == "validated"
    assert result["run_id"] == "comprun_handoff_exact"
    assert result["release_sha"] == SHA
    assert result["source_workflow_run_id"] == SOURCE_RUN_ID
    assert result["source_workflow_run_attempt"] == SOURCE_RUN_ATTEMPT
    assert result["source_binding"] == f"{SOURCE_RUN_ID}:{SOURCE_RUN_ATTEMPT}"
    assert result["canonical_truth_sha256"] == CANONICAL_TRUTH_SHA256
    assert len(result["source_proof_sha256"]) == 64
    assert result["human_review_required"] is True
    assert result["human_review_completed"] is False
    assert result["approval_status"] == "pending_human_approval"
    assert result["review_decision_absent"] is True
    assert result["accepted_edition_absent"] is True
    assert result["client_delivery_allowed"] is False
    assert result["delivery_status"] == "blocked"


def test_valid_existing_run_recovery_is_a_strict_handoff_source(
    tmp_path: Path,
) -> None:
    payload = _recovered_proof()
    path = _write(tmp_path, payload)

    result = load_source_proof(
        path,
        expected_sha=SHA,
        repository=REPOSITORY,
        source_workflow_run_id=SOURCE_RUN_ID,
        source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
        expected_proof_tool_sha=PROOF_TOOL_SHA,
    )

    assert result["status"] == "validated"
    assert result["source_artifact_schema"] == RECOVERED_SOURCE_SCHEMA
    assert result["source_proof_kind"] == "existing_run_recovery"
    assert result["proof_tool_sha"] == PROOF_TOOL_SHA
    assert result["run_id"] == payload["run_id"]
    assert result["producer_start_request_count"] == 1
    assert result["same_run_bilingual_assessment_rerun"] is False
    assert result["human_review_required"] is True
    assert result["human_review_completed"] is False
    assert result["approval_status"] == "pending_human_approval"
    assert result["review_decision_absent"] is True
    assert result["accepted_edition_absent"] is True
    assert result["client_delivery_allowed"] is False
    assert result["delivery_status"] == "blocked"


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        (
            lambda value: value.update({"fresh_assessment_count_during_recovery": 1}),
            "recovered_source_started_new_assessment",
        ),
        (
            lambda value: value.update(
                {
                    "blocked_ui_continuation_attempt_count": 999,
                    "blocked_ui_continuation_attempt_paths": [
                        "/api/nico/assessment/comprehensive-run/example/continue"
                    ],
                }
            ),
            "recovered_source_blocked_ui_continuation_detected",
        ),
        (
            lambda value: value.update(
                {
                    "explicit_same_run_continuation_count": 1,
                    "explicit_same_run_continuation_paths": ["/continue"],
                }
            ),
            "recovered_source_explicit_continuation_detected",
        ),
        (
            lambda value: value["terminal_canonical_state"].update(
                {"evidence_ledger_id": "different-ledger"}
            ),
            "recovered_source_terminal_ledger_mismatch",
        ),
        (
            lambda value: value.update({"failed_source_job_log_sha256": "invalid"}),
            "recovered_source_lineage_hashes_invalid",
        ),
        (
            lambda value: value.update({"english_pdf_sha256": "2" * 64}),
            "recovered_source_pdf_hashes_invalid",
        ),
        (
            lambda value: value.update(
                {"source_script_control_flow_order_verified": False}
            ),
            "recovered_source_script_flow_unproven",
        ),
        (
            lambda value: value["terminal_canonical_state"].update(
                {"human_review_completed": True}
            ),
            "recovered_source_terminal_review_boundary_invalid",
        ),
        (
            lambda value: value["terminal_canonical_state"].update(
                {"review_decision": {"decision": "approved"}}
            ),
            "recovered_source_terminal_review_boundary_invalid",
        ),
    ),
)
def test_existing_run_recovery_handoff_fails_closed(
    tmp_path: Path,
    mutation,
    code: str,
) -> None:
    payload = deepcopy(_recovered_proof())
    mutation(payload)

    with pytest.raises(ValueError, match=code):
        load_source_proof(
            _write(tmp_path, payload),
            expected_sha=SHA,
            repository=REPOSITORY,
            source_workflow_run_id=SOURCE_RUN_ID,
            source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
            expected_proof_tool_sha=PROOF_TOOL_SHA,
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    (
        (lambda value: value.update({"expected_sha": "b" * 40}), "source_proof_release_sha_mismatch"),
        (lambda value: value.update({"repository": "OtherOrg/other"}), "source_proof_repository_mismatch"),
        (lambda value: value.update({"run_id": ""}), "source_proof_run_id_missing"),
        (
            lambda value: value.update({"source_workflow_run_id": "999999"}),
            "source_proof_workflow_run_id_mismatch",
        ),
        (
            lambda value: value.update({"source_workflow_run_attempt": "1"}),
            "source_proof_workflow_run_attempt_mismatch",
        ),
        (
            lambda value: value.update({"source_binding": "123456:1"}),
            "source_proof_binding_mismatch",
        ),
        (
            lambda value: value.update({"canonical_truth_sha256": "not-a-digest"}),
            "source_proof_canonical_truth_digest_invalid",
        ),
        (
            lambda value: value.update(
                {"canonical_truth_digest_computed_from_json": False}
            ),
            "source_proof_canonical_truth_bytes_unproven",
        ),
        (lambda value: value["terminal"].update({"commit_sha": "b" * 40}), "source_proof_terminal_commit_mismatch"),
        (lambda value: value["terminal"].update({"phase": "running"}), "source_proof_terminal_state_invalid"),
        (lambda value: value.update({"start_request_count": 2}), "source_proof_intake_count_invalid"),
        (lambda value: value.update({"same_run_bilingual_assessment_rerun": True}), "source_proof_bilingual_rerun_detected"),
        (lambda value: value.update({"human_review_completed": True}), "source_proof_human_review_completion_invalid"),
        (lambda value: value.update({"approval_status": "approved_final"}), "source_proof_approval_boundary_invalid"),
        (lambda value: value.update({"review_decision": {"decision": "approved"}}), "source_proof_approval_boundary_invalid"),
        (lambda value: value.update({"client_delivery_allowed": True}), "source_proof_delivery_boundary_invalid"),
        (lambda value: value.update({"delivery_status": "authorized"}), "source_proof_delivery_boundary_invalid"),
        (lambda value: value.update({"delivery_authorization": {"authorized": True}}), "source_proof_delivery_boundary_invalid"),
        (lambda value: value.update({"approved_delivery_package": {"status": "complete"}}), "source_proof_approved_delivery_package_boundary_invalid"),
        (lambda value: value.update({"accepted_edition_absent": False}), "source_proof_accepted_edition_boundary_invalid"),
        (lambda value: value.update({"accepted_edition": {"accepted_edition": True}}), "source_proof_accepted_edition_boundary_invalid"),
        (lambda value: value["terminal"].update({"accepted_edition": {}}), "source_proof_terminal_authority_boundary_invalid"),
        (lambda value: value["terminal"].update({"review_decision": {}}), "source_proof_terminal_authority_boundary_invalid"),
        (lambda value: value["terminal"].update({"delivery_authorization": {}}), "source_proof_terminal_authority_boundary_invalid"),
        (lambda value: value["terminal"].update({"approved_delivery_package": {}}), "source_proof_terminal_authority_boundary_invalid"),
        (lambda value: value.update({"record": {"review_decision": {}}}), "source_proof_record_authority_boundary_invalid"),
        (lambda value: value.update({"record": [{"review_decision": {}}]}), "source_proof_record_authority_boundary_invalid"),
    ),
)
def test_invalid_source_proof_fails_closed(tmp_path: Path, mutation, code: str) -> None:
    payload = deepcopy(_proof())
    mutation(payload)

    with pytest.raises(ValueError, match=code):
        load_source_proof(
            _write(tmp_path, payload),
            expected_sha=SHA,
            repository=REPOSITORY,
            source_workflow_run_id=SOURCE_RUN_ID,
            source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
            expected_proof_tool_sha=PROOF_TOOL_SHA,
        )


def test_recovered_proof_tool_sha_is_bound_to_trusted_checkout(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, _recovered_proof())

    with pytest.raises(ValueError, match="recovered_source_proof_tool_sha_mismatch"):
        load_source_proof(
            path,
            expected_sha=SHA,
            repository=REPOSITORY,
            source_workflow_run_id=SOURCE_RUN_ID,
            source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
            expected_proof_tool_sha="c" * 40,
        )

    with pytest.raises(ValueError, match="expected_proof_tool_sha_invalid"):
        load_source_proof(
            path,
            expected_sha=SHA,
            repository=REPOSITORY,
            source_workflow_run_id=SOURCE_RUN_ID,
            source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
            expected_proof_tool_sha="not-a-git-sha",
        )


@pytest.mark.parametrize(
    ("run_id", "attempt", "code"),
    (
        ("", "1", "source_workflow_run_id_invalid"),
        ("abc", "1", "source_workflow_run_id_invalid"),
        ("123", "0", "source_workflow_run_attempt_invalid"),
        ("123", "two", "source_workflow_run_attempt_invalid"),
    ),
)
def test_source_binding_requires_positive_run_id_and_attempt(
    run_id: str,
    attempt: str,
    code: str,
) -> None:
    with pytest.raises(ValueError, match=code):
        source_binding_marker(run_id, attempt)


def test_status_selection_cannot_reuse_success_from_an_older_attempt() -> None:
    context = "NICO Mobile Restart Production Proof"
    statuses = [
        {
            "id": 20,
            "context": context,
            "state": "success",
            "description": "source:123456:1 mobile proof passed",
            "created_at": "2026-08-28T12:00:00Z",
        },
        {
            "id": 21,
            "context": context,
            "state": "pending",
            "description": "source:123456:2 mobile proof running",
            "created_at": "2026-08-28T12:01:00Z",
        },
    ]

    selected = select_source_bound_status(
        statuses,
        context=context,
        source_workflow_run_id=SOURCE_RUN_ID,
        source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
    )

    assert selected["state"] == "pending"
    assert selected["description"].startswith("source:123456:2 ")


def test_status_selection_fails_closed_when_only_an_old_attempt_exists() -> None:
    selected = select_source_bound_status(
        [
            {
                "id": 20,
                "context": "NICO Mobile Restart Production Proof",
                "state": "success",
                "description": "source:123456:1 mobile proof passed",
                "created_at": "2026-08-28T12:00:00Z",
            }
        ],
        context="NICO Mobile Restart Production Proof",
        source_workflow_run_id=SOURCE_RUN_ID,
        source_workflow_run_attempt=SOURCE_RUN_ATTEMPT,
    )

    assert selected == {
        "state": "missing",
        "description": "",
        "target_url": "",
    }


def test_canonical_truth_digest_requires_all_projections_to_match() -> None:
    assert require_matching_canonical_truth_digest(
        CANONICAL_TRUTH_SHA256,
        CANONICAL_TRUTH_SHA256.upper(),
        CANONICAL_TRUTH_SHA256,
    ) == CANONICAL_TRUTH_SHA256


@pytest.mark.parametrize(
    "values",
    (
        (CANONICAL_TRUTH_SHA256, ""),
        (CANONICAL_TRUTH_SHA256, "d" * 64),
        (CANONICAL_TRUTH_SHA256, "not-a-digest"),
    ),
)
def test_canonical_truth_digest_fails_closed_on_missing_malformed_or_drifted_values(
    values: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="canonical_truth_digest"):
        require_matching_canonical_truth_digest(*values)


def test_all_consumers_abort_intake_and_continuation_mutations() -> None:
    mobile = Path("scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")
    desktop = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )

    for source in (mobile, desktop):
        assert 'path == "/api/nico/assessment/comprehensive-intake"' in source
        assert 'path.endswith("/continue")' in source
        assert 'route.abort("blockedbyclient")' in source
        assert "continuation_post_count" in source
        assert "start_request_count" in source


def test_workflow_consumers_bind_recovered_proof_to_checked_out_tool_sha() -> None:
    consumers = (
        Path("scripts/completed_run_two_pass_acceptance_v1.py"),
        Path("scripts/mobile_restart_live_acceptance_v1.py"),
    )
    workflows = (
        Path(".github/workflows/two-service-production-acceptance.yml"),
        Path(".github/workflows/mobile-restart-production-proof.yml"),
        Path(".github/workflows/ios-webkit-paint-proof.yml"),
    )

    for path in consumers:
        source = path.read_text(encoding="utf-8")
        assert 'parser.add_argument("--expected-proof-tool-sha", required=True)' in source
        assert "expected_proof_tool_sha=args.expected_proof_tool_sha" in source
    for path in workflows:
        source = path.read_text(encoding="utf-8")
        assert 'PROOF_TOOL_SHA="$(git rev-parse HEAD)"' in source
        assert '--expected-proof-tool-sha "${PROOF_TOOL_SHA}"' in source


def test_desktop_and_webkit_acceptance_cover_visible_actions_and_spanish_recovery() -> None:
    desktop = Path("scripts/completed_run_two_pass_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    mobile = Path("scripts/mobile_restart_live_acceptance_v1.py").read_text(
        encoding="utf-8"
    )
    ios_workflow = Path(".github/workflows/ios-webkit-paint-proof.yml").read_text(
        encoding="utf-8"
    )

    assert "first_pdf = recovery._verify_manifest_and_pdf" in desktop
    assert "second_pdf = recovery._verify_manifest_and_pdf" in desktop
    assert 'proof["visible_pdf_action_count"] = 2' in desktop
    assert "_review_locale_surface(page, locale, run_id)" in desktop
    assert 'parser.add_argument("--ui-locale", choices=("en", "es-MX")' in mobile
    assert 'assessment_path = "/es/assessment" if args.ui_locale == "es-MX"' in mobile
    assert "_mobile_review_locale_surface" in mobile
    assert "--ui-locale es-MX" in ios_workflow
    assert 'payload["real_device_tested"] is False' in ios_workflow


def test_unified_serializes_bounded_markdown_before_regenerated_pdf_dispatches() -> None:
    path = Path("scripts/completed_run_two_pass_acceptance_v1.py")
    source = path.read_text(encoding="utf-8")
    observe_start = source.index("def _observe_terminal(")
    observe_end = source.index("\ndef ", observe_start + 1)
    observe = source[observe_start:observe_end]

    markdown_stability = observe.index("proof = recovery._observe_terminal_stability(")
    first_pdf = observe.index("first_pdf = recovery._verify_manifest_and_pdf")
    second_pdf = observe.index("second_pdf = recovery._verify_manifest_and_pdf")
    assert markdown_stability < first_pdf < second_pdf

    main_start = source.index("def main(")
    main = source[main_start:]
    source_locale_pass = main.index("first_pass = _run_pass(")
    regenerated_locale_pass = main.index(
        "second_pass = _run_pass(", source_locale_pass
    )
    runs_assignment = main.index(
        "runs = [first_pass, second_pass]", regenerated_locale_pass
    )
    source_pass = main[source_locale_pass:regenerated_locale_pass]
    regenerated_pass = main[regenerated_locale_pass:runs_assignment]
    assert 'pass_number=1, locale="es-MX"' in source_pass
    assert "pass_number=2" in regenerated_pass
    assert 'locale="en"' in regenerated_pass
    assert (
        'verified_canonical_truth=first_pass["canonical_truth"]'
        in regenerated_pass
    )
    assert source_locale_pass < regenerated_locale_pass < runs_assignment


def test_review_locale_proofs_wait_for_client_projection_before_asserting() -> None:
    consumers = (
        (
            Path("scripts/completed_run_two_pass_acceptance_v1.py"),
            "_review_locale_surface",
        ),
        (
            Path("scripts/mobile_restart_live_acceptance_v1.py"),
            "_mobile_review_locale_surface",
        ),
    )

    for path, function_name in consumers:
        source = path.read_text(encoding="utf-8")
        start = source.index(f"def {function_name}(")
        end = source.index("\ndef ", start + 1)
        helper = source[start:end]

        projection_wait = helper.index("page.wait_for_function(")
        language_read = helper.index("document_language = str(")
        assert projection_wait < language_read
        assert "document.documentElement.lang" in helper
        assert "main[data-review-contract='accepted-edition-v2'] h1" in helper
        assert "expectedHeading" in helper


def test_desktop_acceptance_waits_for_authored_locale_projection_before_reading() -> None:
    path = Path("scripts/completed_run_two_pass_acceptance_v1.py")
    source = path.read_text(encoding="utf-8")
    start = source.index("def _locale_surface(")
    end = source.index("\ndef ", start + 1)
    helper = source[start:end]

    projection_wait = helper.index("page.wait_for_function(")
    surface_read = helper.index("value = page.evaluate(")
    assert projection_wait < surface_read
    assert 'main[data-workspace="assessment"]' in helper
    assert "workspace.innerText" in helper
    assert "expectedMarker" in helper
    assert (
        'marker = "Madurez técnica" if expected_spanish else "Technical maturity"'
        in helper
    )
    assert "Technical identity" not in helper
    assert "Identidad técnica" not in helper

    workspace_source = Path(
        "apps/web/app/assessment/AssessmentWorkspace.tsx"
    ).read_text(encoding="utf-8")
    desktop_start = workspace_source.index("function renderDesktopResult()")
    desktop_end = workspace_source.index("function renderStatePanel()", desktop_start)
    desktop_renderer = workspace_source[desktop_start:desktop_end]
    assert "copy.technicalMaturityLabel" in desktop_renderer
