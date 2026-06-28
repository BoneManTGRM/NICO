from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set

from .masking import mask_secret_value


@dataclass(frozen=True)
class SecretReference:
    reference_id: str
    purpose: str
    masked_value: str


@dataclass
class LocalDemoVault:
    """Local-only placeholder vault that stores references, not raw secrets."""

    references: Dict[str, SecretReference] = field(default_factory=dict)
    approved_operations: Set[str] = field(default_factory=set)

    def store_secret_reference(self, reference_id: str, purpose: str, demo_value: str = "placeholder") -> SecretReference:
        ref = SecretReference(reference_id=reference_id, purpose=purpose, masked_value=mask_secret_value(demo_value))
        self.references[reference_id] = ref
        return ref

    def deny_unapproved_secret_access(self, reference_id: str) -> dict:
        return {"allowed": False, "reference_id": reference_id, "reason": "approval_required"}

    def approve_placeholder_operation(self, operation_id: str) -> None:
        self.approved_operations.add(operation_id)

    def resolve_secret_for_approved_operation(self, reference_id: str, operation_id: str) -> dict:
        if operation_id not in self.approved_operations:
            return self.deny_unapproved_secret_access(reference_id)
        ref = self.references.get(reference_id)
        return {"allowed": bool(ref), "reference_id": reference_id, "masked_value": ref.masked_value if ref else "***"}

    def rotate_secret_reference(self, reference_id: str) -> dict:
        return {"reference_id": reference_id, "status": "rotation_placeholder_requires_operator_action"}
