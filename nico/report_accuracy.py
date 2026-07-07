from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from nico.artifact_evidence_v2 import apply_evidence_artifact_scoring
from nico.i18n_es_mx import localize_result, reports_es_mx, wants_es_mx
from nico.reparodynamics_engine import reparodynamic_loop
from nico.scanner_artifact_scoring import apply_scanner_artifact_scoring

RAW_GITHUB_ERROR_PATTERNS = [
    re.compile(r"GitHub returned\s+(403|429)\s*:\s*\{.*?\}", re.IGNORECASE),
    re.compile(r"\{\s*\"documentation_url\".*?\}", re.IGNORECASE),
]

METADATA_LIMIT_MARKERS = ("github returned 403", "github returned 429", "api rate", "request limit", "abuse detection", "rate-limited", "rate limited")
CODE_MARKER_SUMMARY_RE = re.compile(r"Text files inspected for code-risk markers: TODO/FIXME/security notes=(\d+), risky pattern hits=(\d+), test-path signals=(\d+)\.", re.IGNORECASE)
ACTIONABLE_CODE_MARKER_RE = re.compile(r"(?i)(\bTODO\b|\bFIXME\b|SECURITY\s*[:=\-]|security\s+(issue|risk|bug|vulnerability|credential|secret|fix|todo|fixme))")
GENERIC_CODE_MARKER_FINDING = "TODO/FIXME/security-note markers require triage before client-ready delivery."

SECTION_REQUIRED_SOURCES: dict[str, set[str]] = {
    "code_audit": {"github_metadata", "repository_files"},
    "dependency_health": {"repository_files", "dependency_intelligence"},
    "secrets_review": {"repository_files", "secret_scanning"},
    "static_analysis": {"repository_files", "static_analysis"},
    "ci_cd": {"workflow_files", "workflow_runs"},
    "architecture_debt": {"repository_tree", "repository_files"},
    "velocity_complexity": {"github_metadata", "repository_tree"},
    "scanner_worker_evidence": {"scanner_worker"},
    "test_execution": {"test_execution"},
    "build_execution": {"build_execution"},
}


def is_metadata_limited(value: Any) -> bool:
    text = str(value or "").lower()
    return any(marker in text for marker in METADATA_LIMIT_MARKERS)


def sanitize_client_note(value: Any) -> str:
    text = " ".join(str(value or "").replace("\u2014", "-").replace("\u2013", "-").split())
    lower = text.lower()
    if is_metadata_limited(text):
        if "workflow" in lower or "ci/cd" in lower or ".github/workflows" in lower:
            return "Workflow metadata was unavailable or degraded because GitHub metadata access was rate-limited or incomplete. Do not treat missing workflow metadata as proof that CI is absent."
        if "pull" in lower or "pr" in lower:
            return "Pull-request metadata was unavailable or degraded because GitHub metadata access was rate-limited or incomplete. Do not treat missing PR metadata as proof of direct-to-main work."
        if "commit" in lower:
            return "Commit metadata was unavailable or degraded because GitHub metadata access was rate-limited or incomplete. Do not treat missing commit metadata as proof of inactivity."
        return "GitHub metadata was unavailable or degraded because metadata access was rate-limited or incomplete. Rerun with authenticated GitHub access before firm claims."
    for pattern in RAW_GITHUB_ERROR_PATTERNS:
        text = pattern.sub("GitHub metadata was unavailable; raw API response omitted from the client report.", text)
    return re.sub(r"https?://\S+", "[link omitted]", text).strip()


def sanitize_note_list(items: list[Any]) -> list[str]:
    output: list[str] = []
    for item in items or []:
        cleaned = sanitize_client_note(item)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output


def source_from_text(value: Any) -> set[str]:
    text = str(value or "").lower()
    sources: set[str] = set()
    if any(term in text for term in ["commit", "pull-request", "pull request", "pr ", "github metadata"]):
        sources.add("github_metadata")
    if any(term in text for term in ["workflow", "github actions", ".github/workflows"]):
        sources.add("workflow_files")
        if "run" in text or "history" in text or "artifact" in text:
            sources.add("workflow_runs")
    if any(term in text for term in ["requirements.txt", "package.json", "lockfile", "repository files", "text files", "readme", "source-file"]):
        sources.add("repository_files")
    if any(term in text for term in ["tree", "root contains", "source-file signal", "test-path signal"]):
        sources.add("repository_tree")
    if any(term in text for term in ["osv", "pip-audit", "npm audit", "npm-audit", "osv-scanner", "dependency audit", "dependency artifact", "dependency vulnerabilit"]):
        sources.add("dependency_intelligence")
    if any(term in text for term in ["secret", "credential-scan", "gitleaks", "trufflehog", "sensitive scan"]):
        sources.add("secret_scanning")
    if any(term in text for term in ["semgrep", "bandit", "eslint", "typescript", "static", "risk-pattern"]):
        sources.add("static_analysis")
    if any(term in text for term in ["scanner worker", "scanner-worker", "controlled_scanner_worker"]):
        sources.add("scanner_worker")
    if any(term in text for term in ["pytest", "npm-test", "test execution", "tests passed", "test run"]):
        sources.add("test_execution")
    if any(term in text for term in ["npm-build", "build execution", "production build", "build completed"]):
        sources.add("build_execution")
    return sources


def _find_section(sections: list[dict[str, Any]], section_id: str) -> dict[str, Any] | None:
    return next((item for item in sections if item.get("id") == section_id), None)


def _has_audit_workflow(sections: list[dict[str, Any]]) -> bool:
    ci = _find_section(sections, "ci_cd")
    if not ci:
        return False
    text = "\n".join(str(item) for item in ci.get("evidence", []) + ci.get("findings", [])).lower()
    return "security-audit" in text or "security audit" in text or "audit evidence" in text


def apply_ci_audit_workflow_evidence(sections: list[dict[str, Any]]) -> None:
    if not _has_audit_workflow(sections):
        return
    ci = _find_section(sections, "ci_cd")
    if not ci:
        return
    note = "CI audit workflow configuration is present, but workflow presence alone does not prove clean dependency evidence. Parsed evidence artifacts are required before score lift."
    ci.setdefault("evidence", [])
    if note not in ci["evidence"]:
        ci["evidence"].append(note)
    sources = set(ci.get("evidence_sources") or [])
    sources.add("workflow_files")
    ci["evidence_sources"] = sorted(sources)


def _is_actionable_code_marker(note: Any) -> bool:
    text = str(note or "")
    if CODE_MARKER_SUMMARY_RE.search(text) or text == GENERIC_CODE_MARKER_FINDING:
        return False
    return bool(ACTIONABLE_CODE_MARKER_RE.search(text))


def apply_code_marker_noise_filter(sections: list[dict[str, Any]]) -> None:
    code = _find_section(sections, "code_audit")
    if not code:
        return
    evidence = list(code.get("evidence", []) or [])
    findings = list(code.get("findings", []) or [])
    summary_match = next((CODE_MARKER_SUMMARY_RE.search(str(item)) for item in evidence if CODE_MARKER_SUMMARY_RE.search(str(item))), None)
    if not summary_match:
        return
    actionable = [item for item in evidence + findings if _is_actionable_code_marker(item)]
    if actionable:
        return
    risky_hits = int(summary_match.group(2))
    test_signals = int(summary_match.group(3))
    replacement = f"Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits={risky_hits}, test-path signals={test_signals}. General security wording in docs/workflows was not treated as an actionable code marker."
    filtered_evidence = []
    for item in evidence:
        text = str(item)
        if CODE_MARKER_SUMMARY_RE.search(text):
            if replacement not in filtered_evidence:
                filtered_evidence.append(replacement)
            continue
        if "security" in text.lower() and not _is_actionable_code_marker(text):
            continue
        filtered_evidence.append(item)
    filtered_findings = [item for item in findings if str(item) != GENERIC_CODE_MARKER_FINDING]
    code["evidence"] = filtered_evidence
    code["findings"] = filtered_findings
    if not filtered_findings:
        code["score"] = max(int(code.get("score") or 0), 86)
        code["status"] = "green"


def classify_section_confidence(section: dict[str, Any]) -> dict[str, Any]:
    section_id = str(section.get("id") or "")
    evidence = sanitize_note_list(list(section.get("evidence", []) or []))
    findings = sanitize_note_list(list(section.get("findings", []) or []))
    unavailable = sanitize_note_list(list(section.get("unavailable", []) or []))
    evidence_sources: set[str] = set(section.get("evidence_sources") or [])
    unavailable_sources: set[str] = set(section.get("unavailable_sources") or [])
    for note in evidence + findings:
        evidence_sources.update(source_from_text(note))
    for note in unavailable:
        unavailable_sources.update(source_from_text(note))
    required_sources = set(section.get("required_sources") or []) or SECTION_REQUIRED_SOURCES.get(section_id, set())
    missing_required = sorted(required_sources - evidence_sources)
    optional_unavailable = sorted(unavailable_sources - set(missing_required))
    metadata_limited = any(is_metadata_limited(note) for note in unavailable + evidence + findings)
    if not evidence and not findings:
        confidence = "unavailable"
    elif missing_required or metadata_limited:
        confidence = "limited"
    elif unavailable:
        confidence = "medium"
    else:
        confidence = "high"
    score = max(0, min(100, int(section.get("score") or 0)))
    status = str(section.get("status") or "unknown").lower()
    if confidence in {"limited", "unavailable"} and status == "green":
        status = "yellow"
        score = min(score, 74)
    if confidence == "unavailable":
        status = "gray"
        score = min(score, 44)
    verified_claims = evidence + findings
    unverified_claims = unavailable[:]
    if confidence in {"limited", "unavailable"}:
        unverified_claims.append("This section cannot support firm client-facing claims until missing or degraded evidence is resolved.")
    elif optional_unavailable:
        unverified_claims.append("Some stronger external evidence is still unavailable, but this section has enough hosted evidence for a provisional score.")
    if section_id in {"secrets_review", "static_analysis"} and unavailable:
        unverified_claims.append("A clean built-in pattern check is not equivalent to a complete scanner-clean result.")
    section.update({
        "score": score,
        "status": status,
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
        "confidence": confidence,
        "evidence_sources": sorted(evidence_sources),
        "unavailable_sources": sorted(unavailable_sources),
        "required_sources": sorted(required_sources),
        "missing_required_sources": missing_required,
        "optional_unavailable_sources": optional_unavailable,
        "verified_claims": verified_claims,
        "unverified_claims": sanitize_note_list(unverified_claims),
        "human_review_required": True,
    })
    return section


def maturity_from_sections(sections: list[dict[str, Any]]) -> dict[str, Any]:
    if not sections:
        return {"level": "Unavailable", "score": 0}
    score = round(sum(int(item.get("score") or 0) for item in sections) / len(sections))
    if score >= 75:
        level = "Senior maturity signal"
    elif score >= 55:
        level = "Mid maturity signal"
    elif score >= 40:
        level = "Junior maturity signal"
    else:
        level = "Early maturity signal"
    return {"level": level, "score": score}


def delivery_verdict(result: dict[str, Any]) -> dict[str, Any]:
    sections = [item for item in result.get("sections", []) if isinstance(item, dict)]
    limited = [item.get("label") or item.get("id") for item in sections if item.get("confidence") in {"limited", "unavailable"}]
    red = [item.get("label") or item.get("id") for item in sections if item.get("status") == "red"]
    unavailable = [note for item in sections for note in item.get("unavailable", []) or []]
    blockers: list[str] = []
    if red:
        blockers.append(f"Red sections require triage: {', '.join(map(str, red[:6]))}.")
    if limited:
        blockers.append(f"Limited-confidence sections require additional evidence: {', '.join(map(str, limited[:6]))}.")
    if unavailable:
        blockers.append("Unavailable evidence remains disclosed and must be reviewed.")
    confidence = "high" if not blockers else ("limited" if limited else "medium")
    return {"status": "review_ready" if not blockers else "human_review_required", "confidence": confidence, "blockers": blockers, "limited_sections": limited, "red_sections": red, "unavailable_items": len(unavailable)}


def _apply_language(output: dict[str, Any]) -> dict[str, Any]:
    if not any(wants_es_mx(output.get(key)) for key in ("report_language", "language", "assessment_mode")):
        return output
    localized = localize_result(output)
    localized["reports"] = {**(output.get("reports") or {}), **reports_es_mx(localized)}
    return localized


def apply_report_accuracy(result: dict[str, Any]) -> dict[str, Any]:
    output = apply_evidence_artifact_scoring(deepcopy(result))
    output = apply_scanner_artifact_scoring(output)
    sections = []
    for section in output.get("sections", []) or []:
        if isinstance(section, dict):
            sections.append(section)
    apply_code_marker_noise_filter(sections)
    sections = [classify_section_confidence(section) for section in sections]
    apply_ci_audit_workflow_evidence(sections)
    sections = [classify_section_confidence(section) for section in sections]
    output["sections"] = sections
    output["maturity_signal"] = maturity_from_sections(sections)
    output["maturity_semaphore"] = {item.get("label") or item.get("id"): item.get("status") for item in sections}
    output["client_delivery_verdict"] = delivery_verdict(output)
    output["reparodynamics"] = reparodynamic_loop(output)
    output["truthfulness_rules"] = [
        "Confirmed claims require direct evidence.",
        "Unavailable evidence stays visible.",
        "Missing GitHub metadata is not treated as proof of no commits, no PRs, or no CI.",
        "Scanner-unavailable sections cannot claim full scanner-clean status.",
        "CI workflow presence alone cannot lift scores; parsed evidence artifact contents are required.",
        "Human review is required before client-facing delivery.",
    ]
    output["human_review_required"] = True
    return _apply_language(output)
