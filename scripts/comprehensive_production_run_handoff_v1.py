#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive-production-run-handoff.v1"
SOURCE_SCHEMA = "nico.spanish_comprehensive_live_acceptance.v3.2"
RECOVERED_SOURCE_SCHEMA = "nico.spanish_comprehensive_existing_run_recovery.v1"
TERMINAL_PHASES = {"Se requiere revisión experta", "Revisión interna requerida"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _positive_decimal(value: Any, *, code: str) -> str:
    candidate = _text(value)
    if not candidate.isdecimal() or int(candidate) <= 0:
        raise ValueError(code)
    return candidate


def source_binding_marker(
    source_workflow_run_id: Any,
    source_workflow_run_attempt: Any,
) -> str:
    run_id = _positive_decimal(
        source_workflow_run_id,
        code="source_workflow_run_id_invalid",
    )
    attempt = _positive_decimal(
        source_workflow_run_attempt,
        code="source_workflow_run_attempt_invalid",
    )
    return f"source:{run_id}:{attempt}"


def require_matching_canonical_truth_digest(*values: Any) -> str:
    normalized = [_text(value).lower() for value in values]
    if not normalized or any(not _SHA256.fullmatch(value) for value in normalized):
        raise ValueError("canonical_truth_digest_missing_or_invalid")
    if len(set(normalized)) != 1:
        raise ValueError("canonical_truth_digest_mismatch")
    return normalized[0]


def canonical_json_sha256(value: Any) -> str:
    """Hash canonical assessment truth with the server's JSON serialization."""

    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def require_canonical_json_digest(value: Any, expected_digest: Any) -> str:
    """Prove a reported canonical digest is bound to the retrieved JSON bytes."""

    return require_matching_canonical_truth_digest(
        canonical_json_sha256(value),
        expected_digest,
    )


def select_source_bound_status(
    statuses: Iterable[Any],
    *,
    context: str,
    source_workflow_run_id: Any,
    source_workflow_run_attempt: Any,
) -> dict[str, str]:
    marker = source_binding_marker(
        source_workflow_run_id,
        source_workflow_run_attempt,
    )
    candidates: list[Mapping[str, Any]] = []
    for value in statuses:
        if not isinstance(value, Mapping):
            continue
        if _text(value.get("context")) != context:
            continue
        if not _text(value.get("description")).startswith(marker + " "):
            continue
        candidates.append(value)
    if not candidates:
        return {"state": "missing", "description": "", "target_url": ""}
    latest = max(
        candidates,
        key=lambda value: (
            _text(value.get("created_at")),
            int(value.get("id") or 0),
        ),
    )
    return {
        "state": _text(latest.get("state") or "unknown").lower(),
        "description": _text(latest.get("description")),
        "target_url": _text(latest.get("target_url")),
    }


def load_source_proof(
    path: Path,
    *,
    expected_sha: str,
    repository: str,
    source_workflow_run_id: str,
    source_workflow_run_attempt: str,
) -> dict[str, Any]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("source_proof_must_be_mapping")
    source_schema = _text(payload.get("artifact_schema"))
    terminal = payload.get("terminal")
    if not isinstance(terminal, Mapping):
        raise ValueError("source_proof_terminal_missing")
    marker = source_binding_marker(
        source_workflow_run_id,
        source_workflow_run_attempt,
    )
    canonical_truth_sha256 = _text(payload.get("canonical_truth_sha256")).lower()
    checks = {
        "source_proof_schema_invalid": source_schema
        in {SOURCE_SCHEMA, RECOVERED_SOURCE_SCHEMA},
        "source_proof_status_invalid": _text(payload.get("status")) == "passed",
        "source_proof_release_sha_mismatch": _text(payload.get("expected_sha")) == expected_sha,
        "source_proof_repository_mismatch": _text(payload.get("repository")).casefold()
        == repository.casefold(),
        "source_proof_workflow_run_id_mismatch": _text(
            payload.get("source_workflow_run_id")
        )
        == _text(source_workflow_run_id),
        "source_proof_workflow_run_attempt_mismatch": _text(
            payload.get("source_workflow_run_attempt")
        )
        == _text(source_workflow_run_attempt),
        "source_proof_binding_mismatch": _text(payload.get("source_binding"))
        == marker.removeprefix("source:"),
        "source_proof_run_id_missing": bool(_text(payload.get("run_id"))),
        "source_proof_canonical_truth_digest_invalid": bool(
            _SHA256.fullmatch(canonical_truth_sha256)
        ),
        "source_proof_canonical_truth_bytes_unproven": payload.get(
            "canonical_truth_digest_computed_from_json"
        )
        is True,
        "source_proof_localized_pdf_hash_unproven": payload.get(
            "localized_pdf_artifact_hash_headers_verified"
        )
        is True,
        "source_proof_localized_read_mutation_unproven": payload.get(
            "terminal_state_unchanged_after_localized_reads"
        )
        is True
        and payload.get("localized_report_mutation_request_count") == 0,
        "source_proof_terminal_run_mismatch": _text(terminal.get("run_id"))
        == _text(payload.get("run_id")),
        "source_proof_terminal_commit_mismatch": _text(terminal.get("commit_sha"))
        == expected_sha,
        "source_proof_terminal_state_invalid": _text(terminal.get("phase"))
        in TERMINAL_PHASES,
        "source_proof_duplicate_intake_unproven": payload.get("duplicate_intake_absent")
        is True,
        "source_proof_bilingual_same_run_unproven": payload.get(
            "same_run_bilingual_pdf_verified"
        )
        is True,
        "source_proof_bilingual_rerun_detected": payload.get(
            "same_run_bilingual_assessment_rerun"
        )
        is False,
        "source_proof_human_review_boundary_missing": payload.get("human_review_required")
        is True,
        "source_proof_delivery_boundary_invalid": payload.get("client_delivery_allowed")
        is False,
    }
    if source_schema == SOURCE_SCHEMA:
        checks.update(
            {
                "source_proof_intake_count_invalid": payload.get(
                    "start_request_count"
                )
                == 1,
            }
        )
    elif source_schema == RECOVERED_SOURCE_SCHEMA:
        initial = payload.get("initial_canonical_state")
        initial = initial if isinstance(initial, Mapping) else {}
        canonical_terminal = payload.get("terminal_canonical_state")
        canonical_terminal = (
            canonical_terminal if isinstance(canonical_terminal, Mapping) else {}
        )
        evidence_ledger_id = _text(payload.get("evidence_ledger_id"))
        source_hash_keys = (
            "source_artifact_digest",
            "failed_source_proof_sha256",
            "failed_source_job_log_sha256",
            "source_script_sha256",
        )
        source_hashes_valid = all(
            _SHA256.fullmatch(_text(payload.get(key)).lower())
            for key in source_hash_keys
        )
        spanish_pdf_sha256 = _text(payload.get("spanish_pdf_sha256")).lower()
        english_pdf_sha256 = _text(payload.get("english_pdf_sha256")).lower()
        checks.update(
            {
                "recovered_source_proof_tool_sha_invalid": bool(
                    _GIT_SHA.fullmatch(_text(payload.get("proof_tool_sha")).lower())
                ),
                "recovered_source_lineage_hashes_invalid": source_hashes_valid,
                "recovered_source_script_flow_unproven": payload.get(
                    "source_script_control_flow_order_verified"
                )
                is True,
                "recovered_source_job_flow_unproven": payload.get(
                    "failed_source_control_flow_reached_running_visibility"
                )
                is True
                and payload.get("failed_source_prior_intake_assertions_completed")
                is True
                and payload.get(
                    "failed_source_running_reload_completed_before_visibility"
                )
                is True
                and payload.get(
                    "source_failure_classified_as_proof_harness_visibility_only"
                )
                is True,
                "recovered_source_intake_lineage_invalid": payload.get(
                    "source_producer_lineage_start_request_count"
                )
                == 1,
                "recovered_source_started_new_assessment": payload.get(
                    "recovery_start_request_count"
                )
                == 0
                and payload.get("fresh_assessment_count_during_recovery") == 0,
                "recovered_source_intake_guard_unproven": payload.get(
                    "intake_route_guard_verified"
                )
                is True,
                "recovered_source_continuation_guard_unproven": payload.get(
                    "uncontrolled_continuation_route_guard_verified"
                )
                is True,
                "recovered_source_explicit_continuation_detected": payload.get(
                    "explicit_same_run_continuation_count"
                )
                == 0
                and payload.get("explicit_same_run_continuation_paths") == [],
                "recovered_source_terminal_ui_mutation_detected": payload.get(
                    "terminal_ui_mutation_attempt_count"
                )
                == 0,
                "recovered_source_client_mutation_unproven": payload.get(
                    "no_client_mutation_terminal_observation"
                )
                is True,
                "recovered_source_identity_flags_unproven": payload.get(
                    "same_run_recovery_verified"
                )
                is True
                and payload.get("same_commit_recovery_verified") is True
                and payload.get("same_evidence_ledger_verified") is True
                and payload.get("exact_run_identity_preserved") is True,
                "recovered_source_evidence_ledger_missing": bool(evidence_ledger_id),
                "recovered_source_initial_run_mismatch": _text(initial.get("run_id"))
                == _text(payload.get("run_id")),
                "recovered_source_initial_repository_mismatch": _text(
                    initial.get("repository")
                ).casefold()
                == repository.casefold(),
                "recovered_source_initial_commit_mismatch": _text(
                    initial.get("commit_sha")
                )
                == expected_sha,
                "recovered_source_initial_ledger_mismatch": _text(
                    initial.get("evidence_ledger_id")
                )
                == evidence_ledger_id,
                "recovered_source_initial_language_mismatch": _text(
                    initial.get("report_language")
                )
                == "es-MX",
                "recovered_source_terminal_run_mismatch": _text(
                    canonical_terminal.get("run_id")
                )
                == _text(payload.get("run_id")),
                "recovered_source_terminal_repository_mismatch": _text(
                    canonical_terminal.get("repository")
                ).casefold()
                == repository.casefold(),
                "recovered_source_terminal_commit_mismatch": _text(
                    canonical_terminal.get("commit_sha")
                )
                == expected_sha,
                "recovered_source_terminal_ledger_mismatch": _text(
                    canonical_terminal.get("evidence_ledger_id")
                )
                == evidence_ledger_id,
                "recovered_source_terminal_state_invalid": canonical_terminal.get(
                    "terminal"
                )
                is True,
                "recovered_source_terminal_review_boundary_invalid": canonical_terminal.get(
                    "human_review_required"
                )
                is True
                and canonical_terminal.get("client_delivery_allowed") is False,
                "recovered_source_terminal_visibility_unproven": payload.get(
                    "terminal_background_foreground_recovery_verified"
                )
                is True,
                "recovered_source_pdf_hashes_invalid": bool(
                    _SHA256.fullmatch(spanish_pdf_sha256)
                    and _SHA256.fullmatch(english_pdf_sha256)
                    and spanish_pdf_sha256 != english_pdf_sha256
                ),
                "recovered_source_five_field_literals_unproven": payload.get(
                    "five_field_literals_verified_in_both_pdfs"
                )
                is True,
                "recovered_source_five_field_summary_unproven": payload.get(
                    "five_fields_consolidated_in_both_client_evidence_summaries"
                )
                is True,
                "recovered_source_intake_evidence_class_invalid": _text(
                    payload.get("source_intake_evidence_class")
                )
                == "immutable_source_control_flow_plus_durable_exact_run_state",
            }
        )
    failures = sorted(code for code, passed in checks.items() if not passed)
    if failures:
        raise ValueError(",".join(failures))
    return {
        "artifact_schema": VERSION,
        "status": "validated",
        "source_artifact_schema": source_schema,
        "source_proof_kind": (
            "existing_run_recovery"
            if source_schema == RECOVERED_SOURCE_SCHEMA
            else "fresh_producer"
        ),
        "source_proof_path": path.as_posix(),
        "source_proof_sha256": hashlib.sha256(raw).hexdigest(),
        "source_workflow_run_id": _text(source_workflow_run_id),
        "source_workflow_run_attempt": _text(source_workflow_run_attempt),
        "source_binding": marker.removeprefix("source:"),
        "release_sha": expected_sha,
        "repository": repository,
        "run_id": _text(payload.get("run_id")),
        "terminal_phase": _text(terminal.get("phase")),
        "terminal_commit_sha": _text(terminal.get("commit_sha")),
        "canonical_truth_sha256": canonical_truth_sha256,
        "producer_start_request_count": 1,
        "same_run_bilingual_pdf_verified": True,
        "same_run_bilingual_assessment_rerun": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the sole production Comprehensive run handoff."
    )
    parser.add_argument("--source-proof", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-workflow-run-id", required=True)
    parser.add_argument("--source-workflow-run-attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = load_source_proof(
        args.source_proof,
        expected_sha=args.expected_sha,
        repository=args.repository,
        source_workflow_run_id=args.source_workflow_run_id,
        source_workflow_run_attempt=args.source_workflow_run_attempt,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
