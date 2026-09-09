from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

VERSION = "nico.comprehensive_review_client_approval.v1"


def project_client_delivery_approval_readiness(
    record: Mapping[str, Any],
    projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Add bounded client-approval identity truth to a review-work projection.

    Human review/QC readiness and client-delivery identity are separate gates.  This
    projection reuses the exact Phase-3 authority used by final approval and exposes
    only bounded status values; it never exposes retained contact/access/scope text.
    """

    from nico.phase3_engagement_intake_v1 import engagement_truth

    result = deepcopy(dict(projection))
    truth = engagement_truth(record)
    eligible = truth.get("client_delivery_identity_valid") is True
    mode = str(truth.get("mode") or "").strip().casefold()
    result.update(
        {
            "client_delivery_approval_eligible": eligible,
            "client_delivery_engagement_mode": (
                mode if mode in {"client", "internal"} else "unknown"
            ),
            "client_delivery_approval_blockers": (
                [] if eligible else ["client_delivery_identity_required"]
            ),
            "client_delivery_identity_values_exposed": False,
        }
    )
    return result


__all__ = [
    "VERSION",
    "project_client_delivery_approval_readiness",
]
