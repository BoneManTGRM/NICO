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
TERMINAL_PHASES = {"Se requiere revisión experta", "Revisión interna requerida"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
    terminal = payload.get("terminal")
    if not isinstance(terminal, Mapping):
        raise ValueError("source_proof_terminal_missing")
    marker = source_binding_marker(
        source_workflow_run_id,
        source_workflow_run_attempt,
    )
    canonical_truth_sha256 = _text(payload.get("canonical_truth_sha256")).lower()
    checks = {
        "source_proof_schema_invalid": _text(payload.get("artifact_schema")) == SOURCE_SCHEMA,
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
        "source_proof_intake_count_invalid": int(payload.get("start_request_count") or -1)
        == 1,
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
    failures = sorted(code for code, passed in checks.items() if not passed)
    if failures:
        raise ValueError(",".join(failures))
    return {
        "artifact_schema": VERSION,
        "status": "validated",
        "source_artifact_schema": SOURCE_SCHEMA,
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
