from nico.access.policy import require_permission
from nico.agent_security.models import AgentConfig
from nico.agent_security.scanner import scan_agent_config
from nico.approvals.workflow import evaluate_action
from nico.connectors.base import ConnectorRequest
from nico.connectors.guard import evaluate_connector_request
from nico.scanners.sandbox import SandboxPlan, safe_scanner_output, validate_sandbox_plan
from nico.security.masking import mask_text
from nico.security.vault import LocalDemoVault
from nico.swarm.orchestrator import plan_agent_task
from nico.tenancy.isolation import can_access_tenant_resource
from nico.tenancy.models import TenantContext


def test_agent_security_flags_overbroad_permissions():
    findings = scan_agent_config(AgentConfig(name="risky", tools=("scanner", "shell"), can_mutate=True, requires_approval=False))
    categories = {finding["category"] for finding in findings}
    assert "over_broad_tool_permissions" in categories
    assert "autonomous_mutation_permission" in categories


def test_secret_masking_and_vault_reference_only():
    raw = 'API_KEY="FAKE_TEST_ONLY_SECRET_123456"'
    assert "FAKE_TEST_ONLY_SECRET_123456" not in mask_text(raw)
    vault = LocalDemoVault()
    ref = vault.store_secret_reference("demo/api", "demo", "FAKE_TEST_ONLY_SECRET_123456")
    assert ref.masked_value != "FAKE_TEST_ONLY_SECRET_123456"
    assert vault.resolve_secret_for_approved_operation("demo/api", "op")["allowed"] is False


def test_rbac_and_approval_gates():
    assert require_permission("viewer", "production_mutation", approved=True)["allowed"] is False
    assert evaluate_action("production_mutation", approved=False).allowed is False
    assert evaluate_action("production_mutation", approved=True).allowed is True


def test_tenant_isolation_blocks_cross_tenant_reads():
    context = TenantContext(tenant_id="tenant-a")
    assert can_access_tenant_resource(context, "tenant-a") is True
    assert can_access_tenant_resource(context, "tenant-b") is False


def test_connector_disabled_by_default():
    request = ConnectorRequest(connector="github", operation="inspect_repository", role="owner", approved=True, has_secret_reference=True)
    decision = evaluate_connector_request(request)
    assert decision["allowed"] is False
    assert decision["reason"] == "connector_disabled_by_default"


def test_swarm_blocks_report_mutation_and_secret_memory():
    assert plan_agent_task("report", "mutate", approved=True)["allowed"] is False
    secret_decision = plan_agent_task("memory", "memory_summary", memory_zone="secret_memory")
    assert secret_decision["allowed"] is False


def test_sandbox_policy_blocks_destructive_commands_and_masks_output(tmp_path):
    plan = SandboxPlan(command="rm -rf /", working_directory=str(tmp_path))
    assert validate_sandbox_plan(plan, str(tmp_path))["allowed"] is False
    assert "FAKE_TEST_ONLY_SECRET_123456" not in safe_scanner_output('token="FAKE_TEST_ONLY_SECRET_123456"')
