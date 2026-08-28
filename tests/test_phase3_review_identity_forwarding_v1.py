from __future__ import annotations

from typing import Any

from nico.phase3_engagement_intake_v1 import _guard_service


def test_phase3_production_guard_forwards_exact_artifact_identity_unchanged() -> None:
    expected = {
        "artifact_schema": "nico.comprehensive_review_artifact_identity.v1",
        "run_id": "comprun-phase3-forwarding",
        "revision": 9,
        "report_artifact_digest": "a" * 64,
        "artifact_digests": {"pdf": {"sha256": "b" * 64, "size_bytes": 24}},
    }

    class Service:
        def __init__(self) -> None:
            self.kwargs: dict[str, Any] = {}

        def load(self, run_id: str) -> dict[str, Any]:
            return {
                "identity": {
                    "run_id": run_id,
                    "customer_id": "client-customer",
                    "project_id": "client-project",
                },
                "human_evidence": {
                    "modules": {
                        "stakeholder_context": {
                            "evidence": {
                                "engagement_mode": ["client"],
                                "client_identity": ["Client Literal"],
                                "project_identity": ["Project Literal"],
                                "primary_technical_contact": ["Owner"],
                                "access_method": ["Read-only access"],
                                "authorized_scope": ["Exact repository scope"],
                            }
                        }
                    }
                },
            }

        def review(self, run_id: str, **kwargs: Any) -> dict[str, Any]:
            self.kwargs = {"run_id": run_id, **kwargs}
            return {"status": "approved"}

    service = Service()
    assert _guard_service(service) is True
    service.review(
        "comprun-phase3-forwarding",
        reviewer="Authorized Human",
        reviewer_role="Security reviewer",
        decision="approved",
        decision_reason="Reviewed exact artifacts.",
        decided_at="2026-08-28T00:00:00+00:00",
        expected_artifact_identity=expected,
    )

    assert service.kwargs["expected_artifact_identity"] is expected
