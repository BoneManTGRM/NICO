from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefensiveAgent:
    name: str
    role: str
    allowed_tools: tuple[str, ...]
    memory_zones: tuple[str, ...]
    can_mutate: bool = False
    can_export: bool = False


DEFENSIVE_AGENTS = {
    "scan": DefensiveAgent("Scan Agent", "scan", ("scanner",), ("scan_memory", "finding_memory")),
    "drift": DefensiveAgent("Drift Agent", "drift", ("drift_detector",), ("scan_memory", "finding_memory")),
    "rye": DefensiveAgent("RYE Scoring Agent", "rye_scoring", ("rye_score",), ("finding_memory", "repair_memory")),
    "tgrm": DefensiveAgent("TGRM Repair Agent", "repair", ("repair_plan",), ("repair_memory",), can_mutate=False),
    "verification": DefensiveAgent("Verification Agent", "verification", ("verify",), ("verification_memory",)),
    "memory": DefensiveAgent("Memory Agent", "memory", ("memory_summary",), ("scan_memory", "finding_memory", "repair_memory", "verification_memory")),
    "compliance": DefensiveAgent("Compliance Agent", "compliance", ("mapping",), ("finding_memory",)),
    "report": DefensiveAgent("Report Agent", "report", ("report",), ("finding_memory", "verification_memory"), can_export=False),
    "connector_guard": DefensiveAgent("Connector Guard Agent", "connector_guard", ("connector_policy",), ("scan_memory",)),
    "supervisor": DefensiveAgent("Swarm Supervisor Agent", "supervision", ("stop", "require_approval"), ("scan_memory", "finding_memory", "repair_memory", "verification_memory")),
}
