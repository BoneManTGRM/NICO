from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.comprehensive-candidate-identity.v1"
MODEL = "stable-per-candidate-count-only-identities.v1"
_MARKER = "__nico_comprehensive_candidate_identity_v1__"


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
        if count == 1:
            item = deepcopy(record)
            item["candidate_id"] = item.get("candidate_id") or item.get("finding_id")
            item["occurrence_count"] = 1
            item["aggregate_occurrence_count"] = 1
            expanded.append(item)
            continue

        aggregate_fingerprint = str(record.get("raw_fingerprint") or "")
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
                    "evidence": (
                        f"Count-only candidate {index} of {count} for scanner "
                        f"{record.get('scanner')} and disposition {record.get('disposition')}. "
                        "The raw candidate payload was unavailable; identity is stable for this exact commit, scanner, disposition, and ordinal."
                    ),
                    "evidence_quality": "count_only",
                    "raw_payload_retention_state": "count_only",
                    "candidate_identity_model": MODEL,
                    "human_review_required": record.get("disposition") == "review_required",
                }
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
    output["findings"] = expanded
    output["candidate_record_count"] = len(expanded)
    output["candidate_record_count_matches_raw"] = len(expanded) == raw_total
    output["candidate_identity_model"] = MODEL
    output["every_raw_candidate_has_stable_identity"] = len(expanded) == raw_total
    output["canonical_digest_sha256"] = _digest(expanded)
    if len(expanded) != raw_total:
        output["status"] = "blocked"
        output["count_parity_verified"] = False
        discrepancies = list(output.get("discrepancies") or [])
        discrepancies.append(
            {
                "reason": "candidate_identity_population_mismatch",
                "raw_total": raw_total,
                "candidate_record_count": len(expanded),
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
        }

    def build_canonical_scanner_finding_register(
        scan: Mapping[str, Any],
        commit_sha: str,
    ) -> dict[str, Any]:
        return expand_candidate_identities(current(scan, commit_sha))

    setattr(build_canonical_scanner_finding_register, _MARKER, True)
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
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MODEL",
    "VERSION",
    "expand_candidate_identities",
    "install_comprehensive_candidate_identity_v1",
]
