from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.comprehensive_production_run_handoff_v1 import (
    canonical_json_sha256,
    require_canonical_json_digest,
    require_matching_canonical_truth_digest,
    load_source_proof,
    select_source_bound_status,
    source_binding_marker,
)


SHA = "a" * 40
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
        "client_delivery_allowed": False,
        "terminal": {
            "run_id": "comprun_handoff_exact",
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
    assert result["client_delivery_allowed"] is False


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
        (lambda value: value.update({"client_delivery_allowed": True}), "source_proof_delivery_boundary_invalid"),
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
