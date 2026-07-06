from __future__ import annotations

from typing import Any


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _section(result: dict[str, Any], section_id: str) -> dict[str, Any] | None:
    for item in result.get("sections", []) or []:
        if item.get("id") == section_id:
            return item
    return None


def _metadata_limited(text: str) -> bool:
    lower = text.lower()
    return "github returned 403" in lower or "github returned 429" in lower or "api rate" in lower or "request limit" in lower


def _notes_limited(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    notes = list(item.get("unavailable", []) or []) + list(item.get("evidence", []) or [])
    return any(_metadata_limited(str(note)) for note in notes)


def polish_express_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result

    for item in result.get("sections", []) or []:
        item["evidence"] = _unique(list(item.get("evidence", []) or []))
        item["findings"] = _unique(list(item.get("findings", []) or []))
        item["unavailable"] = _unique(list(item.get("unavailable", []) or []))

    code = _section(result, "code_audit")
    ci = _section(result, "ci_cd")
    velocity = _section(result, "velocity_complexity")
    deps = _section(result, "dependency_health")
    arch = _section(result, "architecture_debt")
    arch_evidence = " ".join((arch or {}).get("evidence", []) or [])
    limited = _notes_limited(code) or _notes_limited(ci) or _notes_limited(velocity)

    if code and _notes_limited(code):
        code["findings"] = [note for note in code.get("findings", []) if "No recent pull-request evidence" not in note]
        code["evidence"] = [note for note in code.get("evidence", []) if "No recent pull-request evidence" not in note]
        code["evidence"].insert(0, "Commit and pull-request metadata were unavailable in this run; missing metadata is not treated as proof of direct-to-main work.")
        code["score"] = max(int(code.get("score", 0)), 55)
        code["status"] = "yellow"

    if ci and (_notes_limited(ci) or "Repository root contains .github/." in arch_evidence):
        if any("No CI/CD workflow" in note or "No GitHub Actions workflow" in note for note in ci.get("evidence", []) + ci.get("findings", [])):
            ci["findings"] = [note for note in ci.get("findings", []) if "No CI/CD workflow" not in note]
            ci["evidence"] = [note for note in ci.get("evidence", []) if "No GitHub Actions workflow" not in note and "No CI/CD workflow" not in note]
            ci["evidence"].insert(0, "CI/CD file metadata was unavailable or incomplete in this run; missing workflow metadata is not treated as proof that CI is absent.")
            ci["score"] = max(int(ci.get("score", 0)), 50)
            ci["status"] = "yellow"

    if velocity and limited:
        velocity["evidence"] = [note for note in velocity.get("evidence", []) if "0 commits over" not in note and "0 PRs / 0 commits" not in note]
        velocity["evidence"].insert(0, "Velocity and PR traceability are degraded because commit or PR metadata was unavailable in this run.")
        velocity["score"] = max(int(velocity.get("score", 0)), 55)
        velocity["status"] = "yellow"

    if deps:
        deps["evidence"] = _unique(deps.get("evidence", []))
        deps["findings"] = _unique(deps.get("findings", []))

    if limited:
        result["assessment_quality"] = "degraded_metadata"
        result["executive_summary"] += " Some GitHub metadata was unavailable, so affected sections are degraded rather than final negative evidence."
        all_findings: list[str] = []
        for item in result.get("sections", []) or []:
            all_findings.extend(item.get("findings", []) or [])
        result["findings"] = _unique(all_findings)
    return result
