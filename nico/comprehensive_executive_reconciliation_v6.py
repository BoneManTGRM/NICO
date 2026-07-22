from __future__ import annotations

import os
import re
from copy import deepcopy
from typing import Any, Iterable

VERSION = "nico.comprehensive_executive_reconciliation.v6"

CONTROL_WEIGHTS = {
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


def _lower(value: Any) -> str:
    return _text(value).casefold()


def _tool_failures(section: dict[str, Any]) -> set[str]:
    combined = " ".join(
        _text(item)
        for item in [*(section.get("findings") or []), *(section.get("unavailable") or [])]
    )
    return {
        match.group(1).casefold()
        for match in re.finditer(
            r"\b(bandit|semgrep|eslint|typescript|gitleaks|trufflehog|pip-audit|npm-audit|osv-scanner)\b[^.;]{0,120}\b(failed|timeout|unavailable|truncated)\b",
            combined,
            re.I,
        )
    }


def _static_should_be_unscored(section: dict[str, Any]) -> bool:
    failed = _tool_failures(section) & {"bandit", "semgrep", "eslint", "typescript"}
    evidence = " ".join(_text(item) for item in section.get("evidence") or [])
    findings = " ".join(_text(item) for item in section.get("findings") or [])
    candidate_match = re.search(r"review[_ -]?required\D+(\d+)", evidence, re.I)
    material_match = re.search(r"material\D+(\d+)", evidence, re.I)
    review_count = int(candidate_match.group(1)) if candidate_match else 0
    material_count = int(material_match.group(1)) if material_match else 0
    has_verified_blocker = any(
        phrase in _lower(findings)
        for phrase in ("verified critical", "confirmed critical", "verified blocker")
    )
    return bool(failed) and not has_verified_blocker and (review_count > 0 or material_count > 0)


def _display_name_from_location(location: Any) -> str:
    path = _text(location).split(":", 1)[0]
    if not path:
        return "Measured source module"
    name = os.path.basename(path)
    for suffix in (".tsx", ".ts", ".jsx", ".js", ".py"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name or "Measured source module"


def _normalize_finding(record: dict[str, Any]) -> dict[str, Any]:
    item = deepcopy(record)
    title = _text(item.get("title"))
    location = _text(item.get("location"))
    evidence = _lower(item.get("evidence"))
    category = _lower(item.get("category"))

    if "<module-logic>" in title:
        title = title.replace("<module-logic>", f"{_display_name_from_location(location)} module")

    verified_false = "verified=false" in evidence
    medium_or_unknown = "severity=medium" in evidence or "severity=unknown" in evidence
    if verified_false and medium_or_unknown:
        item["priority"] = "P2"
        item["confidence"] = "candidate"
        item["impact"] = "This unverified analyzer candidate requires review before business impact or remediation priority is confirmed."

    if category == "evidence":
        item["priority"] = "P1"
    elif category == "architecture" and "complexity hotspot" in title.casefold():
        item["priority"] = "P1" if re.search(r"cyclomatic_complexity=(?:[8-9]\d|\d{3,})", evidence) else "P2"

    item["title"] = title
    return item


def _dedupe(records: Iterable[dict[str, Any]], limit: int = 28) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    priority_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    normalized = [_normalize_finding(item) for item in records if isinstance(item, dict)]
    for item in sorted(
        normalized,
        key=lambda value: (
            priority_order.get(_text(value.get("priority")), 9),
            _text(value.get("category")),
            _text(value.get("location")),
        ),
    ):
        key = (
            _lower(item.get("title")),
            _lower(item.get("location")),
            _lower(item.get("category")),
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _risk(
    risk_id: str,
    priority: str,
    title: str,
    impact: str,
    confidence: str,
    action: str,
    instances: int,
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "priority": priority,
        "title": title,
        "impact": impact,
        "confidence": confidence,
        "recommendation": action,
        "instance_count": instances,
    }


def _executive_risks(findings: list[dict[str, Any]], sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    architecture = [item for item in findings if _lower(item.get("category")) == "architecture"]
    static = [item for item in findings if _lower(item.get("category")) == "static"]
    dependencies = [item for item in findings if _lower(item.get("category")) == "dependency"]
    code = [item for item in findings if _lower(item.get("category")) == "code"]
    evidence = [item for item in findings if _lower(item.get("category")) == "evidence"]

    if architecture:
        top = architecture[:4]
        names = ", ".join(_display_name_from_location(item.get("location")) for item in top)
        risks.append(_risk(
            "concentrated-complexity",
            "P1",
            "Concentrated frontend and workflow complexity",
            f"{len(architecture)} measured hotspot(s), led by {names}, increase regression risk and review cost.",
            "moderate",
            "Decompose the highest-complexity modules first, add characterization tests, and enforce complexity thresholds in CI.",
            len(architecture),
        ))
    if evidence:
        tools = sorted({_text(item.get("title")).split(" ", 1)[0] for item in evidence})
        risks.append(_risk(
            "scanner-evidence-incomplete",
            "P1",
            "Scanner evidence is incomplete",
            "Required analyzer failures or truncated output prevent verified assurance and make raw candidate counts unsuitable as definitive technical conclusions.",
            "high",
            f"Repair and rerun {', '.join(tools) or 'the affected analyzers'} twice against the same immutable SHA before assigning a final score.",
            len(evidence),
        ))
    if static:
        mutable = [item for item in static if "mutable-action-tag" in _lower(item.get("title"))]
        if mutable:
            risks.append(_risk(
                "mutable-actions",
                "P2",
                "GitHub Actions use mutable action references",
                f"{len(mutable)} unverified medium-severity workflow candidate(s) may weaken supply-chain reproducibility.",
                "candidate",
                "Validate each workflow finding and pin accepted third-party actions to immutable commit SHAs.",
                len(mutable),
            ))
        other_static = [item for item in static if item not in mutable]
        if other_static:
            risks.append(_risk(
                "static-candidates",
                "P2",
                "Static-analysis candidates require disposition",
                f"{len(other_static)} additional analyzer candidate(s) remain unverified and should not be presented as confirmed defects.",
                "candidate",
                "Group by rule, triage representative instances, record bounded exceptions, and rerun the originating analyzer.",
                len(other_static),
            ))
    if dependencies:
        risks.append(_risk(
            "dependency-candidates",
            "P1" if any(_text(item.get("priority")) in {"P0", "P1"} for item in dependencies) else "P2",
            "Dependency findings require remediation or acceptance",
            f"{len(dependencies)} dependency finding(s) require exploitability review and exact-version disposition.",
            "moderate",
            "Confirm affected versions, upgrade or constrain dependencies, regenerate lockfiles, and rerun all dependency analyzers.",
            len(dependencies),
        ))
    ci = next((section for section in sections if section.get("id") == "ci_cd"), {})
    ci_findings = " ".join(_text(item) for item in ci.get("findings") or [])
    match = re.search(r"(\d+) non-success", ci_findings, re.I)
    if match:
        count = int(match.group(1))
        risks.append(_risk(
            "ci-history",
            "P1",
            "Historical CI failures are not yet cause-classified",
            f"{count} retained non-success workflow run(s) obscure release reliability until expected cancellations and real failures are separated.",
            "high",
            "Classify every non-success run by cause and publish a rolling reliability trend with recurring failure classes assigned to owners.",
            count,
        ))
    if code:
        risks.append(_risk(
            "code-risk-patterns",
            "P2",
            "Bounded code-risk patterns require exact-location review",
            f"{len(code)} sampled pattern hit(s) require human validation; pattern matching alone does not establish exploitability.",
            "moderate",
            "Triage each exact location, consolidate duplicate rule instances, remediate confirmed unsafe paths, and rerun against the same SHA.",
            len(code),
        ))
    return sorted(risks, key=lambda item: ({"P0": 0, "P1": 1, "P2": 2}.get(item["priority"], 9), item["title"]))[:8]


def _weighted_maturity(sections: list[dict[str, Any]]) -> tuple[int | None, list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    numerator = 0.0
    denominator = 0.0
    for section in sections:
        section_id = _text(section.get("id"))
        weight = CONTROL_WEIGHTS.get(section_id, 0.0)
        score = section.get("score_value")
        scored = isinstance(score, (int, float)) and not section.get("exclude_from_maturity")
        contribution = round(float(score) * weight, 2) if scored else None
        if scored and weight:
            numerator += float(score) * weight
            denominator += weight
        rows.append({
            "control": section.get("label") or section_id,
            "control_id": section_id,
            "weight": weight,
            "weight_display": f"{int(weight * 100)}%" if weight else "—",
            "score": int(score) if scored else None,
            "weighted_contribution": contribution,
            "assurance": section.get("assurance_label") or "HUMAN REVIEW PENDING",
            "included": bool(scored and weight),
        })
    return (round(numerator / denominator) if denominator else None), rows


def reconcile_comprehensive_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    sections = [item for item in output.get("sections") or [] if isinstance(item, dict)]

    for section in sections:
        if section.get("id") == "static_analysis" and _static_should_be_unscored(section):
            source_score = section.get("score_value", section.get("presented_score", section.get("score")))
            section.update({
                "source_score_before_evidence_gate": source_score,
                "score": None,
                "presented_score": None,
                "score_value": None,
                "score_band": "not_scored",
                "score_band_label": "NOT SCORED",
                "score_tone": "gray",
                "technical_score_display": "NOT SCORED",
                "status": "red",
                "presented_status": "red",
                "assurance_status": "blocked",
                "assurance_label": "BLOCKED",
                "assurance_tone": "red",
                "assurance_display": "BLOCKED",
                "exclude_from_maturity": True,
                "score_treatment": "unscored_incomplete_analyzer_evidence",
                "summary": "Static-analysis evidence is incomplete. Candidate counts and a failed analyzer constrain assurance but do not establish a Critical technical-health score.",
            })

    findings = _dedupe(output.get("findings_register") or [])
    overall, weighting = _weighted_maturity(sections)
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    maturity["source_score_before_reconciliation"] = maturity.get("presented_score", maturity.get("score"))
    maturity["score"] = overall
    maturity["presented_score"] = overall
    if overall is None:
        maturity.update({"score_band": "not_scored", "score_band_label": "NOT SCORED", "score_tone": "gray"})
    elif overall >= 90:
        maturity.update({"score_band": "exceptional", "score_band_label": "EXCEPTIONAL", "score_tone": "green"})
    elif overall >= 80:
        maturity.update({"score_band": "strong", "score_band_label": "STRONG", "score_tone": "green"})
    elif overall >= 70:
        maturity.update({"score_band": "moderate", "score_band_label": "MODERATE", "score_tone": "yellow"})
    elif overall >= 55:
        maturity.update({"score_band": "weak", "score_band_label": "WEAK", "score_tone": "red"})
    else:
        maturity.update({"score_band": "critical", "score_band_label": "CRITICAL", "score_tone": "red"})

    output["sections"] = sections
    output["findings_register"] = findings
    output["executive_risk_register"] = _executive_risks(findings, sections)
    output["scoring_weight_table"] = weighting
    output["maturity_signal"] = maturity
    output["executive_report_target_pages"] = "12-16 excluding evidence appendix"
    output["comprehensive_executive_reconciliation"] = {
        "status": "complete",
        "version": VERSION,
        "incomplete_static_analysis_unscored": True,
        "unverified_medium_candidates_not_p1": True,
        "internal_module_labels_removed": True,
        "executive_risks_consolidated": True,
        "weighted_score_excludes_unscored_controls": True,
    }
    return output


__all__ = ["VERSION", "CONTROL_WEIGHTS", "reconcile_comprehensive_assessment"]
