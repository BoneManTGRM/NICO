from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

HIGH_RULES = {
    "B102",  # exec_used
    "B307",  # eval
    "B602",  # subprocess_popen_with_shell_equals_true
    "B603",  # subprocess_without_shell_equals_true
    "B605",  # start_process_with_a_shell
    "B606",  # start_process_with_no_shell
    "B607",  # start_process_with_partial_path
    "B608",  # hardcoded_sql_expressions
}

CREDENTIAL_RULES = {
    "B105",  # hardcoded_password_string
    "B106",  # hardcoded_password_funcarg
    "B107",  # hardcoded_password_default
}

REVIEW_ONLY_RULES = {
    "B101",  # assert_used
    "B404",  # import_subprocess
    "B603",  # subprocess without shell often needs context
    "B607",  # partial executable path may be low impact in controlled CI/tooling
}

FALSE_POSITIVE_HINT_RULES = {
    "B101",
    "B404",
    "B603",
    "B607",
}

APPROVED_DECISIONS = {
    "false_positive",
    "accepted_risk",
    "mitigated",
    "not_applicable",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _tool_payloads(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_tools = payload.get("tools") or payload.get("results") or {}
    if isinstance(raw_tools, dict):
        return {str(name).lower(): data if isinstance(data, dict) else {"raw": data} for name, data in raw_tools.items()}
    if isinstance(raw_tools, list):
        parsed: dict[str, dict[str, Any]] = {}
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            name = str(item.get("tool") or item.get("scanner") or item.get("name") or "").lower().strip()
            if name:
                parsed[name] = item
        return parsed
    return {}


def extract_bandit_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    bandit = _tool_payloads(payload).get("bandit") or {}
    for key in ("findings", "results", "issues"):
        value = bandit.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _rule_id(finding: dict[str, Any]) -> str:
    return str(
        finding.get("test_id")
        or finding.get("test")
        or finding.get("rule_id")
        or finding.get("id")
        or "UNKNOWN"
    ).upper()


def _bandit_severity(finding: dict[str, Any]) -> str:
    value = str(finding.get("issue_severity") or finding.get("severity") or "unknown").lower()
    if value in {"high", "medium", "low"}:
        return value
    return "unknown"


def _confidence(finding: dict[str, Any]) -> str:
    value = str(finding.get("issue_confidence") or finding.get("confidence") or "unknown").lower()
    if value in {"high", "medium", "low"}:
        return value
    return "unknown"


def _line_ref(finding: dict[str, Any]) -> str:
    filename = str(finding.get("filename") or finding.get("file") or "unknown")
    line = finding.get("line_number") or finding.get("line") or "?"
    return f"{filename}:{line}"


def _finding_key(finding: dict[str, Any]) -> str:
    basis = {
        "rule_id": _rule_id(finding),
        "location": _line_ref(finding),
        "issue_text": str(finding.get("issue_text") or finding.get("message") or finding.get("text") or ""),
        "severity": _bandit_severity(finding),
        "confidence": _confidence(finding),
    }
    return "bandit_" + _stable_hash(basis)[:20]


def _decision_index(approval_artifact: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(approval_artifact, dict):
        return {}
    raw_decisions = approval_artifact.get("decisions") or approval_artifact.get("approvals") or []
    if not isinstance(raw_decisions, list):
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for item in raw_decisions:
        if not isinstance(item, dict):
            continue
        key = str(item.get("finding_key") or item.get("key") or "")
        if key:
            indexed[key] = item
    return indexed


def _is_approved_decision(decision: dict[str, Any] | None) -> bool:
    if not isinstance(decision, dict):
        return False
    value = str(decision.get("decision") or decision.get("classification") or "").lower()
    reviewer = str(decision.get("reviewer") or decision.get("approved_by") or decision.get("signoff_by") or "").strip()
    justification = str(decision.get("justification") or decision.get("reason") or decision.get("comment") or "").strip()
    return value in APPROVED_DECISIONS and bool(reviewer and justification)


def _decision_name(decision: dict[str, Any]) -> str:
    return str(decision.get("decision") or decision.get("classification") or "").lower()


def classify_bandit_finding(finding: dict[str, Any], approval_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    rule = _rule_id(finding)
    severity = _bandit_severity(finding)
    confidence = _confidence(finding)
    issue = str(finding.get("issue_text") or finding.get("message") or finding.get("text") or "Bandit finding requires review.")
    finding_key = _finding_key(finding)
    approved_decision = _decision_index(approval_artifact).get(finding_key)

    if rule in CREDENTIAL_RULES:
        classification = "real_blocker"
        priority = "critical"
        action = "Confirm whether this is a real credential. If confirmed, remove it, rotate the credential, and add a regression test or secret-scan guard."
    elif severity == "high" or rule in HIGH_RULES:
        classification = "real_blocker" if confidence in {"high", "medium", "unknown"} else "needs_human_review"
        priority = "high"
        action = "Review and repair before client-ready delivery unless a documented false-positive justification is approved."
    elif rule in REVIEW_ONLY_RULES or rule in FALSE_POSITIVE_HINT_RULES:
        classification = "needs_human_review"
        priority = "medium" if severity in {"medium", "unknown"} else "low"
        action = "Check calling context and document whether this is safe, mitigated, or a false positive."
    elif severity == "medium":
        classification = "needs_human_review"
        priority = "medium"
        action = "Review and either repair or mark as accepted risk with human signoff."
    else:
        classification = "candidate_false_positive" if confidence == "low" else "needs_human_review"
        priority = "low"
        action = "Triage during human review; repair if exploitable in the deployed context."

    approved = False
    approval_note = None
    if classification != "real_blocker" and _is_approved_decision(approved_decision):
        approved = True
        classification = _decision_name(approved_decision)
        approval_note = str(approved_decision.get("justification") or approved_decision.get("reason") or approved_decision.get("comment"))
        action = "Approved triage decision attached; this finding no longer blocks Static Analysis unless the finding fingerprint changes."

    return {
        "finding_key": finding_key,
        "rule_id": rule,
        "test_name": finding.get("test_name") or finding.get("test") or "unknown",
        "location": _line_ref(finding),
        "severity": severity,
        "confidence": confidence,
        "classification": classification,
        "priority": priority,
        "issue_text": issue,
        "recommended_action": action,
        "false_positive_hint": rule in FALSE_POSITIVE_HINT_RULES or confidence == "low",
        "approved": approved,
        "approval_note": approval_note,
        "human_review_required": not approved and classification in {"real_blocker", "needs_human_review", "candidate_false_positive"},
    }


def build_bandit_triage(payload: dict[str, Any], approval_artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    findings = extract_bandit_findings(payload)
    triaged = [classify_bandit_finding(item, approval_artifact=approval_artifact) for item in findings]
    by_class = Counter(item["classification"] for item in triaged)
    by_priority = Counter(item["priority"] for item in triaged)
    by_rule = Counter(item["rule_id"] for item in triaged)
    blocking = [item for item in triaged if item["classification"] == "real_blocker"]
    needs_review = [item for item in triaged if item["human_review_required"] and item["classification"] != "real_blocker"]
    approved = [item for item in triaged if item.get("approved")]

    status = "clean"
    if blocking:
        status = "blocking_findings"
    elif needs_review:
        status = "needs_human_review"
    elif approved:
        status = "approved_no_blockers"
    elif triaged:
        status = "triaged_no_blockers"

    triage = {
        "artifact_schema": "nico.bandit_triage.v1",
        "status": status,
        "finding_count": len(triaged),
        "blocking_count": len(blocking),
        "review_required_count": len(needs_review),
        "approved_count": len(approved),
        "candidate_false_positive_count": len([item for item in triaged if item["classification"] == "candidate_false_positive"]),
        "by_classification": dict(by_class),
        "by_priority": dict(by_priority),
        "by_rule": dict(by_rule),
        "top_findings": triaged[:20],
        "approval_artifact_attached": isinstance(approval_artifact, dict),
        "human_review_required": bool(blocking or needs_review),
        "generated_at": _now_iso(),
        "guardrail": "Bandit findings only stop blocking after a signed triage decision is attached for the stable finding key; real blockers still require repair.",
    }
    triage["artifact_hash"] = _stable_hash(triage)
    return triage


def bandit_triage_report_lines(triage: dict[str, Any]) -> dict[str, list[str]]:
    evidence = [
        f"Bandit triage classified {triage.get('finding_count', 0)} finding(s): "
        f"blocking={triage.get('blocking_count', 0)}, "
        f"needs_review={triage.get('review_required_count', 0)}, "
        f"approved={triage.get('approved_count', 0)}, "
        f"candidate_false_positive={triage.get('candidate_false_positive_count', 0)}."
    ]
    if triage.get("status") == "approved_no_blockers":
        evidence.append("Bandit triage approval artifact is attached and no Bandit blocker or review-required finding remains.")
    findings: list[str] = []
    if triage.get("blocking_count"):
        findings.append("Bandit triage found blocker-level findings requiring repair before client-ready delivery.")
    elif triage.get("review_required_count"):
        findings.append("Bandit triage found findings that require signed approval, repair, or accepted-risk documentation before final client claims.")

    for item in triage.get("top_findings", [])[:8]:
        if not isinstance(item, dict):
            continue
        if item.get("approved"):
            evidence.append(
                f"Bandit {item.get('rule_id')} at {item.get('location')}: approved as {item.get('classification')} "
                f"with finding_key={item.get('finding_key')}."
            )
            continue
        findings.append(
            f"Bandit {item.get('rule_id')} at {item.get('location')}: "
            f"{item.get('priority')} / {item.get('classification')} — {item.get('issue_text')} "
            f"finding_key={item.get('finding_key')}"
        )
    return {"evidence": evidence, "findings": findings}


def approval_template_for_triage(triage: dict[str, Any], *, reviewer: str = "human-reviewer") -> dict[str, Any]:
    """Return a reviewable triage template; callers must fill real decisions."""
    decisions = []
    for item in triage.get("top_findings", []):
        if not isinstance(item, dict):
            continue
        if item.get("classification") == "real_blocker":
            continue
        decisions.append(
            {
                "finding_key": item.get("finding_key"),
                "rule_id": item.get("rule_id"),
                "location": item.get("location"),
                "decision": "false_positive" if item.get("false_positive_hint") else "accepted_risk",
                "reviewer": reviewer,
                "justification": "REPLACE_WITH_REPO_SPECIFIC_REASON_BEFORE_USE",
            }
        )
    return {
        "artifact_schema": "nico.bandit_triage_approval.v1",
        "generated_at": _now_iso(),
        "decisions": decisions,
        "guardrail": "This is a template only until every justification is replaced with a real signed review reason.",
    }
