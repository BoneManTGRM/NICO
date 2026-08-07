from __future__ import annotations

from copy import deepcopy

from nico.candidate_lineage_migration_v1 import lineage_keys
from nico.candidate_phase1_lineage_v1 import apply_subject_safe_lineage
from nico.candidate_phase1_triage_v1 import apply_phase1_technical_triage

SUBJECT = {"repository": "BoneManTGRM/NICO", "project_id": "nico", "workspace_id": "ws-1", "assessment_target_id": "repo-root"}


def candidate(candidate_id: str, *, category: str = "static", scanner: str = "semgrep", rule: str = "rule.x", path: str = "nico/a.py", line: int = 10, evidence: str = "hit", severity: str = "medium", context: dict | None = None, occurrence_count: int = 1) -> dict:
    value = {
        "finding_id": candidate_id,
        "candidate_id": candidate_id,
        "category": category,
        "scanner": scanner,
        "rule_id": rule,
        "source_path": path,
        "line": line,
        "evidence": evidence,
        "severity": severity,
        "confidence": "high",
        "evidence_quality": "exact_source",
        "occurrence_count": occurrence_count,
        "disposition": "review_required",
        "human_disposition": "pending",
        "human_approval_status": "pending",
    }
    if context is not None:
        value["deterministic_evidence"] = context
    return value


def baseline_for(prior: list[dict], subject: dict | None = None) -> dict:
    rows = []
    for item in prior:
        keys = lineage_keys(item)
        rows.append([keys["exact"], keys["semantic"], keys["group"], keys["line"], item["candidate_id"], "source_review_required", "OLD-CLUSTER"])
    identity = subject or SUBJECT
    return {
        "s": "nico.candidate-lineage-baseline.v2",
        "n": len(rows),
        "a": "none",
        "r": identity["repository"],
        "p": identity.get("project_id"),
        "w": identity.get("workspace_id"),
        "t": identity.get("assessment_target_id"),
        "c": "prior-sha",
        "x": rows,
    }


def register(findings: list[dict], subject: dict | None = None) -> dict:
    return {
        "assessment_subject": deepcopy(subject or SUBJECT),
        "findings": deepcopy(findings),
        "totals": {"raw": sum(item.get("occurrence_count", 1) for item in findings)},
    }


def retained_triage(candidate_id: str, verdict: str = "not_actionable") -> dict:
    proposal = "approved_or_nonblocking" if verdict == "not_actionable" else "review_required"
    rank = None if verdict == "not_actionable" else 1
    return {
        "s": "nico.candidate-technical-triage.v1",
        "c": "prior-sha",
        "n": 1,
        "q": {
            "retained": [
                verdict,
                "high",
                proposal,
                "retained_evidence",
                "Prior evidence supported this proposal.",
                "Proposal only.",
                "Spot check retained evidence.",
                [],
                "",
            ]
        },
        "x": [[candidate_id, "retained", rank]],
    }


def lineage_then_triage(current: list[dict], prior: list[dict], *, source_triage: dict | None = None, subject: dict | None = None, baseline_subject: dict | None = None) -> dict:
    lined = apply_subject_safe_lineage(register(current, subject), baseline=baseline_for(prior, baseline_subject))
    return apply_phase1_technical_triage(lined, triage=source_triage or {"s": "nico.candidate-technical-triage.v1", "c": "prior-sha", "n": 0, "q": {}, "x": []})
