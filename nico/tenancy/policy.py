from __future__ import annotations

TENANT_SCOPED_RESOURCES = {"scan_history", "reports", "findings", "repair_memory", "audit_logs", "api_usage", "connector_settings", "vault_references", "billing_records_placeholder"}


def resource_is_tenant_scoped(resource_type: str) -> bool:
    return resource_type in TENANT_SCOPED_RESOURCES
