from __future__ import annotations

from nico.security.masking import mask_text

from .models import AgentConfig
from .policy import SAFE_TOOLS, SENSITIVE_MEMORY_ZONES


def _finding(category: str, severity: str, evidence: str, recommendation: str) -> dict:
    return {
        "category": category,
        "severity": severity,
        "masked_evidence": mask_text(evidence),
        "recommendation": recommendation,
    }


def scan_agent_config(config: AgentConfig) -> list[dict]:
    findings = []
    unknown_tools = sorted(set(config.tools) - SAFE_TOOLS)
    if unknown_tools:
        findings.append(_finding("over_broad_tool_permissions", "high", ",".join(unknown_tools), "Restrict tools to least privilege."))
    if config.can_mutate and not config.requires_approval:
        findings.append(_finding("autonomous_mutation_permission", "critical", config.name, "Require human approval before mutation."))
    if config.can_export and not config.requires_approval:
        findings.append(_finding("report_export_without_approval", "high", config.name, "Require approval before export."))
    if set(config.memory_zones) & SENSITIVE_MEMORY_ZONES:
        findings.append(_finding("unsafe_memory_access", "high", ",".join(config.memory_zones), "Block raw sensitive memory access."))
    if config.connector_access and not config.requires_approval:
        findings.append(_finding("connector_access_without_approval", "high", ",".join(config.connector_access), "Require connector approval gates."))
    return findings
