from __future__ import annotations

import base64
import gzip
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

VERSION = "nico.candidate-technical-triage.v1"
_TRIAGE_FILE = (
    Path(__file__).resolve().parents[1]
    / "evidence"
    / "candidate-triage"
    / "technical-triage-9c876ba4.json.gz.b64"
)
_SAFE_LINEAGE_STATUSES = frozenset(
    {"carried_forward_exact", "carried_forward_location_changed"}
)
_ALLOWED_VERDICTS = frozenset({"confirmed", "not_actionable", "needs_review"})
_ALLOWED_PROPOSALS = frozenset(
    {"approved_or_nonblocking", "excluded_test_only", "review_required", "verified_material"}
)


def load_default_technical_triage(path: Path | None = None) -> dict[str, Any]:
    source = path or _TRIAGE_FILE
    encoded = "".join(source.read_text(encoding="utf-8").split())
    padding = "=" * (-len(encoded) % 4)
    decoded = gzip.decompress(
        base64.b64decode(encoded + padding, validate=True)
    ).decode("utf-8")
    payload = json.loads(decoded)

    if payload.get("s") != VERSION:
        raise ValueError("candidate_technical_triage_schema_invalid")
    records = payload.get("x")
    if not isinstance(records, list) or len(records) != int(payload.get("n") or -1):
        raise ValueError("candidate_technical_triage_count_invalid")
    codebook = payload.get("q")
    if not isinstance(codebook, Mapping):
        raise ValueError("candidate_technical_triage_codebook_invalid")
    if payload.get("h") != "pending":
        raise ValueError("candidate_technical_triage_human_approval_invalid")
    if payload.get("d") is not False:
        raise ValueError("candidate_technical_triage_delivery_boundary_invalid")
    if payload.get("runtime_validation_performed") is not False:
        raise ValueError("candidate_technical_triage_runtime_claim_invalid")

    seen: set[str] = set()
    verdicts: Counter[str] = Counter()
    proposals: Counter[str] = Counter()
    for raw in records:
        if not isinstance(raw, list) or len(raw) != 3:
            raise ValueError("candidate_technical_triage_record_invalid")
        candidate_id, rationale_code, rank = raw
        candidate = str(candidate_id or "").strip()
        code = str(rationale_code or "").strip()
        if not candidate or candidate in seen or code not in codebook:
            raise ValueError("candidate_technical_triage_identity_invalid")
        seen.add(candidate)

        entry = codebook[code]
        if not isinstance(entry, list) or len(entry) != 9:
            raise ValueError("candidate_technical_triage_codebook_entry_invalid")
        verdict = str(entry[0] or "")
        proposal = str(entry[2] or "")
        if verdict not in _ALLOWED_VERDICTS or proposal not in _ALLOWED_PROPOSALS:
            raise ValueError("candidate_technical_triage_disposition_invalid")
        if verdict == "needs_review" and not isinstance(rank, int):
            raise ValueError("candidate_technical_triage_rank_missing")
        if verdict != "needs_review" and rank is not None:
            raise ValueError("candidate_technical_triage_rank_unexpected")
        verdicts[verdict] += 1
        proposals[proposal] += 1

    expected_verdicts = {
        str(key): int(value)
        for key, value in dict(payload.get("v") or {}).items()
    }
    expected_proposals = {
        str(key): int(value)
        for key, value in dict(payload.get("p") or {}).items()
    }
    if dict(verdicts) != expected_verdicts:
        raise ValueError("candidate_technical_triage_verdict_counts_invalid")
    if dict(proposals) != expected_proposals:
        raise ValueError("candidate_technical_triage_proposal_counts_invalid")
    return payload


def _triage_rows(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    codebook = payload.get("q") if isinstance(payload.get("q"), Mapping) else {}
    output: dict[str, dict[str, Any]] = {}
    for raw in payload.get("x") or []:
        candidate_id, rationale_code, rank = raw
        entry = list(codebook[str(rationale_code)])
        (
            verdict,
            confidence,
            proposal,
            source_type,
            rationale,
            boundary_assessment,
            recommended_next_step,
            proof_gaps,
            rank_basis,
        ) = entry
        output[str(candidate_id)] = {
            "technical_triage_verdict": str(verdict),
            "technical_triage_confidence": str(confidence),
            "technical_triage_proposed_disposition": str(proposal),
            "technical_triage_source_type": str(source_type),
            "technical_triage_rationale_code": str(rationale_code),
            "technical_triage_rationale": str(rationale),
            "technical_triage_boundary_assessment": str(boundary_assessment),
            "technical_triage_recommended_next_step": str(recommended_next_step),
            "technical_triage_proof_gaps": deepcopy(proof_gaps if isinstance(proof_gaps, list) else []),
            "technical_triage_exploitability_stack_rank": rank,
            "technical_triage_rank_basis": str(rank_basis or ""),
        }
    return output


def apply_candidate_technical_triage(
    register: Mapping[str, Any],
    *,
    triage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach prior technical-triage proposals without carrying human approval.

    Only exact or semantic cross-SHA lineage can inherit a prior technical result.
    Evidence-changed and newly observed candidates remain new technical-review work.
    Canonical dispositions and score-driving totals are intentionally unchanged.
    """

    output = deepcopy(dict(register))
    current = [
        deepcopy(dict(item))
        for item in output.get("findings") or []
        if isinstance(item, Mapping)
    ]
    try:
        source = dict(triage or load_default_technical_triage())
        indexed = _triage_rows(source)
    except Exception as exc:
        output["technical_triage"] = {
            "artifact_schema": VERSION,
            "status": "unavailable",
            "reason": type(exc).__name__,
            "technical_triage_available": False,
            "human_approval_status": "pending",
            "human_approval_carried_forward": False,
            "client_delivery_allowed": False,
            "score_effect": "none",
        }
        return output

    verdict_counts: Counter[str] = Counter()
    proposal_counts: Counter[str] = Counter()
    imported = 0
    current_review = 0

    for record in current:
        lineage_status = str(record.get("lineage_status") or "")
        prior_candidate_id = str(record.get("prior_candidate_id") or "")
        record["technical_triage_status"] = "current_evidence_review_required"
        record["technical_triage_human_approval_status"] = "pending"
        record["technical_triage_human_approval_carried_forward"] = False
        record["technical_triage_client_delivery_allowed"] = False

        if lineage_status not in _SAFE_LINEAGE_STATUSES or not prior_candidate_id:
            current_review += 1
            continue
        prior = indexed.get(prior_candidate_id)
        if prior is None:
            current_review += 1
            continue

        record.update(deepcopy(prior))
        record["technical_triage_status"] = "imported_proposal"
        record["technical_triage_source_candidate_id"] = prior_candidate_id
        record["technical_triage_source_commit_sha"] = str(source.get("c") or "")
        record["technical_triage_runtime_validation_performed"] = False
        record["technical_review_required"] = (
            record.get("technical_triage_verdict") != "not_actionable"
        )
        imported += 1
        verdict_counts[str(record.get("technical_triage_verdict") or "")] += 1
        proposal_counts[
            str(record.get("technical_triage_proposed_disposition") or "")
        ] += 1

    output["findings"] = current
    output["technical_triage"] = {
        "artifact_schema": VERSION,
        "status": "complete",
        "technical_triage_available": True,
        "source_schema": str(source.get("source_schema") or ""),
        "source_sha256": str(source.get("source_sha256") or ""),
        "source_target_commit_sha": str(source.get("c") or ""),
        "source_candidate_count": int(source.get("n") or 0),
        "imported_candidate_count": imported,
        "current_evidence_review_required": current_review,
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "proposal_counts": dict(sorted(proposal_counts.items())),
        "safe_lineage_statuses": sorted(_SAFE_LINEAGE_STATUSES),
        "evidence_changed_candidates_inherit_prior_triage": False,
        "new_candidates_inherit_prior_triage": False,
        "runtime_validation_performed": False,
        "human_approval_status": "pending",
        "human_approval_carried_forward": False,
        "disposition_authority": "proposal_only_pending_authorized_human_review",
        "client_delivery_allowed": False,
        "score_effect": "none_canonical_dispositions_and_totals_unchanged",
    }
    output["canonical_digest_sha256"] = hashlib.sha256(
        json.dumps(
            current,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return output


__all__ = [
    "VERSION",
    "apply_candidate_technical_triage",
    "load_default_technical_triage",
]
