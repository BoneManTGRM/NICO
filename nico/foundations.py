from __future__ import annotations

from nico.access.permissions import ROLE_PERMISSIONS
from nico.agent_security.models import AgentConfig
from nico.agent_security.report import agent_security_report
from nico.agent_security.scanner import scan_agent_config
from nico.approvals.workflow import evaluate_action
from nico.connectors.base import ConnectorRequest
from nico.connectors.guard import evaluate_connector_request
from nico.connectors.github import GITHUB_CONNECTOR_POLICY
from nico.scanners.adapters import adapter_status
from nico.scanners.sandbox import SandboxPlan, safe_scanner_output, validate_sandbox_plan
from nico.security.vault import LocalDemoVault
from nico.swarm.orchestrator import plan_agent_task, swarm_policy
from nico.swarm.permissions import permission_matrix
from nico.tenancy.isolation import can_access_tenant_resource, tenant_key
from nico.tenancy.models import TenantContext

LOCAL_ONLY_NOTICE = "local_only_demo_no_external_calls"


def swarm_policy_demo() -> dict:
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "policy": swarm_policy(),
        "permissions": permission_matrix(),
        "sample_decisions": [
            plan_agent_task("report", "mutate", approved=False),
            plan_agent_task("memory", "memory_summary", memory_zone="secret_memory"),
            plan_agent_task("supervisor", "require_approval"),
        ],
    }


def agent_security_scan_demo() -> dict:
    configs = [
        AgentConfig(name="Report Agent", tools=("report",), memory_zones=("finding_memory",), can_export=False),
        AgentConfig(name="Risky Demo Agent", tools=("scanner", "shell"), memory_zones=("secret_memory",), can_mutate=True, requires_approval=False, connector_access=("github",)),
    ]
    findings = []
    for config in configs:
        findings.extend(scan_agent_config(config))
    report = agent_security_report(findings)
    report["mode"] = LOCAL_ONLY_NOTICE
    report["scanned_agents"] = [config.name for config in configs]
    return report


def vault_demo() -> dict:
    vault = LocalDemoVault()
    ref = vault.store_secret_reference("demo/api-reference", "local demo placeholder", "DEMO_PLACEHOLDER_VALUE")
    denied = vault.resolve_secret_for_approved_operation(ref.reference_id, "unapproved-demo")
    vault.approve_placeholder_operation("approved-placeholder-demo")
    approved = vault.resolve_secret_for_approved_operation(ref.reference_id, "approved-placeholder-demo")
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "reference": ref.__dict__,
        "denied_without_approval": denied,
        "approved_placeholder_resolution": approved,
        "rotation": vault.rotate_secret_reference(ref.reference_id),
    }


def connector_policy_demo() -> dict:
    request = ConnectorRequest(connector="github", operation="inspect_repository", role="owner", approved=True, has_secret_reference=True)
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "policy": GITHUB_CONNECTOR_POLICY.__dict__.copy(),
        "sample_request_decision": evaluate_connector_request(request),
    }


def sandbox_scanner_demo() -> dict:
    allowed = SandboxPlan(command="python -m pytest tests", working_directory=".")
    blocked = SandboxPlan(command="rm -rf /", working_directory=".")
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "adapter_status": adapter_status(),
        "allowed_plan": validate_sandbox_plan(allowed, "."),
        "blocked_plan": validate_sandbox_plan(blocked, "."),
        "masked_output": safe_scanner_output('token="DEMO_PLACEHOLDER_VALUE"'),
    }


def audit_latest_demo(records: list[dict] | None = None) -> dict:
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "records": records or [],
        "note": "Audit records are local and masked where sensitive values appear.",
    }


def approvals_pending_demo() -> dict:
    actions = ["production_mutation", "external_connector_access", "report_export", "high_risk_swarm_action"]
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "pending": [evaluate_action(action).__dict__ for action in actions],
    }


def tenant_demo() -> dict:
    context = TenantContext(tenant_id="tenant-a", actor_role="analyst")
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "tenant_key": tenant_key(context, "finding", "demo-001"),
        "same_tenant_allowed": can_access_tenant_resource(context, "tenant-a"),
        "cross_tenant_allowed": can_access_tenant_resource(context, "tenant-b"),
        "role_permissions": sorted(ROLE_PERMISSIONS.get(context.actor_role, set())),
    }


def cyber_twin_demo() -> dict:
    return {
        "mode": LOCAL_ONLY_NOTICE,
        "nodes": [
            {"id": "asset:local-demo", "type": "asset", "label": "Local Demo Workspace"},
            {"id": "file:webhook", "type": "file", "label": "webhook fixture"},
            {"id": "finding:masked", "type": "finding", "label": "masked local finding"},
            {"id": "repair:tgrm", "type": "repair", "label": "targeted repair plan"},
            {"id": "verification:pending", "type": "verification", "label": "local verification step"},
        ],
        "edges": [
            {"from": "asset:local-demo", "to": "file:webhook", "type": "contains"},
            {"from": "file:webhook", "to": "finding:masked", "type": "has_finding"},
            {"from": "finding:masked", "to": "repair:tgrm", "type": "has_repair_plan"},
            {"from": "repair:tgrm", "to": "verification:pending", "type": "requires_verification"},
        ],
    }


def bench_demo() -> dict:
    checks = [
        {"metric": "finding_quality", "status": "planned_fixture"},
        {"metric": "masking_success", "status": "demo_checked"},
        {"metric": "repair_plan_quality", "status": "planned_fixture"},
        {"metric": "approval_boundary_success", "status": "demo_checked"},
        {"metric": "verification_success", "status": "planned_fixture"},
        {"metric": "false_positive_control", "status": "planned_fixture"},
        {"metric": "swarm_risk_control", "status": "demo_checked"},
        {"metric": "regression_safety", "status": "planned_fixture"},
    ]
    return {"mode": LOCAL_ONLY_NOTICE, "benchmark_claim": "no_production_benchmark_claimed", "checks": checks}
