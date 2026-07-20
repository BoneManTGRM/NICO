from __future__ import annotations

import re
from typing import Any

VERSION = "nico.express_scanner_disposition_truth.v1"

_TOOL_NAMES = (
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
)
_STATUS_ORDER = {
    "failed": 7,
    "timeout": 6,
    "unavailable": 5,
    "completed_findings": 4,
    "completed_triaged": 3,
    "completed_clean": 2,
    "completed": 1,
    "unknown": 0,
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _count(text: str) -> int | None:
    match = re.search(r"findings?\s*[=:]\s*(\d+)|returned\s+(\d+)\s+finding", text, re.I)
    if not match:
        return None
    return int(next(group for group in match.groups() if group is not None))


def _tool_from_text(text: str) -> str | None:
    lowered = text.casefold()
    for tool in _TOOL_NAMES:
        if tool in lowered:
            return tool
    return None


def _classify(text: str) -> tuple[str, int | None]:
    lowered = text.casefold()
    findings = _count(text)
    if any(token in lowered for token in ("status=failed", "status failed", "ended with status failed", "reported failure")):
        return "failed", findings
    if any(token in lowered for token in ("status=timeout", "status timeout", "ended with status timeout", "timed out")):
        return "timeout", findings
    if "unavailable" in lowered or "no eslint configuration" in lowered:
        return "unavailable", findings
    if findings is not None and findings > 0:
        return "completed_findings", findings
    if findings == 0 or any(token in lowered for token in ("zero vulnerability", "no vulnerability", "reported zero", "findings=0")):
        return "completed_clean", 0
    if "status=completed" in lowered or "status completed" in lowered or "completed:" in lowered:
        return "completed", findings
    return "unknown", findings


def _merge_disposition(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None:
        return candidate
    current_rank = _STATUS_ORDER.get(str(current.get("status")), 0)
    candidate_rank = _STATUS_ORDER.get(str(candidate.get("status")), 0)
    if candidate_rank > current_rank:
        winner, other = candidate, current
    else:
        winner, other = current, candidate
    evidence = list(winner.get("source_statements") or [])
    for item in other.get("source_statements") or []:
        if item not in evidence:
            evidence.append(item)
    winner = dict(winner)
    winner["source_statements"] = evidence
    counts = [value for value in (winner.get("findings"), other.get("findings")) if isinstance(value, int)]
    winner["findings"] = max(counts) if counts else None
    return winner


def _dispositions(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for field in ("evidence", "findings", "unavailable", "limitations"):
        for raw in section.get(field) or []:
            statement = _text(raw)
            tool = _tool_from_text(statement)
            if not tool:
                continue
            status, findings = _classify(statement)
            candidate = {
                "tool": tool,
                "status": status,
                "findings": findings,
                "source_statements": [statement],
            }
            output[tool] = _merge_disposition(output.get(tool), candidate)
    return output


def _status_line(item: dict[str, Any]) -> str:
    tool = str(item["tool"])
    status = str(item["status"])
    findings = item.get("findings")
    if status == "completed_clean":
        return f"Canonical scanner disposition: {tool}=completed_clean; verified findings=0."
    if status == "completed_triaged":
        return f"Canonical scanner disposition: {tool}=completed_with_candidates; candidates={findings}; signed triage resolved all candidates with no unresolved blocker."
    if status == "completed_findings":
        return f"Canonical scanner disposition: {tool}=completed_with_candidates; candidates={findings}; human triage required."
    if status == "failed":
        return f"Canonical scanner disposition: {tool}=failed; no clean conclusion permitted."
    if status == "timeout":
        return f"Canonical scanner disposition: {tool}=timed_out; partial output is review-only and no clean conclusion is permitted."
    if status == "unavailable":
        return f"Canonical scanner disposition: {tool}=unavailable; the missing analyzer is disclosed and not substituted by another tool."
    return f"Canonical scanner disposition: {tool}={status}; no stronger conclusion is inferred."


def _static_summary(dispositions: dict[str, dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "unknown") for item in dispositions.values()}
    if statuses & {"failed", "timeout", "unavailable", "completed_findings"}:
        return "Static analysis reports each analyzer independently; unresolved failures, timeouts, unavailable analyzers, and candidate findings remain explicitly separated from completed evidence."
    if statuses:
        return "Static analysis reports each completed analyzer independently and preserves its canonical disposition without overstating the evidence."
    return "Static analysis preserves the existing evidence state; no scanner disposition is inferred without a named analyzer statement."


def _replace_scope_conflicts(section: dict[str, Any], dispositions: dict[str, dict[str, Any]]) -> None:
    section_id = _text(section.get("id")).casefold()
    evidence = [_text(value) for value in section.get("evidence") or [] if _text(value)]
    findings = [_text(value) for value in section.get("findings") or [] if _text(value)]

    if section_id == "dependency_health":
        osv = dispositions.get("osv-scanner")
        if osv and osv.get("status") == "completed_findings":
            evidence = [
                "Direct pinned-package vulnerability queries returned no records for their bounded query set; the exact-snapshot OSV repository scan returned candidate records and therefore controls the final disposition."
                if "osv returned no vulnerability" in item.casefold()
                else item
                for item in evidence
            ]
            section["summary"] = "Dependency review combines clean package-audit evidence with unresolved exact-snapshot OSV candidates; the section remains review-limited until those candidates are triaged."

    if section_id == "secrets_review":
        if any(item.get("status") in {"timeout", "failed", "completed_findings"} for item in dispositions.values()):
            findings = [
                re.sub(r"reported\s+(\d+)\s+finding\(s\)", r"reported \1 raw candidate(s)", item, flags=re.I)
                for item in findings
            ]
            section["summary"] = "Secrets review reports scanner candidates, failures, and timeouts as review-limited evidence; it does not establish credential exposure until exact locations and values are triaged."

    if section_id == "static_analysis":
        section["summary"] = _static_summary(dispositions)
        if dispositions.get("bandit", {}).get("status") == "failed":
            evidence = [
                item.replace(
                    "Static review finding reconciliation: clean Bandit triage supersedes raw Bandit finding count for release-readiness gating.",
                    "Bandit triage metadata is retained for reviewer prioritization, but the failed Bandit execution prevents a clean Bandit conclusion.",
                )
                for item in evidence
            ]

    canonical_lines = [_status_line(dispositions[name]) for name in sorted(dispositions)]
    evidence = [item for item in evidence if not item.startswith("Canonical scanner disposition:")]
    section["evidence"] = [*evidence, *canonical_lines]
    section["findings"] = findings


def _apply_resolved_triage(result: dict[str, Any], section_id: str, dispositions: dict[str, dict[str, Any]]) -> None:
    if section_id != "static_analysis":
        return
    triage = result.get("bandit_triage")
    if not isinstance(triage, dict):
        return
    if triage.get("status") != "approved_no_blockers" or int(triage.get("review_required_count") or 0) != 0:
        return
    bandit = dispositions.get("bandit")
    if bandit and bandit.get("status") == "completed_findings":
        bandit["status"] = "completed_triaged"
        bandit["triage_status"] = "approved_no_blockers"


def reconcile_express_scanner_dispositions(result: dict[str, Any]) -> dict[str, Any]:
    all_dispositions: dict[str, dict[str, Any]] = {}
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        if section_id not in {"dependency_health", "secrets_review", "static_analysis", "scanner_worker_evidence"}:
            continue
        dispositions = _dispositions(section)
        _apply_resolved_triage(result, section_id, dispositions)
        section["scanner_dispositions"] = dispositions
        _replace_scope_conflicts(section, dispositions)
        for name, item in dispositions.items():
            all_dispositions[name] = _merge_disposition(all_dispositions.get(name), item)

    result["scanner_dispositions"] = all_dispositions
    unresolved_statuses = {"failed", "timeout", "unavailable", "completed_findings", "unknown"}
    unresolved = any(str(item.get("status")) in unresolved_statuses for item in all_dispositions.values())
    result["express_scanner_disposition_truth"] = {
        "status": "complete",
        "version": VERSION,
        "tool_count": len(all_dispositions),
        "one_canonical_disposition_per_tool": True,
        "scope_conflicts_disclosed": True,
        "failed_or_timed_out_not_clean": True,
        "human_review_required": unresolved,
        "client_delivery_allowed": False,
    }
    return result


def install_express_scanner_disposition_truth_v1() -> dict[str, Any]:
    from nico import express_canonical_truth_finalization_v23 as target

    previous = target._canonicalize_sections
    marker = "_nico_scanner_disposition_truth_v1"
    if getattr(previous, marker, False):
        return {"status": "already_installed", "version": VERSION}

    def canonicalize_sections(result: dict[str, Any]) -> None:
        previous(result)
        reconcile_express_scanner_dispositions(result)

    setattr(canonicalize_sections, marker, True)
    setattr(canonicalize_sections, "_nico_previous", previous)
    target._canonicalize_sections = canonicalize_sections
    return {"status": "installed", "version": VERSION, "canonical_truth_hooked": True}


__all__ = [
    "VERSION",
    "install_express_scanner_disposition_truth_v1",
    "reconcile_express_scanner_dispositions",
]
