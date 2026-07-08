from __future__ import annotations

import re
from typing import Any

SECTION_HEADER_RE = re.compile(
    r"(?P<label>Dependency / Library Ecosystem|Static Analysis|Secrets Exposure Review|Velocity / Complexity)[^\n]{0,80}\bGREEN\b[^\n]*",
    re.IGNORECASE,
)
SCORE_RE = re.compile(r"\bSCORE\s+(?P<score>\d{1,3})\s*/\s*100\b", re.IGNORECASE)

REVIEW_LIMITED_MARKERS = (
    "review-limited",
    "unavailable",
    "not attached",
    "not verified",
    "still required",
    "missing",
    "completed_with_findings",
    "review_required",
    "needs_human_review",
)

SECTION_RISK_MARKERS = {
    "dependency": ("osv", "pip-audit", "npm audit", "npm-audit", "osv-scanner", "vulnerability"),
    "static": ("bandit", "semgrep", "eslint", "typescript", "finding"),
    "secrets": ("gitleaks", "trufflehog", "full-history", "credential"),
    "velocity": ("release-readiness", "complexity", "final-clean"),
}


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(_text(item) for item in value)
    return str(value or "")


def _section_text(section: dict[str, Any]) -> str:
    return "\n".join(_text(section.get(key)) for key in ("summary", "evidence", "findings", "unavailable"))


def _section_kind(section: dict[str, Any]) -> str | None:
    key = f"{section.get('id', '')} {section.get('label', '')}".lower()
    if "dependency" in key or "library" in key:
        return "dependency"
    if "static" in key:
        return "static"
    if "secret" in key:
        return "secrets"
    if "velocity" in key or "complexity" in key:
        return "velocity"
    return None


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(marker in lower for marker in markers)


def _json_green_contradictions(result: dict[str, Any]) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for section in result.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        if section.get("status") != "green":
            continue
        kind = _section_kind(section)
        if not kind:
            continue
        text = _section_text(section)
        if _has_any(text, REVIEW_LIMITED_MARKERS) and _has_any(text, SECTION_RISK_MARKERS[kind]):
            violations.append(
                {
                    "type": "json_green_contradiction",
                    "section": section.get("label") or section.get("id"),
                    "reason": f"{kind} section is GREEN while section text discloses missing, unavailable, or review-limited evidence.",
                }
            )
    return violations


def _export_green_contradictions(result: dict[str, Any]) -> list[dict[str, Any]]:
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    export_text = "\n".join(str(reports.get(key) or "") for key in ("markdown", "html"))
    lower = export_text.lower()
    violations: list[dict[str, Any]] = []
    if not export_text.strip():
        violations.append({"type": "missing_export_text", "section": "reports", "reason": "Markdown/HTML export text is empty after report rebuild."})
        return violations
    for match in SECTION_HEADER_RE.finditer(export_text):
        label = match.group("label")
        start = max(0, match.start() - 500)
        end = min(len(export_text), match.end() + 1200)
        window = export_text[start:end].lower()
        section_key = "dependency" if "dependency" in label.lower() else "static" if "static" in label.lower() else "secrets" if "secrets" in label.lower() else "velocity"
        if _has_any(window, REVIEW_LIMITED_MARKERS) and _has_any(window, SECTION_RISK_MARKERS[section_key]):
            violations.append(
                {
                    "type": "export_green_contradiction",
                    "section": label,
                    "reason": "Rendered report shows GREEN while nearby export text discloses missing, unavailable, or review-limited evidence.",
                }
            )
    if "trust level: review-limited" in lower and "delivery verdict" in lower and "human review" not in lower:
        violations.append(
            {
                "type": "trust_delivery_mismatch",
                "section": "delivery_verdict",
                "reason": "Rendered report is review-limited but does not clearly show human review required.",
            }
        )
    return violations


def _score_mismatch(result: dict[str, Any]) -> list[dict[str, Any]]:
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    export_text = "\n".join(str(reports.get(key) or "") for key in ("markdown", "html"))
    expected = None
    if isinstance(result.get("maturity_signal"), dict):
        try:
            expected = int(result["maturity_signal"].get("score"))
        except (TypeError, ValueError):
            expected = None
    if expected is None:
        return []
    match = SCORE_RE.search(export_text)
    if not match:
        return []
    exported = int(match.group("score"))
    if exported != expected:
        return [
            {
                "type": "score_mismatch",
                "section": "maturity_signal",
                "reason": f"Rendered score {exported} does not match final JSON score {expected}.",
            }
        ]
    return []


def _blocked_report(result: dict[str, Any], violations: list[dict[str, Any]]) -> str:
    score = result.get("maturity_signal", {}).get("score") if isinstance(result.get("maturity_signal"), dict) else "unknown"
    lines = [
        "# NICO Export Blocked",
        "",
        "This client-facing export was blocked by the Export Truth Gate because rendered report output contradicted final evidence state.",
        "",
        f"Final JSON score: {score}",
        "Delivery verdict: human review required",
        "",
        "## Blocking issues",
    ]
    for violation in violations:
        lines.append(f"- {violation.get('section')}: {violation.get('reason')}")
    lines.extend(
        [
            "",
            "## Required repair",
            "Re-run final report QA, strict trust engine, evidence ledger attachment, and report rebuild before client delivery.",
        ]
    )
    return "\n".join(lines)


def apply_export_truth_gate(result: dict[str, Any]) -> dict[str, Any]:
    """Validate rendered report exports against the final JSON evidence state.

    This gate runs after report rebuild. It blocks client-facing exports if the
    JSON or rendered Markdown/HTML still show green contradictions, score drift,
    or missing export text.
    """

    if result.get("status") != "complete":
        return result
    violations = _json_green_contradictions(result) + _export_green_contradictions(result) + _score_mismatch(result)
    gate = {
        "version": "export-truth-gate-v1",
        "status": "failed" if violations else "passed",
        "export_allowed": not violations,
        "violations": violations,
        "rules": [
            "no_green_json_section_with_review_limited_evidence",
            "no_green_rendered_section_with_nearby_missing_or_unavailable_evidence",
            "rendered_score_matches_final_json_score",
            "rendered_exports_must_not_be_empty",
        ],
    }
    result["export_truth_gate"] = gate
    result.setdefault("report_quality_guards", {})["export_truth_gate"] = {
        "status": gate["status"],
        "export_allowed": gate["export_allowed"],
        "violation_count": len(violations),
    }
    if violations:
        result["delivery_verdict"] = "human_review_required"
        result["client_ready"] = False
        reports = result.setdefault("reports", {})
        blocked = _blocked_report(result, violations)
        reports["markdown"] = blocked
        reports["html"] = "<pre>" + blocked.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>"
        reports["pdf_base64"] = ""
    return result
