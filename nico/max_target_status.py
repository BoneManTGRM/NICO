from __future__ import annotations

from typing import Any

from nico.client_ready_evidence import build_client_ready_evidence
from nico.mid_evidence_upgrade import build_mid_evidence_upgrade
from nico.retainer_ops_evidence import build_retainer_ops_evidence
from nico.service_coverage_gaps import service_coverage_gap

TARGETS = {
    "express": 95,
    "mid": 85,
    "retainer": 70,
    "client_ready": 85,
}


def build_max_target_status(payload: dict[str, Any]) -> dict[str, Any]:
    express = service_coverage_gap(payload, "express")
    mid = build_mid_evidence_upgrade(payload)
    retainer = build_retainer_ops_evidence(payload)
    client_ready = build_client_ready_evidence(payload)
    services = {
        "express": {
            "target": TARGETS["express"],
            "score": express["current"],
            "gap": express["gap"],
            "missing": express["missing"],
            "ready_for_max": express["ready_for_max"],
        },
        "mid": {
            "target": TARGETS["mid"],
            "score": mid["score"],
            "gap": max(TARGETS["mid"] - mid["score"], 0),
            "missing": mid["missing"],
            "ready_for_max": mid["score"] >= TARGETS["mid"] and not mid["missing"],
        },
        "retainer": {
            "target": TARGETS["retainer"],
            "score": retainer["score"],
            "gap": max(TARGETS["retainer"] - retainer["score"], 0),
            "missing": retainer["missing"],
            "ready_for_max": retainer["score"] >= TARGETS["retainer"] and not retainer["missing"],
        },
        "client_ready": {
            "target": TARGETS["client_ready"],
            "score": client_ready["score"],
            "gap": max(TARGETS["client_ready"] - client_ready["score"], 0),
            "missing": client_ready["missing"],
            "ready_for_max": client_ready["score"] >= TARGETS["client_ready"] and not client_ready["missing"],
        },
    }
    total_score = round(sum(item["score"] for item in services.values()) / len(services))
    total_target = round(sum(item["target"] for item in services.values()) / len(services))
    ordered_next = []
    for service, item in services.items():
        for missing in item["missing"]:
            ordered_next.append({"service": service, "gate": missing})
    return {
        "status": "green" if total_score >= total_target and not ordered_next else "yellow" if total_score >= 60 else "red",
        "overall_score": total_score,
        "overall_target": total_target,
        "overall_gap": max(total_target - total_score, 0),
        "ready_for_all_max": all(item["ready_for_max"] for item in services.values()),
        "services": services,
        "next_gates": ordered_next,
        "rule": "Max target status combines service coverage, Mid evidence, retainer operating evidence, and client-ready delivery evidence. It does not replace human review, stakeholder input, or client acceptance.",
    }
