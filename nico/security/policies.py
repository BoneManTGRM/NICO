from __future__ import annotations

SECRET_POLICY = {
    "raw_secret_logging": "blocked",
    "report_secret_exposure": "masked_reference_only",
    "vault_mode": "local_placeholder",
    "production_encryption": "not_enabled",
    "approval_required_for_secret_use": True,
}


def secret_use_allowed(has_permission: bool, has_approval: bool) -> bool:
    return bool(has_permission and has_approval)
