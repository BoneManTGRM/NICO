"""Build an evidence-bound client value scorecard from verified findings."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TIERS = ("express", "mid", "full")
MIN_FINDINGS = {"express": 3, "mid": 7, "full": 12}


def build_client_value_scorecard(
    tier: str,
    findings: Sequence[Mapping[str, Any]],
    *,
    assessment_id: str,
    report_sha256: str,
) -> dict[str, Any]:
    """Return quantified decision utility without inventing unsupported value."""
    normalized_tier = str(tier).lower().strip()
    failures: list[str] = []
    if normalized_tier not in TIERS:
        failures.append("invalid_tier")
    if not assessment_id.strip():
        failures.append("missing_assessment_id")
    if len(report_sha256) != 64:
        failures.append("invalid_report_sha256")
    if len(findings) < MIN_FINDINGS.get(normalized_tier, 1):
        failures.append("insufficient_findings")

    verified: list[dict[str, Any]] = []
    for index, finding in enumerate(findings):
        prefix = f"finding_{index}"
        required = (
            "title",
            "evidence_reference",
            "business_consequence",
            "remediation",
            "owner",
            "priority",
            "confidence",
        )
        missing = [field for field in required if not str(finding.get(field, "")).strip()]
        if missing:
            failures.append(f"{prefix}:missing:{','.join(missing)}")
            continue
        if finding.get("evidence_verified") is not True:
            failures.append(f"{prefix}:evidence_unverified")
            continue

        try:
            exposure = max(0.0, float(finding.get("estimated_exposure", 0)))
            remediation_cost = max(0.0, float(finding.get("estimated_remediation_cost", 0)))
            confidence = float(finding.get("confidence", 0))
        except (TypeError, ValueError):
            failures.append(f"{prefix}:invalid_numeric_value")
            continue
        if not 0 <= confidence <= 100:
            failures.append(f"{prefix}:invalid_confidence")
            continue

        verified.append(
            {
                "title": str(finding["title"]),
                "priority": str(finding["priority"]),
                "owner": str(finding["owner"]),
                "estimated_exposure": exposure,
                "estimated_remediation_cost": remediation_cost,
                "risk_adjusted_exposure": exposure * confidence / 100.0,
                "net_potential_value": max(0.0, exposure - remediation_cost),
                "confidence": confidence,
                "business_consequence": str(finding["business_consequence"]),
                "remediation": str(finding["remediation"]),
                "evidence_reference": str(finding["evidence_reference"]),
            }
        )

    verified.sort(
        key=lambda item: (item["risk_adjusted_exposure"], item["confidence"]),
        reverse=True,
    )
    total_exposure = sum(item["estimated_exposure"] for item in verified)
    total_remediation = sum(item["estimated_remediation_cost"] for item in verified)
    risk_adjusted = sum(item["risk_adjusted_exposure"] for item in verified)
    net_value = sum(item["net_potential_value"] for item in verified)

    return {
        "status": "complete" if not failures else "blocked",
        "assessment_id": assessment_id,
        "report_sha256": report_sha256,
        "tier": normalized_tier,
        "failures": sorted(set(failures)),
        "verified_finding_count": len(verified),
        "total_estimated_exposure": round(total_exposure, 2),
        "total_estimated_remediation_cost": round(total_remediation, 2),
        "risk_adjusted_exposure": round(risk_adjusted, 2),
        "net_potential_value": round(net_value, 2),
        "top_decisions": verified[:5],
    }
