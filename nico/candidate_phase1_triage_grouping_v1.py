from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any, Mapping

from nico.candidate_phase1_triage_dependency_v1 import actual_dependency
from nico.candidate_phase1_triage_utils_v1 import count, lookup, norm, path, scope, severity, text

_VOLATILE = {"timestamp", "generated_at", "observed_at", "duration_ms", "run_id", "line", "column", "start_line", "start_column"}


def _source_pattern(value: str) -> str:
    value = re.sub(r"\d+", "#", value.replace("\\", "/").casefold())
    parts = value.split("/")
    return "/".join(parts[-3:])


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(raw) for key, raw in sorted(value.items(), key=lambda item: str(item[0])) if str(key).casefold() not in _VOLATILE}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.split())
    return value


def _evidence_signature(record: Mapping[str, Any]) -> str:
    payload = {
        "message": text(record.get("evidence") or record.get("message") or record.get("title"), 2000).casefold(),
        "deterministic_evidence": _stable(record.get("deterministic_evidence") or record.get("scanner_evidence") or {}),
        "evidence_used": sorted(text(item, 300) for item in record.get("evidence_used") or []),
        "counterevidence": sorted(text(item, 300) for item in record.get("counterevidence") or []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _key(record: Mapping[str, Any]) -> tuple[Any, ...]:
    dep = actual_dependency(record)
    return (
        norm(record.get("scanner") or record.get("tool")),
        norm(record.get("category")),
        norm(record.get("rule_id") or record.get("rule") or record.get("advisory_id")),
        dep["package"].casefold(), dep["version"].casefold(), dep["ecosystem"].casefold(),
        scope(record), norm(record.get("technical_triage_rationale_code") or record.get("rationale_code")),
        _source_pattern(path(record)), norm(record.get("technical_triage_verdict")),
        norm(record.get("technical_triage_confidence")),
        tuple(sorted(text(item, 180) for item in record.get("technical_triage_proof_gaps") or [])),
        _evidence_signature(record),
    )


def cluster_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[_key(record)].append(record)
    summaries: list[dict[str, Any]] = []
    for key, members in groups.items():
        digest = hashlib.sha256(json.dumps(key, separators=(",", ":"), default=str).encode()).hexdigest()[:20].upper()
        cluster_id = f"NICO-CLUSTER-{digest}"
        size = sum(count(item) for item in members)
        candidate_ids = sorted(text(item.get("candidate_id") or item.get("finding_id"), 300) for item in members)
        representative = candidate_ids[0] if candidate_ids else ""
        verdicts = {norm(item.get("technical_triage_verdict")) for item in members}
        evidence_signatures = {_evidence_signature(item) for item in members}
        homogeneous_verdict = len(verdicts) == 1
        homogeneous_evidence = len(evidence_signatures) == 1
        evidence_changed = any(item.get("evidence_changed") is True for item in members)
        conflicts = any(lookup(item, "conflicting_evidence") is True for item in members)
        category = norm(members[0].get("category"))
        sev = {severity(item) for item in members}
        gaps = [item.get("technical_triage_proof_gaps") or [] for item in members]
        high_conf_na = verdicts == {"not_actionable"} and all(norm(item.get("technical_triage_confidence")) == "high" for item in members) and all(not value for value in gaps)
        repeat_review = verdicts == {"needs_review"} and category in {"dependency", "static"} and not (sev & {"critical", "high"}) and all(bool(value) for value in gaps) and not evidence_changed and not conflicts
        eligible = size > 1 and homogeneous_verdict and homogeneous_evidence and (high_conf_na or repeat_review)
        reason = "same scanner/rule/package-version/scope/rationale/source-pattern with identical normalized retained technical evidence"
        summary = {
            "cluster_id": cluster_id,
            "cluster_reason": reason,
            "cluster_size": size,
            "candidate_ids": candidate_ids,
            "representative_candidate_id": representative,
            "homogeneous_evidence": homogeneous_evidence,
            "homogeneous_verdict": homogeneous_verdict,
            "grouped_review_eligible": eligible,
        }
        summaries.append(summary)
        for item in members:
            item.update({key: deepcopy(value) for key, value in summary.items() if key != "candidate_ids"})
    return sorted(summaries, key=lambda item: item["cluster_id"])
