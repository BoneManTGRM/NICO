from __future__ import annotations

from .models import TenantContext


def tenant_key(context: TenantContext, resource_type: str, resource_id: str) -> str:
    return f"{context.tenant_id}:{resource_type}:{resource_id}"


def can_access_tenant_resource(context: TenantContext, resource_tenant_id: str) -> bool:
    return context.tenant_id == resource_tenant_id
