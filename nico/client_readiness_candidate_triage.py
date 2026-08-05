from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

VERSION = "nico.client-readiness-candidate-triage.v1"

CANONICAL_DISPOSITIONS = {
    "confirmed_material",
    "false_positive",
    "test_or_example_only",
    "accepted_nonblocking",
    "duplicate",
    "requires_more_evidence",
}

_CATEGORY_ALIASES = {
    "dependency": "dependency",
    "dependencies": "dependency",
    "library": "dependency",
    "secret": "secret",
    "secrets": "secret",
    "credential": "secret",
    "static": "static",
    "static_analysis": "static",
    "sast": "static",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9_.:/-]+", "-", _text(value).lower()).strip("-")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _first(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _category(candidate: Mapping[str, Any]) -> str:
    raw = _slug(_first(candidate, ("category", "candidate_category", "scanner_category", "kind", "type")))
    return _CATEGORY_ALIASES.get(raw, raw or "unknown")


def _source(candidate: Mapping[str, Any]) -> dict[str, Any]:
    nested = candidate.get("source") if isinstance(candidate.get("source"), Mapping) else {}
    path = _text(_first(candidate, ("path", "file", "filename", "source_path")) or nested.get("path"))
    line = _first(candidate, ("line", "line_number", "start_line")) or nested.get("line")
    column = _first(candidate, ("column", "column_number", "start_column")) or nested.get("column")
    package = _text(_first(candidate, ("package", "package_name", "dependency")))
    installed = _text(_first(candidate, ("installed_version", "version")))
    return {
        "path": path,
        "line": int(line) if str(line).isdigit() else _text(line),
        "column": int(column) if str(column).isdigit() else _text(column),
        "package": package,
        "installed_version": installed,
    }


def _rule(candidate: Mapping[str, Any]) -> str:
    return _text(_first(candidate, ("rule_id", "rule", "check_id", "advisory_id", "vulnerability_id", "id", "title")))


def _analyzer(candidate: Mapping[str, Any]) -> str:
    return _text(_first(candidate, ("analyzer", "scanner", "tool", "source_tool"))) or "unknown"


def _root_cause(candidate: Mapping[str, Any]) -> str:
    value = _first(candidate, ("root_cause", "fingerprint", "message", "description", "title"))
    return _text(value)[:1000]


def canonical_candidate(candidate: Mapping[str, Any], *, ordinal: int = 0) -> dict[str, Any]:
    """Return a deterministic candidate identity without changing retained evidence."""

    if not isinstance(candidate, Mapping):
        raise TypeError("candidate must be a mapping")
    original = deepcopy(dict(candidate))
    identity_basis = {
        "category": _category(candidate),
        "analyzer": _analyzer(candidate),
        "rule": _rule(candidate),
        "source": _source(candidate),
        "root_cause": _root_cause(candidate),
        "evidence_digest": _sha256(original),
    }
    supplied_id = _text(_first(candidate, ("candidate_id", "finding_id", "id")))
    candidate_id = supplied_id or f"candidate_{_sha256(identity_basis)[:24]}"
    return {
        "candidate_id": candidate_id,
        "ordinal": int(ordinal),
        **identity_basis,
        "original_evidence": original,
    }


def cluster_candidates(candidates: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    normalized = [canonical_candidate(candidate, ordinal=index) for index, candidate in enumerate(candidates)]
    duplicate_ids = [value for value, count in Counter(item["candidate_id"] for item in normalized).items() if count > 1]
    if duplicate_ids:
        raise ValueError(f"duplicate candidate identity: {', '.join(sorted(duplicate_ids))}")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bases: dict[str, dict[str, Any]] = {}
    for item in normalized:
        source = item["source"]
        cluster_basis = {
            "category": item["category"],
            "analyzer": item["analyzer"],
            "rule": item["rule"],
            "source_root": source.get("package") or source.get("path") or "unlocated",
            "root_cause": item["root_cause"],
        }
        key = _sha256(cluster_basis)
        grouped[key].append(item)
        bases[key] = cluster_basis

    clusters: list[dict[str, Any]] = []
    for key in sorted(grouped):
        members = sorted(grouped[key], key=lambda item: (item["candidate_id"], item["ordinal"]))
        candidate_ids = [item["candidate_id"] for item in members]
        cluster_digest = _sha256({"basis": bases[key], "candidate_ids": candidate_ids})
        clusters.append(
            {
                "cluster_id": f"cluster_{key[:24]}",
                "cluster_digest": cluster_digest,
                "cluster_basis": bases[key],
                "candidate_ids": candidate_ids,
                "candidate_count": len(candidate_ids),
                "candidates": members,
            }
        )
    return clusters


def _human_decision_errors(decision: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    reviewer = decision.get("reviewer") if isinstance(decision.get("reviewer"), Mapping) else {}
    if not _text(reviewer.get("identity")):
        errors.append("reviewer.identity is required")
    if not _text(reviewer.get("role")):
        errors.append("reviewer.role is required")
    if reviewer.get("authorized") is not True:
        errors.append("reviewer.authorized must be true")
    if not _text(reviewer.get("authorization_basis")):
        errors.append("reviewer.authorization_basis is required")
    if not _text(decision.get("decided_at")):
        errors.append("decided_at is required")
    if not _text(decision.get("rationale")):
        errors.append("rationale is required")
    return errors


def _defer_errors(decision: Mapping[str, Any]) -> list[str]:
    if decision.get("disposition") != "requires_more_evidence":
        return []
    errors: list[str] = []
    if not _text(decision.get("owner")):
        errors.append("owner is required for requires_more_evidence")
    review_by = _text(decision.get("review_by"))
    try:
        date.fromisoformat(review_by)
    except ValueError:
        errors.append("review_by must be an ISO date for requires_more_evidence")
    acceptance = decision.get("risk_acceptance") if isinstance(decision.get("risk_acceptance"), Mapping) else {}
    for key in ("accepted_by", "authorization_basis", "accepted_at"):
        if not _text(acceptance.get(key)):
            errors.append(f"risk_acceptance.{key} is required for requires_more_evidence")
    return errors


def _validate_decision(decision: Mapping[str, Any], cluster_by_id: Mapping[str, Mapping[str, Any]], candidate_ids: set[str]) -> tuple[list[str], list[str]]:
    errors = _human_decision_errors(decision)
    disposition = _text(decision.get("disposition")).lower()
    if disposition not in CANONICAL_DISPOSITIONS:
        errors.append(f"unsupported disposition: {disposition or 'blank'}")
    errors.extend(_defer_errors({**decision, "disposition": disposition}))

    scope = _text(decision.get("scope")).lower()
    targets: list[str] = []
    if scope == "candidate":
        candidate_id = _text(decision.get("candidate_id"))
        if candidate_id not in candidate_ids:
            errors.append("candidate decision references an unknown candidate_id")
        elif candidate_id:
            targets = [candidate_id]
    elif scope == "cluster":
        cluster_id = _text(decision.get("cluster_id"))
        cluster = cluster_by_id.get(cluster_id)
        if not cluster:
            errors.append("cluster decision references an unknown cluster_id")
        else:
            if _text(decision.get("cluster_digest")) != cluster.get("cluster_digest"):
                errors.append("cluster_digest does not match the exact current cluster")
            evidence = decision.get("representative_evidence")
            if not isinstance(evidence, list) or not any(_text(item) for item in evidence):
                errors.append("representative_evidence is required for a cluster decision")
            targets = list(cluster.get("candidate_ids") or [])
    else:
        errors.append("scope must be candidate or cluster")
    return errors, targets


def build_candidate_triage_register(
    candidates: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]] = (),
    *,
    repository: str = "",
    commit_sha: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Build the canonical fail-closed triage register.

    Automation establishes identity, clusters, and validation only. It never creates
    a human disposition. A formally deferred item is accounted for only when owner,
    review date, rationale, and authorized risk acceptance are retained.
    """

    clusters = cluster_candidates(candidates)
    all_candidates = [candidate for cluster in clusters for candidate in cluster["candidates"]]
    candidate_ids = {item["candidate_id"] for item in all_candidates}
    cluster_by_id = {item["cluster_id"]: item for item in clusters}
    assignments: dict[str, dict[str, Any]] = {}
    invalid_decisions: list[dict[str, Any]] = []

    for index, source_decision in enumerate(decisions):
        decision = deepcopy(dict(source_decision)) if isinstance(source_decision, Mapping) else {}
        errors, targets = _validate_decision(decision, cluster_by_id, candidate_ids)
        duplicate_targets = sorted(target for target in targets if target in assignments)
        if duplicate_targets:
            errors.append(f"candidate already dispositioned: {', '.join(duplicate_targets)}")
        if errors:
            invalid_decisions.append({"decision_index": index, "errors": errors, "decision": decision})
            continue
        normalized = {
            **decision,
            "disposition": _text(decision.get("disposition")).lower(),
            "decision_digest": _sha256(decision),
        }
        for target in targets:
            assignments[target] = normalized

    records: list[dict[str, Any]] = []
    for candidate in sorted(all_candidates, key=lambda item: item["candidate_id"]):
        decision = assignments.get(candidate["candidate_id"])
        records.append(
            {
                **candidate,
                "decision_status": "complete" if decision else "pending_human_review",
                "decision": decision or {},
            }
        )

    pending = [item["candidate_id"] for item in records if item["decision_status"] != "complete"]
    counts = Counter(
        item["decision"].get("disposition") if item["decision_status"] == "complete" else "pending_human_review"
        for item in records
    )
    category_counts = Counter(item["category"] for item in records)
    complete = bool(records or not candidate_ids) and not invalid_decisions and not pending
    register_basis = {
        "version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "candidate_ids": sorted(candidate_ids),
        "cluster_digests": sorted(item["cluster_digest"] for item in clusters),
        "decision_digests": sorted(item["decision"].get("decision_digest", "") for item in records if item["decision"]),
    }
    return {
        "schema_version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "passed" if complete else "blocked",
        "triage_complete": complete,
        "client_delivery_allowed": False,
        "automation_may_approve": False,
        "candidate_count": len(records),
        "cluster_count": len(clusters),
        "category_counts": dict(sorted(category_counts.items())),
        "disposition_counts": dict(sorted(counts.items())),
        "pending_candidate_ids": pending,
        "invalid_decisions": invalid_decisions,
        "clusters": clusters,
        "records": records,
        "register_digest": _sha256(register_basis),
        "rule": "Candidate identities and clusters are automated; dispositions require an authorized human decision bound to the exact candidate or cluster digest.",
    }


def candidate_triage_gate(register: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if str(register.get("schema_version") or "") != VERSION:
        blockers.append("candidate triage schema version is missing or unsupported")
    if register.get("triage_complete") is not True:
        blockers.append("candidate triage is incomplete")
    if register.get("invalid_decisions"):
        blockers.append("candidate triage contains invalid human decisions")
    if register.get("pending_candidate_ids"):
        blockers.append("candidate triage contains unexplained pending candidates")
    expected = int(register.get("candidate_count") or 0)
    actual = len(register.get("records") or [])
    if expected != actual:
        blockers.append("candidate register count does not reconcile")
    return {
        "status": "passed" if not blockers else "blocked",
        "ready_for_next_gate": not blockers,
        "client_delivery_allowed": False,
        "blockers": blockers,
        "register_digest": register.get("register_digest") or "",
        "rule": "Passing candidate triage is necessary but never sufficient for client delivery authorization.",
    }


__all__ = [
    "CANONICAL_DISPOSITIONS",
    "VERSION",
    "build_candidate_triage_register",
    "candidate_triage_gate",
    "canonical_candidate",
    "cluster_candidates",
]
