from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive-candidate-identity.v1.2"
MODEL = "stable-per-candidate-count-only-identities.v1"
_MARKER = "__nico_comprehensive_candidate_identity_v1__"
_RECONCILIATION_MARKER = "__nico_truth_reconciled_register_v7__"

_QUALITY_KEYS = (
    "exact_source",
    "source_path",
    "payload_without_source",
    "count_only",
)
_DISPOSITION_TOTAL_KEYS = {
    "verified_material": "material",
    "review_required": "review_required",
    "approved_or_nonblocking": "approved_or_nonblocking",
    "excluded_test_only": "excluded_test_only",
}
_TOTAL_KEYS = (
    "raw",
    "material",
    "review_required",
    "approved_or_nonblocking",
    "excluded_test_only",
    *_QUALITY_KEYS,
)


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _evidence_quality(record: Mapping[str, Any]) -> str:
    quality = str(record.get("evidence_quality") or "").strip()
    return quality if quality in _QUALITY_KEYS else "payload_without_source"


def _retention_state(record: Mapping[str, Any], quality: str) -> str:
    explicit = str(record.get("raw_payload_retention_state") or "").strip()
    if quality == "count_only":
        return "count_only"
    return explicit or "retained"


def _expanded_totals(records: list[dict[str, Any]]) -> dict[str, int]:
    totals = dict.fromkeys(_TOTAL_KEYS, 0)
    for record in records:
        count = _integer(record.get("occurrence_count"))
        disposition_key = _DISPOSITION_TOTAL_KEYS.get(
            str(record.get("disposition") or "")
        )
        quality = _evidence_quality(record)
        totals["raw"] += count
        if disposition_key:
            totals[disposition_key] += count
        totals[quality] += count
    return totals


def expand_candidate_identities(register: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(register))
    source = [
        deepcopy(dict(item))
        for item in output.get("findings") or []
        if isinstance(item, Mapping)
    ]
    expanded: list[dict[str, Any]] = []
    for record in source:
        count = max(1, _integer(record.get("occurrence_count")))
        quality = _evidence_quality(record)
        retention_state = _retention_state(record, quality)
        if count == 1:
            item = deepcopy(record)
            item["candidate_id"] = item.get("candidate_id") or item.get("finding_id")
            item["occurrence_count"] = 1
            item["aggregate_occurrence_count"] = 1
            item["evidence_quality"] = quality
            item["raw_payload_retention_state"] = retention_state
            expanded.append(item)
            continue

        aggregate_fingerprint = str(record.get("raw_fingerprint") or "")
        original_evidence = str(record.get("evidence") or "")
        for index in range(1, count + 1):
            fingerprint = _digest(
                {
                    "aggregate_fingerprint": aggregate_fingerprint,
                    "scanner": record.get("scanner"),
                    "category": record.get("category"),
                    "disposition": record.get("disposition"),
                    "exact_commit_sha": record.get("exact_commit_sha"),
                    "ordinal": index,
                    "population": count,
                }
            )
            item = deepcopy(record)
            item.update(
                {
                    "candidate_id": f"NICO-CANDIDATE-{fingerprint[:20].upper()}",
                    "finding_id": f"NICO-CANDIDATE-{fingerprint[:20].upper()}",
                    "raw_fingerprint": fingerprint,
                    "occurrence_count": 1,
                    "aggregate_occurrence_count": count,
                    "aggregate_candidate_ordinal": index,
                    "aggregate_candidate_population": count,
                    "aggregate_source_fingerprint": aggregate_fingerprint,
                    "evidence_quality": quality,
                    "raw_payload_retention_state": retention_state,
                    "candidate_identity_model": MODEL,
                    "human_review_required": record.get("disposition")
                    == "review_required",
                }
            )
            if quality == "count_only":
                item["evidence"] = (
                    f"Count-only candidate {index} of {count} for scanner "
                    f"{record.get('scanner')} and disposition "
                    f"{record.get('disposition')}. The raw candidate payload was "
                    "unavailable; identity is stable for this exact commit, scanner, "
                    "disposition, and ordinal."
                )
            else:
                # A detailed source record can legitimately have occurrence_count > 1
                # after exact duplicate normalization. Per-candidate IDs must not turn
                # retained source evidence into count-only evidence or claim that raw
                # payloads were unavailable.
                item["evidence"] = original_evidence
                item["aggregate_identity_note"] = (
                    f"Candidate {index} of {count} shares the retained normalized "
                    "source evidence for this duplicate group."
                )
            item["evidence_digest_sha256"] = _digest(item["evidence"])
            item["supporting_evidence_digest_sha256"] = item[
                "evidence_digest_sha256"
            ]
            expanded.append(item)

    expanded.sort(
        key=lambda item: (
            str(item.get("category") or ""),
            str(item.get("scanner") or ""),
            str(item.get("disposition") or ""),
            str(item.get("source_path") or ""),
            _integer(item.get("line")),
            str(item.get("candidate_id") or item.get("finding_id") or ""),
        )
    )
    totals = output.get("totals") if isinstance(output.get("totals"), Mapping) else {}
    raw_total = _integer(totals.get("raw"))
    recomputed_totals = _expanded_totals(expanded)
    totals_match = all(
        _integer(totals.get(key)) == recomputed_totals[key] for key in _TOTAL_KEYS
    )
    output["findings"] = expanded
    output["candidate_record_count"] = len(expanded)
    output["candidate_record_count_matches_raw"] = len(expanded) == raw_total
    output["candidate_identity_model"] = MODEL
    output["every_raw_candidate_has_stable_identity"] = len(expanded) == raw_total
    output["candidate_evidence_quality_totals_recomputed"] = recomputed_totals
    output["candidate_evidence_quality_totals_match_source"] = totals_match
    output["source_evidence_quality_preserved"] = True
    output["raw_payload_retention_complete"] = recomputed_totals["count_only"] == 0
    output["canonical_digest_sha256"] = _digest(expanded)
    if len(expanded) != raw_total or not totals_match:
        output["status"] = "blocked"
        output["count_parity_verified"] = False
        discrepancies = list(output.get("discrepancies") or [])
        if len(expanded) != raw_total:
            discrepancies.append(
                {
                    "reason": "candidate_identity_population_mismatch",
                    "raw_total": raw_total,
                    "candidate_record_count": len(expanded),
                }
            )
        if not totals_match:
            discrepancies.append(
                {
                    "reason": "candidate_identity_evidence_quality_totals_mismatch",
                    "source_totals": {
                        key: _integer(totals.get(key)) for key in _TOTAL_KEYS
                    },
                    "recomputed_totals": recomputed_totals,
                }
            )
        output["discrepancies"] = discrepancies
    return output


def install_comprehensive_candidate_identity_v1() -> dict[str, Any]:
    from nico import comprehensive_native_providers_v5 as providers

    current = providers.build_canonical_scanner_finding_register
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "model": MODEL,
            "every_raw_candidate_has_stable_identity": True,
            "source_evidence_quality_preserved": True,
            "payload_retention_truth_recomputed": True,
            "lower_reconciliation_marker_preserved": getattr(
                current,
                _RECONCILIATION_MARKER,
                False,
            ),
        }

    def build_canonical_scanner_finding_register(
        scan: Mapping[str, Any],
        commit_sha: str,
    ) -> dict[str, Any]:
        return expand_candidate_identities(current(scan, commit_sha))

    setattr(build_canonical_scanner_finding_register, _MARKER, True)
    # The candidate wrapper is intentionally the outer layer. Preserve the lower
    # reconciliation marker so a later direct installer call remains idempotent
    # instead of reusing the global reconciliation wrapper and forming a cycle.
    if getattr(current, _RECONCILIATION_MARKER, False):
        setattr(build_canonical_scanner_finding_register, _RECONCILIATION_MARKER, True)
    setattr(build_canonical_scanner_finding_register, "_nico_previous", current)
    providers.build_canonical_scanner_finding_register = (
        build_canonical_scanner_finding_register
    )
    return {
        "status": "installed",
        "version": VERSION,
        "model": MODEL,
        "every_raw_candidate_has_stable_identity": True,
        "count_only_candidates_are_individually_auditable": True,
        "source_evidence_quality_preserved": True,
        "payload_retention_truth_recomputed": True,
        "lower_reconciliation_marker_preserved": getattr(
            build_canonical_scanner_finding_register,
            _RECONCILIATION_MARKER,
            False,
        ),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MODEL",
    "VERSION",
    "expand_candidate_identities",
    "install_comprehensive_candidate_identity_v1",
]
