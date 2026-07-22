from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any

VERSION = "nico.comprehensive_premium_synthesis.v6"

SECTION_WEIGHTS = {
    "code_audit": 0.20,
    "dependency_health": 0.15,
    "secrets_review": 0.15,
    "static_analysis": 0.15,
    "ci_cd": 0.15,
    "architecture_debt": 0.15,
    "velocity_complexity": 0.05,
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _component_name(location: Any) -> str:
    value = _text(location).split(":", 1)[0]
    name = PurePosixPath(value).name or "measured module"
    for suffix in (".tsx", ".ts", ".jsx", ".js", ".py"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name or "measured module"


def _normalize_finding(record: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(record)
    title = _text(item.get("title"))
    category = _text(item.get("category")).casefold()
    confidence = _text(item.get("confidence")).casefold()
    evidence = _text(item.get("evidence")).casefold()

    if "<module-logic>" in title:
        item["title"] = title.replace("<module-logic>", f"{_component_name(item.get('location'))} module")

    unverified = "verified=false" in evidence or confidence not in {"high", "verified"}
    severity_medium_or_lower = any(token in evidence for token in ("severity=medium", "severity=low", "severity=unknown"))
    if unverified and severity_medium_or_lower and item.get("priority") in {"P0", "P1"}:
        item["priority"] = "P2"

    if category == "static" and unverified:
        item["impact"] = "This analyzer candidate requires validation before it can be treated as a confirmed technical defect."
        item["recommendation"] = (
            "Validate the rule against the exact file and revision, group equivalent instances, then remediate or approve a bounded exception."
        )
        item["acceptance_criteria"] = (
            "The originating analyzer completes on the exact SHA and the grouped candidate is resolved or approved with traceable rationale."
        )

    return item


def _dedupe_detailed(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in records:
        if not isinstance(raw, dict):
            continue
        item = _normalize_finding(raw)
        key = (
            _text(item.get("category")).casefold(),
            _text(item.get("title")).casefold(),
            _text(item.get("location")).casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _consolidate_executive(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        category = _text(item.get("category")).casefold() or "other"
        groups.setdefault(category, []).append(item)

    executive: list[dict[str, Any]] = []

    architecture = groups.get("architecture", [])
    if architecture:
        names = [_component_name(item.get("location")) for item in architecture[:4]]
        executive.append({
            "priority": "P1",
            "title": "Concentrated frontend complexity",
            "impact": "Large, highly branched modules increase regression risk, review cost, and the difficulty of safe change.",
            "confidence": "moderate",
            "recommendation": "Decompose the highest-complexity modules first, beginning with " + ", ".join(names) + ", and add characterization tests plus CI complexity thresholds.",
        })

    evidence = groups.get("evidence", [])
    if evidence:
        executive.append({
            "priority": "P1",
            "title": "Static-analysis evidence incomplete",
            "impact": "Incomplete analyzer execution prevents a defensible technical conclusion for the affected control.",
            "confidence": "high",
            "recommendation": "Repair the failed analyzer boundary and retain two consecutive exact-SHA successful runs before assigning a technical score.",
        })

    static = groups.get("static", [])
    if static:
        count = len(static)
        executive.append({
            "priority": "P2",
            "title": f"{count} grouped static-analysis candidates require validation",
            "impact": "Unverified medium-severity candidates may represent real hardening opportunities, but they are not yet confirmed defects.",
            "confidence": "moderate",
            "recommendation": "Group equivalent rules, validate representative instances, and remediate confirmed issues by theme rather than repeating identical work items.",
        })

    dependency = groups.get("dependency", [])
    if dependency:
        executive.append({
            "priority": "P1" if any(item.get("priority") in {"P0", "P1"} for item in dependency) else "P2",
            "title": "Dependency findings require disposition",
            "impact": "Confirmed vulnerable or unsupported dependencies can create security, stability, and maintenance exposure.",
            "confidence": "high" if any(item.get("priority") == "P0" for item in dependency) else "moderate",
            "recommendation": "Triage the retained dependency findings, upgrade or constrain affected packages, regenerate lockfiles, and rerun all dependency analyzers.",
        })

    secret = groups.get("secret", [])
    if secret:
        executive.append({
            "priority": "P1" if any(item.get("priority") in {"P0", "P1"} for item in secret) else "P2",
            "title": "Secret-history assurance remains review-limited",
            "impact": "Incomplete or unverified history coverage prevents a clean credential-exposure conclusion.",
            "confidence": "moderate",
            "recommendation": "Complete history scanning, validate retained candidates without exposing raw values, and rotate any confirmed live credential.",
        })

    ci_cd = groups.get("ci_cd", [])
    if ci_cd:
        executive.append({
            "priority": "P1",
            "title": "Historical CI failures need cause classification",
            "impact": "Unclassified non-success runs obscure release reliability and can conceal recurring operational defects.",
            "confidence": "high",
            "recommendation": "Separate cancellations from failures, classify recurring causes, assign owners, and publish a rolling reliability trend.",
        })

    code = groups.get("code", [])
    if code:
        executive.append({
            "priority": "P2",
            "title": "Bounded code-risk patterns require exact-location review",
            "impact": "Pattern matches may indicate unsafe APIs or may be benign framework behavior; confirmation is required before escalation.",
            "confidence": "moderate",
            "recommendation": "Review the retained locations as one remediation theme, disposition each match, and rerun against the same immutable revision.",
        })

    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    return sorted(executive, key=lambda item: (order.get(str(item.get("priority")), 9), str(item.get("title"))))[:8]


def _static_is_incomplete(section: dict[str, Any]) -> bool:
    findings = " ".join(_text(item).casefold() for item in section.get("findings") or [])
    unavailable = " ".join(_text(item).casefold() for item in section.get("unavailable") or [])
    evidence = " ".join(_text(item).casefold() for item in section.get("evidence") or [])
    failed = "failed static" in findings or "failed static" in evidence or "bandit" in unavailable
    review_required = "review_required=" in evidence or "require human triage" in findings
    return failed and review_required


def _weighted_maturity(sections: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    weighted_sum = 0.0
    active_weight = 0.0
    for section in sections:
        section_id = _text(section.get("id"))
        weight = SECTION_WEIGHTS.get(section_id, 0.0)
        score = section.get("score_value")
        scored = isinstance(score, (int, float)) and section.get("exclude_from_maturity") is not True
        contribution = round(float(score) * weight, 2) if scored else None
        rows.append({
            "control": section.get("label") or section_id,
            "section_id": section_id,
            "weight": weight,
            "weight_percent": round(weight * 100),
            "technical_score": int(score) if scored else None,
            "weighted_contribution": contribution,
            "assurance": section.get("assurance_label"),
            "included": scored,
        })
        if scored:
            weighted_sum += float(score) * weight
            active_weight += weight
    if active_weight <= 0:
        return None, rows
    return round(weighted_sum / active_weight), rows


def _band(score: int | None) -> tuple[str, str]:
    if score is None:
        return "not_scored", "NOT SCORED"
    if score >= 90:
        return "exceptional", "EXCEPTIONAL"
    if score >= 80:
        return "strong", "STRONG"
    if score >= 70:
        return "moderate", "MODERATE"
    if score >= 55:
        return "weak", "WEAK"
    return "critical", "CRITICAL"


def polish_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    sections = [item for item in output.get("sections") or [] if isinstance(item, dict)]

    for section in sections:
        if section.get("id") == "static_analysis" and _static_is_incomplete(section):
            source_score = section.get("score_value", section.get("presented_score", section.get("score")))
            section["source_score_before_evidence_gate"] = source_score
            section["score"] = None
            section["presented_score"] = None
            section["score_value"] = None
            section["score_band"] = "not_scored"
            section["score_band_label"] = "NOT SCORED"
            section["technical_score_display"] = "NOT SCORED"
            section["exclude_from_maturity"] = True
            section["status"] = "red"
            section["presented_status"] = "red"
            section["assurance_status"] = "blocked"
            section["assurance_label"] = "BLOCKED"
            section["assurance_display"] = "BLOCKED"
            section["summary"] = (
                "Static Analysis is not scored because required current-run analyzer evidence is incomplete. "
                "Candidate findings remain visible for human disposition without being treated as proven critical code quality."
            )

    detailed = _dedupe_detailed([item for item in output.get("findings_register") or [] if isinstance(item, dict)])
    output["findings_register"] = detailed
    output["executive_risk_register"] = _consolidate_executive(detailed)

    overall, weighting = _weighted_maturity(sections)
    key, label = _band(overall)
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    maturity["source_score_before_weighted_reconciliation"] = maturity.get("presented_score", maturity.get("score"))
    maturity["score"] = overall
    maturity["presented_score"] = overall
    maturity["score_band"] = key
    maturity["score_band_label"] = label
    maturity["scoring_method"] = "weighted_scored_controls_only_v6"
    maturity["unscored_controls_excluded"] = [row["section_id"] for row in weighting if not row["included"]]
    output["maturity_signal"] = maturity
    output["scoring_weights"] = weighting
    output["sections"] = sections
    output["premium_synthesis"] = {
        "status": "complete",
        "version": VERSION,
        "executive_risks_consolidated": True,
        "unverified_medium_candidates_not_p1": True,
        "internal_module_labels_removed": True,
        "incomplete_static_analysis_not_scored": True,
        "weighted_scoring_explicit": True,
    }
    return output


__all__ = ["VERSION", "SECTION_WEIGHTS", "polish_assessment"]
