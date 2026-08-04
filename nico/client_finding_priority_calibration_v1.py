from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.client-finding-priority-calibration.v1"
MODEL = "evidence-critical-path-priority.v1"
_MARKER = "__nico_client_finding_priority_calibration_v1__"

_PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_SECURITY_TOKENS = (
    "auth",
    "authorization",
    "permission",
    "credential",
    "secret",
    "tls",
    "certificate",
    "security",
)
_DELIVERY_TOKENS = (
    "delivery",
    "release",
    "deploy",
    "publication",
    "production-report",
    "production_report",
    "final-review",
    "final_review",
    "approval",
)
_RECOVERY_TOKENS = (
    "recovery",
    "restore",
    "backup",
    "resilience",
    "restart",
)
_DATA_INTEGRITY_TOKENS = (
    "persistence",
    "storage",
    "repository-snapshot",
    "repository_snapshot",
    "evidence",
    "scoring",
    "score-integrity",
    "score_integrity",
    "truth-gate",
    "truth_gate",
    "manifest",
)
_OPERATIONS_TOKENS = (
    "operations",
    "operational",
    "monitor",
    "alert",
)


def _text(value: Any, limit: int = 6000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _combined(item: Mapping[str, Any]) -> str:
    return " ".join(
        _text(item.get(key), 2500)
        for key in (
            "path",
            "location",
            "symbol",
            "title",
            "decision_title",
            "category",
            "finding_family",
            "rule_id",
            "observed_evidence",
            "fact",
            "business_impact",
            "impact",
            "recommended_correction",
        )
    ).casefold()


def _complexity(item: Mapping[str, Any]) -> int:
    for value in (
        item.get("cyclomatic_complexity"),
        item.get("complexity"),
        item.get("measured_complexity"),
    ):
        parsed = _integer(value)
        if parsed:
            return parsed
    combined = _combined(item)
    for pattern in (
        r"cyclomatic[_\s-]*complexity\s*[=:]\s*(\d+)",
        r"complexity\s*[=:]\s*(\d+)",
    ):
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return 0


def _is_complexity(item: Mapping[str, Any]) -> bool:
    combined = _combined(item)
    return bool(
        _complexity(item)
        or "complexity-hotspot" in combined
        or "complexity_hotspot" in combined
        or "reduce complexity" in combined
        or "concentrated branch" in combined
    )


def _contains_any(value: str, tokens: tuple[str, ...]) -> bool:
    return any(token in value for token in tokens)


def _relevance(item: Mapping[str, Any]) -> dict[str, bool]:
    combined = _combined(item)
    return {
        "security": _contains_any(combined, _SECURITY_TOKENS),
        "delivery": _contains_any(combined, _DELIVERY_TOKENS),
        "recovery": _contains_any(combined, _RECOVERY_TOKENS),
        "data_integrity": _contains_any(combined, _DATA_INTEGRITY_TOKENS),
        "operations": _contains_any(combined, _OPERATIONS_TOKENS),
    }


def _evidence_confidence(item: Mapping[str, Any]) -> str:
    combined = _combined(item)
    explicit = _text(item.get("confidence") or item.get("evidence_confidence"), 80).casefold()
    if explicit in {"high", "medium", "low"}:
        return explicit
    if any(marker in combined for marker in ("compiler_ast", "compiler ast", "python ast", "exact-sha", "exact sha")):
        return "high"
    if "heuristic" in combined:
        return "medium"
    return "medium" if item.get("location") or item.get("path") else "low"


def _production_exposure(item: Mapping[str, Any]) -> str:
    path = _text(item.get("path") or item.get("location"), 1200).casefold()
    if any(part in path.split("/") for part in ("test", "tests", "fixture", "fixtures", "example", "examples")):
        return "non_production"
    if path.startswith(("apps/", "nico/", "scripts/")):
        return "production_or_operational"
    return "unknown"


def _priority_for_complexity(item: Mapping[str, Any]) -> dict[str, Any]:
    complexity = _complexity(item)
    relevance = _relevance(item)
    confidence = _evidence_confidence(item)
    exposure = _production_exposure(item)

    complexity_points = min(30, max(0, complexity - 25))
    relevance_points = (
        (30 if relevance["security"] else 0)
        + (24 if relevance["delivery"] else 0)
        + (22 if relevance["recovery"] else 0)
        + (14 if relevance["data_integrity"] else 0)
        + (12 if relevance["operations"] else 0)
    )
    exposure_points = 8 if exposure == "production_or_operational" else 0
    confidence_points = {"high": 8, "medium": 4, "low": 0}[confidence]
    priority_score = min(100, complexity_points + relevance_points + exposure_points + confidence_points)
    critical_path = any(relevance.values())

    # Complexity alone is a maintainability issue. P1 requires a separately
    # evidenced critical path and a sufficiently high combined risk score.
    if critical_path and complexity >= 35 and priority_score >= 45:
        priority = "P1"
    elif complexity >= 30:
        priority = "P2"
    else:
        priority = "P3"

    technical_severity = (
        "high"
        if complexity >= 40
        else "moderate"
        if complexity >= 30
        else "low"
    )
    relevant_names = [name.replace("_", " ") for name, active in relevance.items() if active]
    if priority == "P1":
        rationale = (
            f"P1 elevation is based on measured cyclomatic complexity {complexity}, "
            f"{', '.join(relevant_names)} critical-path relevance, {exposure.replace('_', ' ')}, "
            f"and {confidence} evidence confidence; complexity alone did not create P1."
        )
    elif priority == "P2":
        rationale = (
            f"P2 maintainability priority: measured cyclomatic complexity {complexity} exceeds the "
            "review threshold, but retained evidence does not establish a delivery-blocking, security-critical, "
            "or otherwise P1-level consequence."
        )
    else:
        rationale = (
            f"P3 localized maintainability priority: measured cyclomatic complexity {complexity} does not "
            "meet the P1 or P2 evidence threshold."
        )

    return {
        "priority": priority,
        "priority_score": priority_score,
        "priority_rationale": rationale,
        "technical_severity": technical_severity,
        "production_exposure": exposure,
        "critical_path_relevance": relevant_names,
        "security_relevance": relevance["security"],
        "authorization_relevance": relevance["security"] and "auth" in _combined(item),
        "delivery_relevance": relevance["delivery"],
        "recovery_relevance": relevance["recovery"],
        "data_integrity_relevance": relevance["data_integrity"],
        "operations_relevance": relevance["operations"],
        "evidence_confidence": confidence,
        "measured_cyclomatic_complexity": complexity,
        "priority_model_version": MODEL,
        "complexity_alone_created_p1": False,
    }


def calibrate_finding(item: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(item))
    if _is_complexity(output):
        output.update(_priority_for_complexity(output))
    else:
        existing = _text(output.get("priority") or "P2", 20).upper()
        priority = existing if existing in _PRIORITY_ORDER else "P2"
        output["priority"] = priority
        output["priority_score"] = _integer(output.get("priority_score"))
        output["priority_rationale"] = _text(output.get("priority_rationale")) or (
            "Priority retained from non-complexity evidence. Human review must confirm severity, impact, and urgency."
        )
        output["technical_severity"] = output.get("technical_severity") or output.get("severity") or "unknown"
        output["production_exposure"] = output.get("production_exposure") or _production_exposure(output)
        output["critical_path_relevance"] = output.get("critical_path_relevance") or []
        output["evidence_confidence"] = output.get("evidence_confidence") or _evidence_confidence(output)
        output["priority_model_version"] = MODEL
        output["complexity_alone_created_p1"] = False
    return output


def calibrate_finding_register(register: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(register))
    all_records: list[dict[str, Any]] = []
    for surface in (
        "code_findings",
        "operational_findings",
        "excluded_non_production_findings",
    ):
        records = [
            calibrate_finding(item)
            for item in output.get(surface) or []
            if isinstance(item, Mapping)
        ]
        records.sort(
            key=lambda item: (
                _PRIORITY_ORDER.get(_text(item.get("priority")).upper(), 9),
                -_integer(item.get("priority_score")),
                -_integer(item.get("measured_cyclomatic_complexity")),
                _text(item.get("path") or item.get("location")),
                _integer(item.get("line")),
                _text(item.get("finding_id")),
            )
        )
        output[surface] = records
        if surface != "excluded_non_production_findings":
            all_records.extend(records)

    distribution = {priority: 0 for priority in ("P0", "P1", "P2", "P3")}
    for item in all_records:
        priority = _text(item.get("priority")).upper()
        if priority in distribution:
            distribution[priority] += 1
    p1_without_rationale = [
        _text(item.get("finding_id"))
        for item in all_records
        if item.get("priority") == "P1" and not _text(item.get("priority_rationale"))
    ]
    complexity_p1_without_critical_path = [
        _text(item.get("finding_id"))
        for item in all_records
        if item.get("priority") == "P1"
        and _is_complexity(item)
        and not list(item.get("critical_path_relevance") or [])
    ]
    summary = deepcopy(dict(output.get("summary") or {}))
    summary.update(
        {
            "priority_model_version": MODEL,
            "priority_distribution": distribution,
            "p1_count": distribution["P1"],
            "p2_count": distribution["P2"],
            "p3_count": distribution["P3"],
            "p1_elevation_rationale_required": True,
            "p1_without_rationale": p1_without_rationale,
            "complexity_p1_without_critical_path": complexity_p1_without_critical_path,
            "complexity_alone_creates_p1": False,
            "priority_order_deterministic": True,
            "priority_contract_verified": (
                not p1_without_rationale and not complexity_p1_without_critical_path
            ),
        }
    )
    output["summary"] = summary
    return output


def install_client_finding_priority_calibration_v1() -> dict[str, Any]:
    from nico import client_report_completion_v2 as completion

    current = completion._install_register
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "model": MODEL,
            "complexity_alone_creates_p1": False,
        }

    def _install_register(canonical: dict[str, Any]) -> dict[str, Any]:
        installed = current(canonical)
        register = installed.get("client_finding_remediation_register")
        if not isinstance(register, Mapping):
            return installed
        calibrated = calibrate_finding_register(register)
        synchronized = completion.synchronize_canonical_finding_surfaces(
            installed,
            calibrated,
        )
        synchronized["client_finding_remediation_register"] = deepcopy(calibrated)
        synchronized["finding_population"] = deepcopy(calibrated.get("summary") or {})
        contract = deepcopy(dict(synchronized.get("v2_pipeline_contract") or {}))
        contract.update(
            {
                "finding_priority_model_version": MODEL,
                "complexity_alone_creates_p1": False,
                "p1_elevation_rationale_required": True,
                "priority_order_deterministic": True,
                "priority_contract_verified": calibrated.get("summary", {}).get(
                    "priority_contract_verified"
                )
                is True,
            }
        )
        synchronized["v2_pipeline_contract"] = contract
        return synchronized

    setattr(_install_register, _MARKER, True)
    setattr(_install_register, "_nico_previous", current)
    completion._install_register = _install_register
    return {
        "status": "installed",
        "version": VERSION,
        "model": MODEL,
        "complexity_alone_creates_p1": False,
        "p1_elevation_rationale_required": True,
        "priority_order_deterministic": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MODEL",
    "VERSION",
    "calibrate_finding",
    "calibrate_finding_register",
    "install_client_finding_priority_calibration_v1",
]
