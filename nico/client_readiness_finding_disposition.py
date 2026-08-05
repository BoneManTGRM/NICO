from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Iterable, Mapping

VERSION = "nico.client-readiness-finding-disposition.v1"
DECISIONS = {"accept", "remediate", "defer", "reject", "requires_more_evidence"}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_digest(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", _text(value)))


def _source(finding: Mapping[str, Any]) -> dict[str, Any]:
    nested = finding.get("source") if isinstance(finding.get("source"), Mapping) else {}
    path = _text(finding.get("path") or finding.get("source_path") or nested.get("path"))
    line = finding.get("line") or finding.get("line_number") or nested.get("line") or ""
    return {
        "path": path,
        "line": int(line) if str(line).isdigit() else _text(line),
    }


def canonical_finding(finding: Mapping[str, Any], *, ordinal: int = 0) -> dict[str, Any]:
    if not isinstance(finding, Mapping):
        raise TypeError("finding must be a mapping")
    original = deepcopy(dict(finding))
    supplied_id = _text(finding.get("finding_id") or finding.get("id"))
    source = _source(finding)
    identity_basis = {
        "title": _text(finding.get("title") or finding.get("finding")),
        "priority": _text(finding.get("priority") or "unprioritized").upper(),
        "source": source,
        "evidence": _text(finding.get("evidence")),
        "original_digest": _sha256(original),
    }
    finding_id = supplied_id or f"finding_{_sha256(identity_basis)[:24]}"
    return {
        "finding_id": finding_id,
        "ordinal": int(ordinal),
        **identity_basis,
        "release_blocking": finding.get("release_blocking") is True,
        "control_plane": finding.get("control_plane") is True,
        "original_finding": original,
        "finding_digest": _sha256({"finding_id": finding_id, **identity_basis}),
    }


def _reviewer_errors(decision: Mapping[str, Any]) -> list[str]:
    reviewer = decision.get("reviewer") if isinstance(decision.get("reviewer"), Mapping) else {}
    errors: list[str] = []
    for key in ("identity", "role", "authorization_basis"):
        if not _text(reviewer.get(key)):
            errors.append(f"reviewer.{key} is required")
    if reviewer.get("authorized") is not True:
        errors.append("reviewer.authorized must be true")
    if not _text(decision.get("decided_at")):
        errors.append("decided_at is required")
    if not _text(decision.get("rationale")):
        errors.append("rationale is required")
    return errors


def _valid_iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(_text(value))
    except ValueError:
        return False
    return True


def _risk_acceptance_errors(decision: Mapping[str, Any]) -> list[str]:
    acceptance = decision.get("residual_risk_acceptance") if isinstance(decision.get("residual_risk_acceptance"), Mapping) else {}
    errors: list[str] = []
    for key in ("accepted_by", "role", "authorization_basis", "accepted_at", "scope"):
        if not _text(acceptance.get(key)):
            errors.append(f"residual_risk_acceptance.{key} is required")
    return errors


def _decision_errors(decision: Mapping[str, Any], finding: Mapping[str, Any]) -> list[str]:
    errors = _reviewer_errors(decision)
    state = _text(decision.get("decision")).lower()
    if state not in DECISIONS:
        errors.append(f"unsupported finding decision: {state or 'blank'}")
    if state == "requires_more_evidence" and not _text(decision.get("evidence_request")):
        errors.append("evidence_request is required when requesting more evidence")
    if _text(decision.get("finding_digest")) != finding.get("finding_digest"):
        errors.append("finding_digest does not match the exact current finding")
    for key in ("risk", "probable_impact", "owner", "verification_method"):
        if not _text(decision.get(key)):
            errors.append(f"{key} is required")
    if not _valid_iso_date(decision.get("target_date")):
        errors.append("target_date must be an ISO date")

    verification = decision.get("verification") if isinstance(decision.get("verification"), Mapping) else {}
    if state == "remediate":
        if _text(verification.get("status")).lower() not in {"passed", "pending"}:
            errors.append("remediation verification.status must be passed or pending")
        if not _text(verification.get("artifact_sha256")) and _text(verification.get("status")).lower() == "passed":
            errors.append("passed remediation requires verification.artifact_sha256")
        if _text(verification.get("artifact_sha256")) and not _valid_digest(verification.get("artifact_sha256")):
            errors.append("verification.artifact_sha256 must be a SHA-256 digest")
    if state == "reject":
        if not _text(decision.get("rejection_evidence")):
            errors.append("rejection_evidence is required when rejecting a finding")
    if state in {"accept", "defer"} or (
        finding.get("release_blocking") and state in {"accept", "defer", "remediate"}
    ):
        errors.extend(_risk_acceptance_errors(decision))
    if finding.get("release_blocking") and state == "remediate" and _text(verification.get("status")).lower() != "passed":
        errors.append("release-blocking remediation must be verified as passed")
    return errors


def build_finding_disposition_register(
    findings: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]] = (),
    *,
    repository: str = "",
    commit_sha: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    normalized = [canonical_finding(item, ordinal=index) for index, item in enumerate(findings)]
    duplicates = sorted(value for value, count in Counter(item["finding_id"] for item in normalized).items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate finding identity: {', '.join(duplicates)}")
    finding_by_id = {item["finding_id"]: item for item in normalized}

    applied: dict[str, dict[str, Any]] = {}
    invalid_decisions: list[dict[str, Any]] = []
    for index, source_decision in enumerate(decisions):
        decision = deepcopy(dict(source_decision)) if isinstance(source_decision, Mapping) else {}
        finding_id = _text(decision.get("finding_id"))
        finding = finding_by_id.get(finding_id)
        errors: list[str] = []
        if not finding:
            errors.append("decision references an unknown finding_id")
        elif finding_id in applied:
            errors.append("finding already has a decision")
        else:
            errors.extend(_decision_errors(decision, finding))
        if errors:
            invalid_decisions.append({"decision_index": index, "finding_id": finding_id, "errors": errors, "decision": decision})
            continue
        normalized_decision = {
            **decision,
            "decision": _text(decision.get("decision")).lower(),
            "decision_digest": _sha256(decision),
        }
        applied[finding_id] = normalized_decision

    records: list[dict[str, Any]] = []
    release_blockers: list[str] = []
    for finding in sorted(normalized, key=lambda item: item["finding_id"]):
        decision = applied.get(finding["finding_id"])
        decision_status = "pending_human_decision"
        if decision:
            decision_status = (
                "requires_more_evidence"
                if decision["decision"] == "requires_more_evidence"
                else "complete"
            )
        record = {
            **finding,
            "decision_status": decision_status,
            "decision": decision or {},
        }
        records.append(record)
        if finding["release_blocking"]:
            if not decision:
                release_blockers.append(f"{finding['finding_id']} has no authorized decision")
            elif decision["decision"] == "requires_more_evidence":
                release_blockers.append(
                    f"{finding['finding_id']} requires more evidence before disposition"
                )
            elif decision["decision"] == "remediate":
                verification = decision.get("verification") if isinstance(decision.get("verification"), Mapping) else {}
                if _text(verification.get("status")).lower() != "passed":
                    release_blockers.append(f"{finding['finding_id']} remediation is not verified")

    pending = [item["finding_id"] for item in records if item["decision_status"] != "complete"]
    decision_counts = Counter(
        item["decision"].get("decision") if item["decision"] else "pending_human_decision"
        for item in records
    )
    complete = not invalid_decisions and not pending and not release_blockers
    basis = {
        "version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "finding_digests": sorted(item["finding_digest"] for item in records),
        "decision_digests": sorted(item["decision"].get("decision_digest", "") for item in records if item["decision"]),
    }
    return {
        "schema_version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "passed" if complete else "blocked",
        "disposition_complete": complete,
        "client_delivery_allowed": False,
        "automation_may_decide": False,
        "finding_count": len(records),
        "decision_counts": dict(sorted(decision_counts.items())),
        "pending_finding_ids": pending,
        "release_blockers": release_blockers,
        "invalid_decisions": invalid_decisions,
        "records": records,
        "register_digest": _sha256(basis),
        "rule": "NICO may prepare exact-source finding records and verification criteria, but only an authorized human may accept, remediate, defer, reject, or request more evidence for a finding.",
    }


def finding_disposition_gate(register: Mapping[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    if str(register.get("schema_version") or "") != VERSION:
        blockers.append("finding disposition schema version is missing or unsupported")
    if register.get("disposition_complete") is not True:
        blockers.append("finding disposition is incomplete")
    if register.get("pending_finding_ids"):
        blockers.append("one or more findings lack an authorized human decision")
    if register.get("invalid_decisions"):
        blockers.append("one or more finding decisions are invalid")
    if register.get("release_blockers"):
        blockers.append("one or more release-blocking findings are unresolved")
    if int(register.get("finding_count") or 0) != len(register.get("records") or []):
        blockers.append("finding population does not reconcile")
    return {
        "status": "passed" if not blockers else "blocked",
        "ready_for_next_gate": not blockers,
        "client_delivery_allowed": False,
        "blockers": blockers,
        "register_digest": register.get("register_digest") or "",
        "rule": "Passing finding disposition is necessary but never sufficient for client delivery authorization.",
    }


__all__ = [
    "DECISIONS",
    "VERSION",
    "build_finding_disposition_register",
    "canonical_finding",
    "finding_disposition_gate",
]
